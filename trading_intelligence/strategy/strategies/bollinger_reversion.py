"""
Bollinger Band Mean-Reversion Strategy — Candidate 2, built for Regime.RANGE.

Long-only (Binance Spot). Entry when price closes below the lower Bollinger
Band (oversold stretch) and then closes back above it on a later bar (the
reversion has actually started, not just assumed), confirmed by RSI being
in oversold territory at that bar (filters out noise-only band touches).
Exit when price reverts back to the middle band (SMA) or RSI recovers past
its exit threshold — whichever comes first.

The oversold condition (close below the lower band AND RSI below
rsi_oversold) and the reversion confirmation (close back above the lower
band) do not have to land on consecutive bars — `confirm_lookback` allows
the oversold condition to have occurred up to that many bars before the
confirming bar. A genuine mean-reversion dip is rarely a single clean bar;
requiring the two conditions on exactly adjacent bars missed real setups
where price sat below the band for 2-3 bars before confirming (verified
directly against synthetic data before fixing this: the single-bar version
produced only 3 signals across 4 years of realistic daily data, the same
"check why before accepting a near-zero count" discipline this project's
BacktestEngine/StrategyRouter calibration gap (CHECKPOINT.md section 22)
used — a structural entry-timing fix decided before looking at any
performance/Sharpe number, not a post-hoc tuning pass).

This is a mean-reversion approach, the opposite assumption of
DualMACrossover's trend-following: it expects price to revert toward its
recent average rather than continue. It is designed for ranging markets
(see trading_intelligence/regime/detector.py's Regime.RANGE) and is NOT
intended to run outside a regime filter — a real trend will blow through
the lower band repeatedly without reverting, which is exactly what the
router's regime gating exists to prevent this strategy from seeing.

Stop: ATR-based, placed below entry by `stop_atr_mult` * ATR(stop_atr_period)
at the signal bar — a swing-low lookback (as DualMACrossover uses) is less
appropriate here, since a mean-reversion entry's swing low is often the
oversold extreme itself, which would place the stop uncomfortably close to
the entry on a thin bounce.
"""
import logging
from decimal import Decimal
from typing import Optional

import pandas as pd

from trading_intelligence.analysis.indicators import atr, bollinger_bands, rsi
from trading_intelligence.strategy.base import AbstractStrategy
from trading_intelligence.strategy.models import TradeProposal

logger = logging.getLogger(__name__)

_DEFAULT_PARAMS = {
    "bb_period": 20,
    "bb_std": 2.0,
    "rsi_period": 14,
    "rsi_oversold": 30.0,     # entry confirmation: RSI must be below this
    "rsi_exit": 50.0,         # exit confirmation: RSI recovering past this also exits
    "stop_atr_period": 14,
    "stop_atr_mult": 1.5,
    "confirm_lookback": 5,    # bars before the current one the oversold condition may have occurred
    "min_bars_required": 40,  # warmup period
}


