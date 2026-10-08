"""
Market regime detection from OHLCV data alone.

Classifies using only data up to and including the current bar — same
no-lookahead discipline as BacktestEngine. Built entirely from
already-tested pure indicators (ADX, ATR, Donchian channel); adds no new
indicator math inline here.

Deliberately does NOT attempt to detect:
  - LIQUIDITY_STRESS (needs order-book depth; this package has none)
  - ABNORMAL_SPREAD (needs live bid/ask; this package has only OHLCV)
  - EVENT_DRIVEN (needs an economic/news calendar; not available here)
Faking a proxy for any of these from OHLCV alone would be exactly the
kind of invented confidence this project's own "Pessimistic Assumptions"
principle (docs/PAPER_TRADING_SIMULATION_SPEC.md) exists to prevent.
Callers that need those three must get them from a different, real data
source and layer them on top of this detector's output — not expect this
module to report them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

import pandas as pd

from trading_intelligence.analysis.indicators import adx, atr, donchian_high, donchian_low


class Regime(str, Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    BREAKOUT_UP = "BREAKOUT_UP"
    BREAKOUT_DOWN = "BREAKOUT_DOWN"
    NO_EDGE = "NO_EDGE"  # the honest default: no classification cleared its confidence bar


class Volatility(str, Enum):
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"  # not enough history yet to rank current ATR against its own percentile


NOT_AVAILABLE_FROM_OHLCV = ("LIQUIDITY_STRESS", "ABNORMAL_SPREAD", "EVENT_DRIVEN")


@dataclass(frozen=True)
class RegimeSnapshot:
    regime: Regime
    volatility: Volatility
    confidence: float  # 0.0-1.0: how clearly the data supports `regime`, not a probability
    metrics: Mapping[str, float]  # adx, atr_pct, atr_percentile, breakout levels — for audit
    unavailable: tuple = field(default=NOT_AVAILABLE_FROM_OHLCV)


DEFAULT_ADX_PERIOD = 14
DEFAULT_VOL_LOOKBACK = 100
DEFAULT_BREAKOUT_PERIOD = 20
DEFAULT_TREND_THRESHOLD = 25.0  # standard Wilder convention: ADX > 25 = trending
DEFAULT_RANGE_THRESHOLD = 20.0  # ADX < 20 = no clear trend
DEFAULT_VOL_HIGH_PCTL = 0.80
DEFAULT_VOL_LOW_PCTL = 0.20


def detect_regime(
    data: pd.DataFrame,
    *,
    adx_period: int = DEFAULT_ADX_PERIOD,
    vol_lookback: int = DEFAULT_VOL_LOOKBACK,
    breakout_period: int = DEFAULT_BREAKOUT_PERIOD,
    trend_threshold: float = DEFAULT_TREND_THRESHOLD,
    range_threshold: float = DEFAULT_RANGE_THRESHOLD,
    vol_high_pctl: float = DEFAULT_VOL_HIGH_PCTL,
    vol_low_pctl: float = DEFAULT_VOL_LOW_PCTL,
) -> RegimeSnapshot:
    """
    Classify the regime of the LAST bar in `data`.

    Args:
        data: OHLCV DataFrame, columns [open, high, low, close, volume],
              sorted ascending, no NaN. Pass all bars up to and including
              "now" — this function only ever looks at data already given,
              never ahead.

    Returns:
        RegimeSnapshot for the final row of `data`.
    """
    if range_threshold >= trend_threshold:
        raise ValueError(
            f"range_threshold ({range_threshold}) must be < trend_threshold ({trend_threshold})"
        )
    required_cols = {"open", "high", "low", "close", "volume"}
    missing = required_cols - set(data.columns)
    if missing:
        raise ValueError(f"data missing columns: {missing}")

    min_bars = max(adx_period, breakout_period) + 1
    if len(data) < min_bars:
        return RegimeSnapshot(
            regime=Regime.NO_EDGE,
            volatility=Volatility.UNKNOWN,
            confidence=0.0,
            metrics={"insufficient_data": True, "bars_available": len(data), "bars_required": min_bars},
        )

    high, low, close = data["high"], data["low"], data["close"]

    adx_series = adx(high, low, close, period=adx_period)
    current_adx = float(adx_series.iloc[-1])

    atr_series = atr(high, low, close, period=adx_period)
    atr_pct_series = atr_series / close
    current_atr_pct = float(atr_pct_series.iloc[-1])

    # Breakout is an EVENT (the first bar to clear a level), not a persistent state:
    # comparing only against the prior window still lets every bar of an established,
    # already-running trend re-trigger "breakout" forever, since each new high is
    # trivially above the one before it. Edge-trigger it: the previous bar must NOT
    # already have cleared the level it faced one bar earlier.
    prior_high = donchian_high(close.shift(1), breakout_period)
    prior_low = donchian_low(close.shift(1), breakout_period)
    current_close = float(close.iloc[-1])
    level_high = prior_high.iloc[-1]
    level_low = prior_low.iloc[-1]
    prev_close = float(close.iloc[-2])
    prev_level_high = prior_high.iloc[-2] if len(prior_high) > 1 else float("nan")
    prev_level_low = prior_low.iloc[-2] if len(prior_low) > 1 else float("nan")
    prev_already_above = pd.notna(prev_level_high) and prev_close > prev_level_high
    prev_already_below = pd.notna(prev_level_low) and prev_close < prev_level_low
    breakout_up = pd.notna(level_high) and current_close > level_high and not prev_already_above
    breakout_down = pd.notna(level_low) and current_close < level_low and not prev_already_below

    metrics = {
        "adx": current_adx,
        "atr_pct": current_atr_pct,
        "donchian_high_prior": float(level_high) if pd.notna(level_high) else float("nan"),
        "donchian_low_prior": float(level_low) if pd.notna(level_low) else float("nan"),
    }

    volatility = Volatility.UNKNOWN
    if len(atr_pct_series.dropna()) >= vol_lookback:
        history = atr_pct_series.dropna().iloc[-vol_lookback:]
        percentile = float((history <= current_atr_pct).mean())
        metrics["atr_percentile"] = percentile
        if percentile >= vol_high_pctl:
            volatility = Volatility.HIGH
        elif percentile <= vol_low_pctl:
            volatility = Volatility.LOW
        else:
            volatility = Volatility.NORMAL

    # Priority: a confirmed breakout is the most specific, time-sensitive signal.
    if breakout_up:
        return RegimeSnapshot(Regime.BREAKOUT_UP, volatility, 1.0, metrics)
    if breakout_down:
        return RegimeSnapshot(Regime.BREAKOUT_DOWN, volatility, 1.0, metrics)

    if current_adx >= trend_threshold:
        sma_period = min(adx_period, len(close))
        direction_up = current_close >= close.iloc[-sma_period:].mean()
        confidence = min(1.0, (current_adx - trend_threshold) / trend_threshold + 0.5)
        regime = Regime.TREND_UP if direction_up else Regime.TREND_DOWN
        return RegimeSnapshot(regime, volatility, confidence, metrics)

    if current_adx <= range_threshold:
        confidence = min(1.0, (range_threshold - current_adx) / range_threshold + 0.5)
        return RegimeSnapshot(Regime.RANGE, volatility, confidence, metrics)

    # ADX sits in the ambiguous band between range_threshold and trend_threshold:
    # neither a confirmed trend nor a confirmed range. Saying so honestly, rather
    # than forcing a classification, is the point of having NO_EDGE at all.
    return RegimeSnapshot(Regime.NO_EDGE, volatility, 0.0, metrics)
