---
type: spec
tags: [trading-intelligence, paper-trading, risk-engine]
status: reference
aliases: ["Paper Trading Simulation Spec"]
---

# Paper Trading Simulation Specification — Trading Intelligence AI

> Author: Trading claude work
> Last updated: 2026-10-05
> Status: CANONICAL — Codex implements paper engine from this spec

## Purpose

Paper trading must be as realistic as possible. The goal is to discover problems
**before** real money is involved. If the paper simulation is too favorable,
it provides false confidence and the live transition will fail.

**The paper engine must be indistinguishable from the live engine in all behavior
except that it does not send orders to the real exchange.**

---

## Core Principle: Pessimistic Assumptions

When in doubt, assume worse execution:
- Slippage: model conservatively (err on the side of worse fills)
- Fees: use taker rate unless there's a documented reason for maker
- Partial fills: assume they happen at worst time (for limit orders)
- Latency: assume realistic API response times

---

## Fill Model

### Market Orders

```
Fill price = next_bar_open + slippage_component

slippage_component (BUY) = +entry_price * slippage_rate
slippage_component (SELL) = -entry_price * slippage_rate

Default slippage_rate: 0.0005 (5 basis points = 0.05%)

Fill is guaranteed at this price (market orders always fill in normal conditions).
Exception: if spread is unusually wide (> 10x normal), log WARNING and use spread midpoint + slippage.
```

### Limit Orders

```
Fill conditions (BUY limit at limit_price):
- Fill if bar_low <= limit_price
- Fill price: min(bar_open, limit_price)  ← conservative: fills at worse of open or limit
- No fill if bar_low > limit_price

Fill conditions (SELL limit at limit_price):
- Fill if bar_high >= limit_price
- Fill price: max(bar_open, limit_price)  ← conservative
- No fill if bar_high < limit_price

Partial fills:
- In paper mode: no partial fills (simplification)
- Either full fill or no fill
```

### Stop Orders (Stop-Loss)

```
Fill conditions (SELL stop at stop_price, for long position):
- Trigger if bar_low <= stop_price
- Fill price: stop_price - (stop_price * slippage_rate * 2)
  ← Stops gap through — add extra slippage on stop fills (gaps are common)

Fill conditions (BUY stop at stop_price, for short position):
- Trigger if bar_high >= stop_price
- Fill price: stop_price + (stop_price * slippage_rate * 2)

Gap handling:
- If bar_open gaps below stop_price (gap down): fill at bar_open (gapped through)
- Apply standard slippage to gap fills
- Log gap fills separately for analysis
```

---

## Fee Model — Binance Spot

```python
# Current Binance Spot fees (verify with live API on startup)
BINANCE_TAKER_FEE = 0.001   # 0.10%
BINANCE_MAKER_FEE = 0.001   # 0.10%

# BNB discount (when BNB balance available and BNB pay active)
BINANCE_BNB_DISCOUNT = 0.25  # 25% discount → effective 0.075%

# Default: use standard taker rate
# Market orders: taker
# Limit orders that take liquidity: taker
# Limit orders that add liquidity: maker (paper: assume taker for simplicity)

def calculate_fee(trade_value: float, fee_rate: float = BINANCE_TAKER_FEE) -> float:
    return trade_value * fee_rate
```

Fee is deducted from equity on every fill. Paper P&L is always fee-adjusted.

---

## Position Accounting

### Long Position
```
Entry:
  cost_basis = fill_price * quantity + entry_fee
  equity -= cost_basis  (equity reduced by cost)
  position = {symbol, quantity, avg_price, entry_fee}

Exit:
  proceeds = fill_price * quantity - exit_fee          # exit_fee already netted out here
  realized_pnl = proceeds - (entry_avg_price * quantity) - entry_fee
  equity += proceeds   # NOT (entry_avg_price*quantity) + realized_pnl — that
                       # double-subtracts entry_fee, since realized_pnl above
                       # already nets it out once. The entry cost was already
                       # fully debited from equity at Entry; nothing separate
                       # is "returned" at Exit beyond the sale's own proceeds.
                       # (Found as a real bug in trading_intelligence/execution/
                       # paper.py — fixed there; corrected here so it isn't
                       # re-implemented the same wrong way elsewhere.)
```

### Unrealized P&L (for risk calculations)
```
unrealized_pnl = (current_price - avg_entry_price) * quantity - estimated_exit_fee
equity_mark = cash + sum(position_value_at_current_price for all positions)
```

The risk engine uses `equity_mark` (marked-to-market) for:
- Daily loss limit calculation
- Drawdown calculation
- Position sizing

---

## Order Lifecycle

