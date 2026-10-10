"""
Stop loss and take profit read from the market at the moment of entry. Owner, 2026-10-10: "debería
ser con análisis: a veces 15 de stop loss y 10 de profit, a veces 10 de stop y 15 de profit,
siempre con lógica del mercado y análisis del momento".

For one entry, from the bars the engine already has:
- Volatility: the coin's recent noise projected over ~4 hours (stop_floor.volatility_stop_pct).
- Structure: the recent support (lowest low) and resistance (highest high) over ~4 hours of bars.
- Regime (detect_regime): a trend or breakout up lets profits run; anything else (range, no edge)
  aims for a nearer target, because mean reversion pays back less than it risks.

Stop: below the support (a small buffer) or 2.5 x volatility, whichever is farther, inside the
owner's band [min_stop_pct, max_stop_pct]. If the engine already set the stop, that stop is kept.

Target:
- trend: the resistance or 1.5 x the volatility move, whichever is farther, kept between 1.2x and
  3x the stop distance (it may go past resistance; the trailing stop protects it meanwhile);
- range: the resistance or the volatility move, whichever is nearer, kept between 0.6x and 1.5x
  the stop distance.
So the reward/risk changes with the market: e.g. a wide stop under support with a near resistance
in a range gives "stop 15, profit 10"; a tight stop in a strong trend gives "stop 10, profit 15+".

These are rules, not a proven optimum: every plan is written to the session journal, so the trades
themselves measure which kind works, by regime and by coin.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Optional

import pandas as pd

from trading_intelligence.strategy.stop_floor import VOL_MULT, volatility_stop_pct

STRUCTURE_MINUTES = 240
SUPPORT_BUFFER_PCT = Decimal("0.2")
TREND_BAND = (Decimal("1.2"), Decimal("3"))
RANGE_BAND = (Decimal("0.6"), Decimal("1.5"))
Q = Decimal("0.00000001")


@dataclass(frozen=True)
class ExitPlan:
    side: str
    entry: Decimal
    stop: Decimal
    target: Decimal
    kind: str  # "tendencia" or "rango"
    stop_pct: Decimal
    target_pct: Decimal
    why: str

    @property
    def reward_risk(self) -> Decimal:
        return (self.target_pct / self.stop_pct).quantize(Decimal("0.01")) if self.stop_pct > 0 else Decimal("0")


def _bars_in(data: pd.DataFrame, minutes: int) -> int:
    if len(data.index) < 2:
        return len(data)
    step = (data.index[-1] - data.index[-2]).total_seconds() / 60
    return max(int(minutes / step) if step > 0 else len(data), 2)


def market_kind(data: pd.DataFrame, side: str = "BUY") -> str:
    """"tendencia" when the market runs in the trade's direction (up for a buy, down for a sell)."""
    from trading_intelligence.regime.detector import Regime, detect_regime

    try:
        regime = detect_regime(data).regime
    except Exception:  # noqa: BLE001 - not enough history: be conservative
        return "rango"
    with_trade = (Regime.TREND_UP, Regime.BREAKOUT_UP) if side == "BUY" else (Regime.TREND_DOWN, Regime.BREAKOUT_DOWN)
    return "tendencia" if regime in with_trade else "rango"


def plan_exits(data: pd.DataFrame, entry: Decimal, *, side: str = "BUY", kind: Optional[str] = None,
               stop_price: Optional[Decimal] = None, min_stop_pct: Decimal = Decimal("3"),
               max_stop_pct: Decimal = Decimal("15")) -> ExitPlan:
    if side not in ("BUY", "SELL") or entry <= 0:
        raise ValueError("side must be BUY or SELL and entry positive")
    kind = kind or market_kind(data, side)
    window = data.tail(_bars_in(data, STRUCTURE_MINUTES))
    support, resistance = Decimal(str(window["low"].min())), Decimal(str(window["high"].max()))
    vol = volatility_stop_pct(data)
    vol_move = VOL_MULT * vol if vol is not None else min_stop_pct  # % of price
    sign = 1 if side == "BUY" else -1

    if stop_price is not None and stop_price > 0:
        stop_pct = abs(entry - stop_price) / entry * 100
        why_stop = "stop del motor"
    else:
        # beyond the nearest level against the position (support for a buy, resistance for a sell)
        level = support if side == "BUY" else resistance
        struct_pct = (abs(entry - level) / entry * 100 + SUPPORT_BUFFER_PCT) if (level - entry) * sign < 0 else Decimal("0")
        stop_pct = max(vol_move, struct_pct)
        why_stop = "debajo del soporte" if struct_pct >= vol_move else "por volatilidad"
        stop_pct = min(max(stop_pct, min_stop_pct), max_stop_pct)

    level = resistance if side == "BUY" else support
    room_pct = abs(level - entry) / entry * 100 if (level - entry) * sign > 0 else Decimal("0")
    if kind == "tendencia":
        lo, hi = TREND_BAND
        wanted = max(room_pct, vol_move * Decimal("1.5"))
        why_target = "tendencia: dejar correr hasta resistencia o más"
    else:
        lo, hi = RANGE_BAND
        wanted = min(room_pct, vol_move) if room_pct > 0 else vol_move
        why_target = "rango: meta cercana, en la resistencia"
    target_pct = min(max(wanted, lo * stop_pct), hi * stop_pct)

    stop_pct, target_pct = stop_pct.quantize(Decimal("0.01")), target_pct.quantize(Decimal("0.01"))
    stop = (entry * (1 - sign * stop_pct / 100)).quantize(Q, rounding=ROUND_DOWN)
    target = (entry * (1 + sign * target_pct / 100)).quantize(Q, rounding=ROUND_DOWN)
    if stop_price is not None and stop_price > 0:
        stop = stop_price
    return ExitPlan(side, entry, stop, target, kind, stop_pct, target_pct, f"{why_stop}; {why_target}")
