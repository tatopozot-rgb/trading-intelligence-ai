"""
Two-way entry signals for futures-like markets (XM CFDs, Binance USDⓈ-M). Owner, 2026-10-10: "lo
mismo pero para futuros y debe ser mejor analizado" — the same logic as the Spot program's
"tendencia_rango" profile (regime detector -> trend: 20/50 moving averages; range: Bollinger
reversion), mirrored for selling short, plus an optional check against the 1-hour trend.

One pure decision function (decide) is used by the live engine and by the backtest
(backtesting/two_way_backtest.py), so what is measured is exactly what trades.

Variants (the backtest compares them on real data before one is chosen):
- "regimen": the regime alone (trend/breakout up -> BUY, down -> SELL).
- "tendencia_rango": trend or breakout up AND fast MA above slow MA -> BUY (mirror for SELL);
  in a range, a close below the lower Bollinger band -> BUY, above the upper band -> SELL.
- "tendencia_rango_1h": the same, but never against the 1-hour trend (20/50 MAs on 1h bars).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import pandas as pd

from trading_intelligence.regime.detector import Regime, detect_regime

FAST, SLOW, BB_PERIOD, BB_STD = 20, 50, 20, 2.0
UP, DOWN = (Regime.TREND_UP, Regime.BREAKOUT_UP), (Regime.TREND_DOWN, Regime.BREAKOUT_DOWN)
VARIANTS = ("regimen", "tendencia_rango", "tendencia_rango_1h")
DEFAULT_VARIANT = "tendencia_rango_1h"


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


def read(data: pd.DataFrame, htf: Optional[pd.DataFrame] = None) -> Reading:
    close = data["close"]
    try:
        regime: Optional[Regime] = detect_regime(data).regime
    except Exception:  # noqa: BLE001 - not enough history: no reading
        regime = None
    mid, sd = close.rolling(BB_PERIOD).mean().iloc[-1], close.rolling(BB_PERIOD).std().iloc[-1]
    return Reading(regime, float(close.iloc[-1]), float(close.rolling(FAST).mean().iloc[-1]),
                   float(close.rolling(SLOW).mean().iloc[-1]), float(mid - BB_STD * sd), float(mid + BB_STD * sd),
                   htf_direction(htf))


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
    if variant == "tendencia_rango_1h" and side is not None and r.htf is not None and r.htf != side:
        return None  # never against the 1-hour trend
    return side


def signal_for(variant: str = DEFAULT_VARIANT) -> Callable[[str, pd.DataFrame, Optional[pd.DataFrame]], Optional[str]]:
    """The engine's signal: (symbol, decision bars, 1-hour bars) -> BUY / SELL / None."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}")

    def signal(symbol: str, data: pd.DataFrame, htf: Optional[pd.DataFrame] = None) -> Optional[str]:
        return decide(read(data, htf), variant)

    return signal
