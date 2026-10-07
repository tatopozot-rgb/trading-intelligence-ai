"""
Pure indicator functions. No state, no side effects.
All functions accept a pd.Series or pd.DataFrame and return a pd.Series.
"""
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


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average Directional Index (Wilder). Measures trend STRENGTH, not direction —
    high ADX means a strong trend (either way), low ADX means ranging/choppy price."""
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index)
    tr = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1
    ).max(axis=1)
    smoothed_tr = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    smoothed_plus_dm = plus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    smoothed_minus_dm = minus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    plus_di = 100 * smoothed_plus_dm / smoothed_tr
    minus_di = 100 * smoothed_minus_dm / smoothed_tr
    di_sum = plus_di + minus_di
    # Both DIs zero (no directional movement at all, e.g. a flat price) -> DX undefined; treat as 0, not NaN.
    dx = np.where(di_sum == 0, 0.0, 100 * (plus_di - minus_di).abs() / di_sum)
    return pd.Series(dx, index=high.index).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


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


def bollinger_bands(
    close: pd.Series, period: int = 20, num_std: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Bollinger Bands: (middle, upper, lower).
    Middle = SMA(period). Bands = middle +/- num_std * rolling std (population,
    ddof=0, the standard Bollinger convention).
    """
    if period < 2:
        raise ValueError(f"period must be >= 2, got {period}")
    if num_std <= 0:
        raise ValueError(f"num_std must be > 0, got {num_std}")
    middle = sma(close, period)
    std = close.rolling(window=period, min_periods=period).std(ddof=0)
    upper = middle + num_std * std
    lower = middle - num_std * std
    return middle, upper, lower


def above_ma_filter(close: pd.Series, period: int, ma_type: Literal["sma", "ema"] = "sma") -> pd.Series:
    """
    Returns a boolean series: True when price is above the MA.
    Used as a regime/trend filter to suppress counter-trend signals.
    """
    calc = sma if ma_type == "sma" else ema
    ma = calc(close, period)
    return close > ma
