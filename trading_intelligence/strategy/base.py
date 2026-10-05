"""Abstract base class for all trading strategies."""
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional

import pandas as pd

from trading_intelligence.strategy.models import TradeProposal


class AbstractStrategy(ABC):
    """
    Every strategy implements on_bar() and produces a TradeProposal or None.

    Strategies do NOT size positions — that is the risk engine's job.
    Strategies MUST always provide a stop_price with any proposal.
    """

    def __init__(self, strategy_id: str, symbol: str, timeframe: str, params: dict):
        self.strategy_id = strategy_id
        self.symbol = symbol
        self.timeframe = timeframe
        self.params = params

    @abstractmethod
    def on_bar(self, data: pd.DataFrame) -> Optional[TradeProposal]:
        """
        Called on each new completed bar.

        Args:
            data: OHLCV DataFrame with columns [open, high, low, close, volume].
                  Index is DatetimeIndex. All bars up to and including the current one.

        Returns:
            TradeProposal if a signal is generated, None otherwise.
        """
        ...

    @abstractmethod
    def on_exit_signal(self, data: pd.DataFrame, entry_price: Decimal) -> bool:
        """
        Called to check if an open position should be exited.

        Returns True to exit the position.
        """
        ...

    def validate_params(self) -> None:
        """Override to add strategy-specific parameter validation."""
