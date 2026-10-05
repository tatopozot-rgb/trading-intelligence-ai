"""
Dual Moving Average Crossover Strategy — Candidate 1.

Long-only (Binance Spot). Entry on fast MA crosses above slow MA, when price
is above the long-term trend filter MA. Exit on fast MA crosses below slow MA.

Stop: placed at the most recent swing low (lowest low of the last `stop_lookback` bars).
"""
import logging
from decimal import Decimal
from typing import Literal, Optional

import pandas as pd

from trading_intelligence.analysis.indicators import (
    above_ma_filter,
    ema,
    ma_crossover_signal,
    sma,
)
from trading_intelligence.strategy.base import AbstractStrategy
from trading_intelligence.strategy.models import TradeProposal

logger = logging.getLogger(__name__)

_DEFAULT_PARAMS = {
    "fast_period": 20,
    "slow_period": 50,
    "ma_type": "ema",           # "sma" or "ema"
    "trend_filter_period": 200, # 0 to disable
    "trend_filter_ma_type": "sma",
    "stop_lookback": 10,        # bars to look back for swing low stop
    "min_bars_required": 220,   # warmup period
}


class DualMACrossover(AbstractStrategy):
    """
    Dual Moving Average Crossover — long only, with optional trend filter.

    Parameters (all optional, see _DEFAULT_PARAMS for defaults):
        fast_period: int
        slow_period: int
        ma_type: "sma" | "ema"
        trend_filter_period: int (0 to disable)
        trend_filter_ma_type: "sma" | "ema"
        stop_lookback: int
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
            strategy_id=strategy_id or f"ma_crossover_{symbol}_{timeframe}",
            symbol=symbol,
            timeframe=timeframe,
            params=merged,
        )
        self.validate_params()

    def validate_params(self) -> None:
        p = self.params
        if p["fast_period"] >= p["slow_period"]:
            raise ValueError(
                f"fast_period ({p['fast_period']}) must be < slow_period ({p['slow_period']})"
            )
        if p["ma_type"] not in ("sma", "ema"):
            raise ValueError(f"ma_type must be 'sma' or 'ema', got '{p['ma_type']}'")
        if p["stop_lookback"] < 1:
            raise ValueError("stop_lookback must be >= 1")

    def on_bar(self, data: pd.DataFrame) -> Optional[TradeProposal]:
        """
        Generate a BUY proposal when fast MA crosses above slow MA and trend
        filter is satisfied. Returns None if no signal or filter rejects.
        """
        p = self.params
        min_required = max(
            p["slow_period"],
            p.get("trend_filter_period", 0) or 0,
            p["stop_lookback"],
        ) + 2  # +2 for crossover diff() to work

        if len(data) < min_required:
            return None

        close = data["close"]
        signal = ma_crossover_signal(close, p["fast_period"], p["slow_period"], p["ma_type"])

        # Most recent bar (index -1): was there a bullish crossover?
        if signal.iloc[-1] != 1:
            return None

        # Trend filter: only enter longs when price is above long-term MA
        if p.get("trend_filter_period"):
            trend_ok = above_ma_filter(
                close, p["trend_filter_period"], p["trend_filter_ma_type"]
            )
            if not trend_ok.iloc[-1]:
                logger.debug(
                    "%s: MA crossover signal suppressed — price below %d-bar trend filter",
                    self.symbol,
                    p["trend_filter_period"],
                )
                return None

        entry_price = Decimal(str(close.iloc[-1]))
        stop_price = self._swing_low_stop(data["low"], p["stop_lookback"])

        if stop_price >= entry_price:
            logger.warning(
                "%s: swing-low stop %s >= entry %s — skipping signal",
                self.symbol, stop_price, entry_price,
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
                f"Fast {p['ma_type'].upper()}({p['fast_period']}) crossed above "
                f"slow {p['ma_type'].upper()}({p['slow_period']})"
            ),
            signal_strength=1.0,
            timestamp=str(data.index[-1]),
        )

    def on_exit_signal(self, data: pd.DataFrame, entry_price: Decimal) -> bool:
        """Exit when fast MA crosses below slow MA."""
        p = self.params
        if len(data) < p["slow_period"] + 2:
            return False
        close = data["close"]
        signal = ma_crossover_signal(close, p["fast_period"], p["slow_period"], p["ma_type"])
        return bool(signal.iloc[-1] == -1)

    @staticmethod
    def _swing_low_stop(low: pd.Series, lookback: int) -> Decimal:
        """Stop at the lowest low over the last `lookback` bars (excluding current bar)."""
        window = low.iloc[-(lookback + 1):-1]
        return Decimal(str(window.min()))
