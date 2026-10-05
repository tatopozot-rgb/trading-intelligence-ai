"""
Pure indicator functions. No state, no side effects.
All functions accept a pd.Series or pd.DataFrame and return a pd.Series.
"""
from decimal import Decimal
from typing import Literal

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple moving average."""
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average (Wilder-style span = 2*period-1 not used; standard EMA)."""
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range."""
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder smoothing)."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    # When avg_loss is 0 (all gains): RSI = 100. Avoid 0/0 → NaN.
    rsi_vals = np.where(
        avg_loss == 0,
        100.0,
        100 - (100 / (1 + avg_gain / avg_loss)),
    )
    return pd.Series(rsi_vals, index=series.index)


def roc(series: pd.Series, period: int = 10) -> pd.Series:
    """Rate of Change as a decimal fraction (not percentage)."""
    return (series - series.shift(period)) / series.shift(period)


def donchian_high(series: pd.Series, period: int) -> pd.Series:
    """N-period rolling high (Donchian channel upper band)."""
    return series.rolling(window=period, min_periods=period).max()


def donchian_low(series: pd.Series, period: int) -> pd.Series:
    """N-period rolling low (Donchian channel lower band)."""
    return series.rolling(window=period, min_periods=period).min()


def ma_crossover_signal(
    close: pd.Series,
    fast_period: int,
    slow_period: int,
    ma_type: Literal["sma", "ema"] = "ema",
) -> pd.Series:
    """
    Returns a signal series:
      +1  = fast crossed above slow (bullish crossover)
      -1  = fast crossed below slow (bearish crossover)
       0  = no crossover this bar
    """
    if fast_period >= slow_period:
        raise ValueError(
            f"fast_period ({fast_period}) must be < slow_period ({slow_period})"
        )

    calc = sma if ma_type == "sma" else ema
    fast = calc(close, fast_period)
    slow = calc(close, slow_period)

    above = (fast > slow).astype(int)
    signal = above.diff()
    # diff() of 0/1 int: +1 = just crossed above, -1 = just crossed below
    return signal.fillna(0).astype(int)


def above_ma_filter(close: pd.Series, period: int, ma_type: Literal["sma", "ema"] = "sma") -> pd.Series:
    """
    Returns a boolean series: True when price is above the MA.
    Used as a regime/trend filter to suppress counter-trend signals.
    """
    calc = sma if ma_type == "sma" else ema
    ma = calc(close, period)
    return close > ma
