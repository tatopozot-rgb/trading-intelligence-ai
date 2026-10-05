"""
Vectorized event-driven backtest engine.

Implements the next-bar execution model from PAPER_TRADING_SIMULATION_SPEC.md:
  - Signal generated at bar T close
  - Order fills at bar T+1 open ± slippage
  - Stop losses evaluated at bar T+1 first (gap-through risk at 2× slippage)
  - Fees: Binance taker 0.1% per side

One position at a time per strategy instance (spot, long-only).
Position sizing uses fixed fractional risk (1% of equity by default) — mirrors
RiskEngine logic so backtests match live paper behavior.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from typing import Optional

import pandas as pd
import numpy as np

from trading_intelligence.strategy.base import AbstractStrategy
from trading_intelligence.strategy.models import TradeProposal

logger = logging.getLogger(__name__)

TAKER_FEE = Decimal("0.001")   # 0.10% Binance taker
SLIPPAGE_BPS = Decimal("5")    # 5 basis points one-way
SLIPPAGE_FACTOR = SLIPPAGE_BPS / Decimal("10000")

# Position sizing
DEFAULT_RISK_PCT = Decimal("1.0")   # 1% equity per trade


@dataclass
class BacktestTrade:
    symbol: str
    strategy_id: str
    entry_bar: int
    entry_time: pd.Timestamp
    entry_price: Decimal
    quantity: Decimal
    stop_price: Decimal
    target_price: Optional[Decimal]
    exit_bar: Optional[int] = None
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[Decimal] = None
    exit_reason: Optional[str] = None  # "stop", "signal", "end_of_data"
    entry_fee: Decimal = Decimal("0")
    exit_fee: Decimal = Decimal("0")

    @property
    def pnl(self) -> Decimal:
        if self.exit_price is None:
            return Decimal("0")
        gross = (self.exit_price - self.entry_price) * self.quantity
        return gross - self.entry_fee - self.exit_fee

    @property
    def return_pct(self) -> float:
        cost = float(self.entry_price * self.quantity + self.entry_fee)
        if cost == 0:
            return 0.0
        return float(self.pnl) / cost


@dataclass
class BacktestResult:
    trades: list[BacktestTrade]
    equity_curve: pd.Series
    initial_equity: Decimal
    final_equity: Decimal

    # Summary stats (populated by compute_metrics)
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: Decimal = Decimal("0")
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    total_fees: Decimal = Decimal("0")

    def compute_metrics(self) -> None:
        closed = [t for t in self.trades if t.exit_price is not None]
        self.total_trades = len(closed)
        if not closed:
            return

        pnls = [float(t.pnl) for t in closed]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        self.winning_trades = len(wins)
        self.losing_trades = len(losses)
        self.total_pnl = sum((t.pnl for t in closed), Decimal("0"))
        self.total_fees = sum((t.entry_fee + t.exit_fee for t in closed), Decimal("0"))
        self.win_rate = self.winning_trades / self.total_trades if self.total_trades else 0.0
        self.avg_win = sum(wins) / len(wins) if wins else 0.0
        self.avg_loss = sum(losses) / len(losses) if losses else 0.0

        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0
        self.profit_factor = gross_profit / gross_loss if gross_loss else float("inf")

        # Sharpe from daily equity returns (annualized, 365 days for crypto)
        daily_returns = self.equity_curve.pct_change().dropna()
        if len(daily_returns) > 1 and daily_returns.std() > 0:
            self.sharpe_ratio = (
                daily_returns.mean() / daily_returns.std() * np.sqrt(365)
            )

        # Max drawdown
        eq = self.equity_curve
        peak = eq.expanding().max()
        drawdown = (eq - peak) / peak
        self.max_drawdown_pct = float(drawdown.min()) * 100  # negative number

    def summary(self) -> str:
        return (
            f"Trades: {self.total_trades} | Win rate: {self.win_rate:.1%} | "
            f"PF: {self.profit_factor:.2f} | Sharpe: {self.sharpe_ratio:.2f} | "
            f"Max DD: {self.max_drawdown_pct:.1f}% | "
            f"Total PnL: {self.total_pnl:.2f} | Fees: {self.total_fees:.2f}"
        )


class BacktestEngine:
    """
    Runs a single strategy on OHLCV data bar by bar.

    Usage:
        engine = BacktestEngine(strategy, initial_equity=Decimal("10000"))
        result = engine.run(ohlcv_df)
        result.compute_metrics()
        print(result.summary())
    """

    def __init__(
        self,
        strategy: AbstractStrategy,
        initial_equity: Decimal = Decimal("10000"),
        risk_pct: Decimal = DEFAULT_RISK_PCT,
        taker_fee: Decimal = TAKER_FEE,
        slippage_factor: Decimal = SLIPPAGE_FACTOR,
    ):
        self.strategy = strategy
        self.initial_equity = initial_equity
        self.risk_pct = risk_pct
        self.taker_fee = taker_fee
        self.slippage_factor = slippage_factor

    def run(self, data: pd.DataFrame) -> BacktestResult:
        """
        Run backtest on OHLCV data.

        Args:
            data: DataFrame with columns [open, high, low, close, volume],
                  DatetimeIndex, already sorted ascending, no NaN in OHLCV.

        Returns:
            BacktestResult with all trades and equity curve.
        """
        if not isinstance(data.index, pd.DatetimeIndex):
            raise ValueError("data must have DatetimeIndex")
        required_cols = {"open", "high", "low", "close", "volume"}
        missing = required_cols - set(data.columns)
        if missing:
            raise ValueError(f"data missing columns: {missing}")

        equity = self.initial_equity
        equity_history: list[tuple[pd.Timestamp, float]] = []
        trades: list[BacktestTrade] = []
        open_trade: Optional[BacktestTrade] = None

        for i in range(1, len(data)):
            current_bar = data.iloc[i]
            bar_time = data.index[i]
            historical = data.iloc[: i + 1]  # up to and including current bar

            # --- Check if pending entry fills this bar (signal was last bar) ---
            if open_trade is None and trades and trades[-1].exit_price is None:
                # Should not happen with our logic, but guard anyway
                pass

            # --- Evaluate open position at this bar's open ---
            if open_trade is not None:
                open_bar_open = Decimal(str(current_bar["open"]))
                open_bar_high = Decimal(str(current_bar["high"]))
                open_bar_low = Decimal(str(current_bar["low"]))

                # Stop hit? Check low vs stop (gap-through: 2× slippage)
                if open_bar_low <= open_trade.stop_price:
                    fill_price = self._stop_fill_price(open_trade.stop_price)
                    open_trade = self._close_trade(
                        open_trade, i, bar_time, fill_price, "stop", equity
                    )
                    equity += open_trade.pnl
                    trades[-1] = open_trade
                    open_trade = None

            # Signal generation: pass all bars up to i (inclusive) but signal
            # fires at bar i close, will fill at bar i+1 open (next iteration)
            if open_trade is None:
                proposal = self.strategy.on_bar(historical)
                if proposal is not None:
                    # Will fill on NEXT bar open — store as "pending" for next iteration
                    next_bar_idx = i + 1
                    if next_bar_idx >= len(data):
                        break  # no next bar to fill
                    next_bar = data.iloc[next_bar_idx]
                    fill_price = Decimal(str(next_bar["open"])) * (1 + self.slippage_factor)
                    qty = self._size_position(equity, fill_price, proposal.stop_price)
                    if qty <= 0:
                        continue
                    entry_fee = fill_price * qty * self.taker_fee
                    equity -= entry_fee  # deduct fee at entry

                    trade = BacktestTrade(
                        symbol=proposal.symbol,
                        strategy_id=proposal.strategy_id,
                        entry_bar=next_bar_idx,
                        entry_time=data.index[next_bar_idx],
                        entry_price=fill_price,
                        quantity=qty,
                        stop_price=proposal.stop_price,
                        target_price=proposal.target_price,
                        entry_fee=entry_fee,
                    )
                    trades.append(trade)
                    open_trade = trade
                    i_skip = next_bar_idx  # will be processed next loop naturally

            elif open_trade is not None:
                # Check exit signal on open position
                if self.strategy.on_exit_signal(historical, open_trade.entry_price):
                    next_bar_idx = i + 1
                    if next_bar_idx < len(data):
                        next_bar = data.iloc[next_bar_idx]
                        fill_price = Decimal(str(next_bar["open"])) * (1 - self.slippage_factor)
                    else:
                        fill_price = Decimal(str(current_bar["close"])) * (1 - self.slippage_factor)
                    open_trade = self._close_trade(
                        open_trade, i + 1, data.index[min(i + 1, len(data) - 1)],
                        fill_price, "signal", equity,
                    )
                    equity += open_trade.pnl
                    trades[-1] = open_trade
                    open_trade = None

            equity_history.append((bar_time, float(equity)))

        # Close any open trade at last bar
        if open_trade is not None:
            last_close = Decimal(str(data.iloc[-1]["close"]))
            open_trade = self._close_trade(
                open_trade, len(data) - 1, data.index[-1], last_close, "end_of_data", equity
            )
            equity += open_trade.pnl
            trades[-1] = open_trade

        equity_curve = pd.Series(
            {t: v for t, v in equity_history}, dtype=float, name="equity"
        )
        return BacktestResult(
            trades=trades,
            equity_curve=equity_curve,
            initial_equity=self.initial_equity,
            final_equity=equity,
        )

    def _size_position(
        self, equity: Decimal, entry_price: Decimal, stop_price: Decimal
    ) -> Decimal:
        """Fixed fractional position sizing (mirrors RiskEngine logic)."""
        risk_amount = equity * (self.risk_pct / Decimal("100"))
        stop_distance = (entry_price - stop_price) / entry_price
        round_trip_fees = 2 * self.taker_fee
        effective_stop = stop_distance + round_trip_fees
        if effective_stop <= 0:
            return Decimal("0")
        qty = risk_amount / (entry_price * effective_stop)
        # Truncate to 8 decimal places (BTC precision)
        return qty.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)

    def _stop_fill_price(self, stop_price: Decimal) -> Decimal:
        """Stop fill with 2× slippage (gap-through model)."""
        return stop_price * (1 - 2 * self.slippage_factor)

    @staticmethod
    def _close_trade(
        trade: BacktestTrade,
        exit_bar: int,
        exit_time: pd.Timestamp,
        fill_price: Decimal,
        reason: str,
        equity: Decimal,
    ) -> BacktestTrade:
        fee = fill_price * trade.quantity * TAKER_FEE
        trade.exit_bar = exit_bar
        trade.exit_time = exit_time
        trade.exit_price = fill_price
        trade.exit_reason = reason
        trade.exit_fee = fee
        return trade