```
States:
  PENDING → SUBMITTED → FILLED | REJECTED | CANCELLED | EXPIRED

Transitions:
  PENDING: order created, awaiting next bar
  SUBMITTED: order passed risk engine, waiting for fill conditions
  FILLED: execution conditions met, position updated
  REJECTED: risk engine refused the order
  CANCELLED: order cancelled before fill
  EXPIRED: GTC order not filled within time_in_force window

Notes:
  - PAPER mode: orders execute at next bar (no intrabar execution simulation)
  - All orders are date-time stamped with both submission and fill times
  - Order IDs are UUIDs, not exchange IDs (paper)
```

---

## Timing Model

All execution uses the **next-bar model**:

```
Signal generated: at close of bar T
Order submitted: at close of bar T (passes risk engine)
Execution: at open of bar T+1 (fill at T+1 open ± slippage)

Rationale:
- Realistic: signal computed after bar closes, execution happens when market opens
- Prevents look-ahead bias from entering into live simulation
- Consistent with backtest methodology
```

---

## Daily Accounting

```
Day start (00:00 UTC):
- Record equity_at_day_start = current_equity_mark
- Reset daily_trade_count = 0
- Reset daily_turnover = 0
- Carry forward open positions

Day end (23:59 UTC):
- Record daily_pnl = equity_mark - equity_at_day_start
- Log daily summary: trades, fees paid, realized_pnl, unrealized_pnl, total_equity
- Update drawdown calculations
- Update Notion Metrics & Results (if connected)
```

---

## What Paper Mode Simulates

| Aspect | Simulated? | Notes |
|--------|-----------|-------|
| Fees | Yes | Taker rate always |
| Slippage | Yes | 5 bps default |
| Next-bar execution | Yes | No instant fills |
| Stop gap-through | Yes | Extra slippage on stops |
| Daily limits | Yes | Same as live engine |
| Kill switch | Yes | Same as live engine |
| Drawdown lock | Yes | Same as live engine |
| Position sizing | Yes | Same risk engine |
| Risk engine | Yes | Identical to live |

## What Paper Mode Does NOT Simulate

| Aspect | Not Simulated | Impact |
|--------|--------------|--------|
| Order book depth | Not simulated | Large orders may get better/worse fills than modeled |
| Market impact | Not simulated | Significant for larger positions |
| Funding rates | Not simulated (spot) | N/A for spot |
| Liquidation risk | Not simulated (spot) | N/A for spot |
| Exchange downtime | Not simulated | Real exchanges have maintenance windows |
| API rate limits | Not simulated | Real trading requires rate limit management |
| Partial fills | Not simulated | Simplified to full/no fill |

---

## Data Feeds in Paper Mode

Paper trading must use live market data (not historical replay) when running in real-time.

```
Live paper mode:
- Use real Binance WebSocket for price data
- Use real Binance REST API for OHLCV
- Execute paper fills based on real prices
- This simulates real-time performance without real money

Historical paper mode (replay):
- Use stored historical OHLCV data
- Useful for validating the paper engine matches backtest
- Must produce same results as backtest for same data
```

---

## State Persistence

Paper state must persist across restarts:

```
Persisted state (to disk/database):
- All open positions with entry details
- Daily P&L counter and start-of-day equity
- Drawdown peak equity
- Kill switch state
- Order history (last N days, configurable)
- Trade history (all completed trades)
- Daily summaries

On startup:
- Load persisted state
- Verify positions still valid against exchange (paper: accept as-is)
- Resume from last known state
- Log: SYSTEM_RESUMED with state summary
```

If state file is missing or corrupted on startup:
- Log ERROR
- Do NOT auto-start trading
- Require operator acknowledgment to start fresh

---

## Metrics Computed Continuously

```python
# Updated after every trade close
metrics = {
    "total_trades": int,
    "winning_trades": int,
    "losing_trades": int,
    "win_rate": float,  # winning_trades / total_trades
    "avg_win": float,   # average P&L of winning trades (after fees)
    "avg_loss": float,  # average P&L of losing trades (after fees)
    "payoff_ratio": float,  # avg_win / abs(avg_loss)
    "profit_factor": float,  # sum(wins) / abs(sum(losses))
    "expectancy": float,     # avg P&L per trade after fees
    "total_pnl": float,      # total realized + unrealized
    "total_fees_paid": float,
    "max_drawdown": float,   # worst drawdown since start
    "current_drawdown": float,
    "equity_curve": list,    # daily equity snapshots
    "sharpe_ratio": float,   # computed over daily returns (requires ≥30 days)
    "sortino_ratio": float,
}
```

---

## Implementation Notes for Codex

- `PaperExecutionEngine` is a class with the same interface as `LiveExecutionEngine`
- Both inherit from `AbstractExecutionEngine` — strategy layer never knows which one is running
- The only configuration difference: `mode = "paper" | "live"`
- Paper engine does not instantiate any real HTTP client to exchange
- Paper engine uses the same `RiskEngine` instance as live engine
- Paper engine maintains its own internal order book and position tracking
- Tests: run backtest on known historical data, compare to paper engine on same data replay