class BollingerReversion(AbstractStrategy):
    """
    Bollinger Band mean-reversion — long only.

    Parameters (all optional, see _DEFAULT_PARAMS for defaults):
        bb_period: int
        bb_std: float
        rsi_period: int
        rsi_oversold: float   (0-100, entry filter)
        rsi_exit: float       (0-100, exit filter; must be > rsi_oversold)
        stop_atr_period: int
        stop_atr_mult: float
    """

    def __init__(
        self,
        symbol: str,
        timeframe: str,
        params: Optional[dict] = None,
        strategy_id: Optional[str] = None,
    ):
        merged = {**_DEFAULT_PARAMS, **(params or {})}
        super().__init__(
            strategy_id=strategy_id or f"bollinger_reversion_{symbol}_{timeframe}",
            symbol=symbol,
            timeframe=timeframe,
            params=merged,
        )
        self.validate_params()

    def validate_params(self) -> None:
        p = self.params
        if p["bb_period"] < 2:
            raise ValueError(f"bb_period must be >= 2, got {p['bb_period']}")
        if p["bb_std"] <= 0:
            raise ValueError(f"bb_std must be > 0, got {p['bb_std']}")
        if p["rsi_period"] < 2:
            raise ValueError(f"rsi_period must be >= 2, got {p['rsi_period']}")
        if not 0 < p["rsi_oversold"] < p["rsi_exit"] < 100:
            raise ValueError(
                f"require 0 < rsi_oversold ({p['rsi_oversold']}) < rsi_exit "
                f"({p['rsi_exit']}) < 100"
            )
        if p["stop_atr_mult"] <= 0:
            raise ValueError(f"stop_atr_mult must be > 0, got {p['stop_atr_mult']}")
        if p["confirm_lookback"] < 1:
            raise ValueError(f"confirm_lookback must be >= 1, got {p['confirm_lookback']}")

    def on_bar(self, data: pd.DataFrame) -> Optional[TradeProposal]:
        """
        Generate a BUY proposal when price closed below the lower Bollinger
        Band with RSI confirming oversold at some bar within the last
        `confirm_lookback` bars, and has now closed back above the lower
        band (reversion confirmed). Returns None if no signal or data is
        insufficient.
        """
        p = self.params
        lookback = p["confirm_lookback"]
        min_required = max(p["bb_period"], p["rsi_period"], p["stop_atr_period"]) + lookback + 2
        if len(data) < min_required:
            return None

        close = data["close"]
        _, _, lower = bollinger_bands(close, p["bb_period"], p["bb_std"])
        rsi_series = rsi(close, p["rsi_period"])

        current_close = close.iloc[-1]
        current_lower = lower.iloc[-1]

        if pd.isna(current_lower):
            return None

        window_close = close.iloc[-(lookback + 1):-1]
        window_lower = lower.iloc[-(lookback + 1):-1]
        window_rsi = rsi_series.iloc[-(lookback + 1):-1]
        was_oversold_recently = bool(
            ((window_close < window_lower) & (window_rsi < p["rsi_oversold"])).any()
        )
        reverting_now = current_close >= current_lower

        if not (was_oversold_recently and reverting_now):
            return None

        entry_price = Decimal(str(current_close))
        stop_price = self._atr_stop(data, entry_price)
        if stop_price is None or stop_price >= entry_price or stop_price <= 0:
            logger.warning(
                "%s: invalid ATR stop for entry %s — skipping signal",
                self.symbol, entry_price,
            )
            return None

        return TradeProposal(
            strategy_id=self.strategy_id,
            symbol=self.symbol,
            side="BUY",
            entry_type="MARKET",
            stop_price=stop_price,
            timeframe=self.timeframe,
            rationale=(
                f"Close reverted above lower Bollinger Band "
                f"({p['bb_period']}, {p['bb_std']}σ) after an RSI-confirmed "
                f"oversold close (RSI < {p['rsi_oversold']}) within the last "
                f"{lookback} bars"
            ),
            signal_strength=1.0,
            timestamp=str(data.index[-1]),
        )

    def on_exit_signal(self, data: pd.DataFrame, entry_price: Decimal) -> bool:
        """Exit when price reverts to the middle band (SMA) or RSI recovers
        past rsi_exit — the reversion thesis has played out either way."""
        p = self.params
        if len(data) < p["bb_period"] + 2:
            return False
        close = data["close"]
        middle, _, _ = bollinger_bands(close, p["bb_period"], p["bb_std"])
        rsi_series = rsi(close, p["rsi_period"])

        current_close = close.iloc[-1]
        current_middle = middle.iloc[-1]
        current_rsi = rsi_series.iloc[-1]

        if pd.isna(current_middle):
            return False

        reverted_to_mean = current_close >= current_middle
        rsi_recovered = pd.notna(current_rsi) and current_rsi >= p["rsi_exit"]
        return bool(reverted_to_mean or rsi_recovered)

    def _atr_stop(self, data: pd.DataFrame, entry_price: Decimal) -> Optional[Decimal]:
        p = self.params
        atr_series = atr(data["high"], data["low"], data["close"], period=p["stop_atr_period"])
        current_atr = atr_series.iloc[-1]
        if pd.isna(current_atr):
            return None
        stop_distance = Decimal(str(current_atr)) * Decimal(str(p["stop_atr_mult"]))
        return entry_price - stop_distance
