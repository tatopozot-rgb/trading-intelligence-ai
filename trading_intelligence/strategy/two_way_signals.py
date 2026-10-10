"""
Two-way entry signals for futures-like markets (XM CFDs, Binance USDⓈ-M). Owner, 2026-10-10: "lo
mismo pero para futuros y debe ser mejor analizado", then "ya puede ver top traders de futuros en
binance, debe siempre revisar TODO" — the Spot program's "tendencia_rango" logic (regime detector ->
trend: 20/50 moving averages; range: Bollinger reversion) mirrored for selling short, checked against
the 1-hour trend and, on Binance, against what Binance's top traders hold.

One pure decision function (decide) and one quality score (quality) are used by the live engine and
by the backtest (backtesting/two_way_backtest.py), so what is measured is exactly what trades.

Variants (the backtest compares them on real data):
- "regimen": the regime alone (trend/breakout up -> BUY, down -> SELL).
- "tendencia_rango": trend or breakout up AND fast MA above slow MA -> BUY (mirror for SELL);
  in a range, a close below the lower Bollinger band -> BUY, above the upper band -> SELL.
- "tendencia_rango_1h": the same, never against the 1-hour trend.
- "tendencia_rango_1h_top": the same, and never against Binance's top traders (their long/short
  position ratio: above 1.1 they lean long, below 0.9 short). Without that data it behaves like
  "tendencia_rango_1h".

Quality (0-1) sizes the risk between the owner's 1% and 15% (live/two_way.py): half from how clearly
the regime reads (the detector's confidence), a quarter when the 1-hour trend agrees, a quarter when
the top traders agree. It depends only on the market, never on past wins or losses.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import pandas as pd

from trading_intelligence.regime.detector import Regime, detect_regime

FAST, SLOW, BB_PERIOD, BB_STD = 20, 50, 20, 2.0
TOP_LONG, TOP_SHORT = 1.1, 0.9  # top traders' long/short position ratio thresholds
UP, DOWN = (Regime.TREND_UP, Regime.BREAKOUT_UP), (Regime.TREND_DOWN, Regime.BREAKOUT_DOWN)
VARIANTS = ("regimen", "tendencia_rango", "tendencia_rango_1h", "tendencia_rango_1h_top")
DEFAULT_VARIANT = "tendencia_rango_1h_top"


@dataclass(frozen=True)
class Reading:
    """What one decision looks at, for one instrument at one bar."""
    regime: Optional[Regime]
    close: float
    fast: float
    slow: float
    bb_low: float
    bb_up: float
    htf: Optional[str]  # "BUY" / "SELL" / None: direction of the 1-hour trend
    confidence: float = 0.0  # the regime detector's confidence, 0-1
    top: Optional[str] = None  # "BUY" / "SELL" / None: where Binance's top traders lean


def top_direction(ratio: Optional[float]) -> Optional[str]:
    if ratio is None or ratio != ratio:  # NaN
        return None
    return "BUY" if ratio >= TOP_LONG else "SELL" if ratio <= TOP_SHORT else None


def htf_direction(htf: Optional[pd.DataFrame]) -> Optional[str]:
    if htf is None or len(htf) < SLOW:
        return None
    close = htf["close"]
    fast, slow, last = close.rolling(FAST).mean().iloc[-1], close.rolling(SLOW).mean().iloc[-1], close.iloc[-1]
    if fast > slow and last > slow:
        return "BUY"
    if fast < slow and last < slow:
        return "SELL"
    return None


def read(data: pd.DataFrame, htf: Optional[pd.DataFrame] = None, top_ratio: Optional[float] = None) -> Reading:
    close = data["close"]
    try:
        snap = detect_regime(data)
        regime: Optional[Regime] = snap.regime
        confidence = float(snap.confidence)
    except Exception:  # noqa: BLE001 - not enough history: no reading
        regime, confidence = None, 0.0
    mid, sd = close.rolling(BB_PERIOD).mean().iloc[-1], close.rolling(BB_PERIOD).std().iloc[-1]
    return Reading(regime, float(close.iloc[-1]), float(close.rolling(FAST).mean().iloc[-1]),
                   float(close.rolling(SLOW).mean().iloc[-1]), float(mid - BB_STD * sd), float(mid + BB_STD * sd),
                   htf_direction(htf), confidence, top_direction(top_ratio))


def decide(r: Reading, variant: str = DEFAULT_VARIANT) -> Optional[str]:
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}")
    if r.regime is None:
        return None
    if variant == "regimen":
        return "BUY" if r.regime in UP else "SELL" if r.regime in DOWN else None
    side: Optional[str] = None
    if r.regime in UP and r.fast > r.slow:
        side = "BUY"
    elif r.regime in DOWN and r.fast < r.slow:
        side = "SELL"
    elif r.regime == Regime.RANGE:
        side = "BUY" if r.close < r.bb_low else "SELL" if r.close > r.bb_up else None
    if variant in ("tendencia_rango_1h", "tendencia_rango_1h_top") and side is not None \
            and r.htf is not None and r.htf != side:
        return None  # never against the 1-hour trend
    if variant == "tendencia_rango_1h_top" and side is not None and r.top is not None and r.top != side:
        return None  # never against Binance's top traders
    return side


def quality(r: Reading, side: str) -> float:
    """0-1: how strongly the market backs this side right now (sizes the risk between 1% and 15%)."""
    q = 0.5 * max(0.0, min(1.0, r.confidence))
    q += 0.25 if r.htf == side else 0.0
    q += 0.25 if r.top == side else 0.0
    return round(min(1.0, q), 4)


Decision = tuple[str, float]  # (side, quality)


def signal_for(variant: str = DEFAULT_VARIANT) -> Callable[..., Optional[Decision]]:
    """The engine's signal: (symbol, decision bars, 1-hour bars, top=ratio) -> (side, quality) or None."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}")

    def signal(symbol: str, data: pd.DataFrame, htf: Optional[pd.DataFrame] = None,
               top: Optional[float] = None) -> Optional[Decision]:
        r = read(data, htf, top)
        side = decide(r, variant)
        return (side, quality(r, side)) if side is not None else None

    return signal
