---
type: spec
tags: [trading-intelligence, risk-engine]
status: reference
aliases: ["Risk Engine Spec"]
---

# Risk Engine Specification — Trading Intelligence AI

> Author: Trading claude work
> Last updated: 2026-10-05
> Status: CANONICAL — Codex implements from this spec

## Purpose

This document is the authoritative specification for the deterministic risk engine.
**Claude cannot override the risk engine. The risk engine has veto on every order.**

The risk engine is not an advisory layer. It is a hard gate. Every trade instruction
from any source — signal, manual, AI recommendation — must pass through it.
Rejection is normal and expected behavior, not an error.

---

## Architecture Principles

1. **Deterministic**: Same inputs always produce same output. No randomness, no ML.
2. **Non-bypassable**: There is no override path, no "force" flag, no emergency bypass.
3. **Immutable audit log**: Every decision (approve/reject) is logged with full context.
4. **Stateful**: The engine maintains running state (open P&L, daily loss, drawdown, position count).
5. **Fail-safe**: On any uncertainty, the engine rejects. "When in doubt, do not trade."
6. **Synchronous**: Order validation is synchronous — no fire-and-forget.

---

## Risk Parameters (Configurable, Not Hardcoded)

All parameters live in a config file or environment. Defaults below are starting points.
Parameters must be validated at startup. Invalid parameters = system refuses to run.

```yaml
risk:
  # Per-trade risk
  max_risk_per_trade_pct: 1.0        # % of current equity risked per trade
  max_position_size_pct: 5.0         # % of equity in single position (regardless of stop)

  # Daily limits
  daily_loss_limit_pct: 2.0          # % daily loss → halt trading for the day
  max_trades_per_day: 20             # maximum new positions opened per day
  max_daily_turnover_pct: 30.0       # max % of equity turned over in a day

  # Drawdown controls
  drawdown_pause_pct: 8.0            # % drawdown from equity peak → pause new trades
  drawdown_halt_pct: 15.0            # % drawdown from equity peak → hard stop
  drawdown_lookback_days: 30         # rolling window for peak calculation

  # Portfolio-level
  max_open_positions: 5              # simultaneous open positions
  max_correlated_exposure_pct: 10.0  # max combined exposure in correlated assets
  max_total_exposure_pct: 20.0       # max % of equity in all open positions combined

  # Execution model
  default_slippage_bps: 5            # basis points of slippage to assume
  include_fees_in_risk_calc: true    # fees reduce effective position sizing

  # Kill switch
  kill_switch_active: false          # set true to halt ALL new orders immediately
```

---

## Position Sizing Method

**Method: Fixed Fractional Risk**

Given:
- `equity` = current account equity (in base currency)
- `risk_pct` = `max_risk_per_trade_pct` (default 1.0%)
- `entry_price` = intended entry
- `stop_price` = stop loss price (REQUIRED — no stop, no trade)
- `fee_rate` = exchange fee (e.g. 0.001 for 0.1%)

```
risk_amount = equity * (risk_pct / 100)
stop_distance_pct = |entry_price - stop_price| / entry_price
effective_stop_distance = stop_distance_pct + (2 * fee_rate)  # round-trip fees
position_size_in_base = risk_amount / (entry_price * effective_stop_distance)
position_value = position_size_in_base * entry_price
```

**Hard caps applied after sizing:**
1. `position_value <= equity * (max_position_size_pct / 100)`
2. `position_value + total_open_exposure <= equity * (max_total_exposure_pct / 100)`
3. Result is floored to exchange's minimum lot/quantity

**No stop = order rejected.** There is no market order without a stop loss defined.

---

## Daily Loss Limit

```
daily_pnl = realized_pnl_today + unrealized_pnl_all_open_positions
daily_loss_pct = daily_pnl / equity_at_day_start * 100

if daily_pnl < 0 and abs(daily_loss_pct) >= daily_loss_limit_pct:
    → HALT: no new positions for remainder of calendar day
    → Existing positions: managed normally (stops, targets active)
    → Kill switch: NOT automatically activated (existing trades continue)
    → Log: DAILY_LOSS_LIMIT_REACHED
    → Notify: operator notification triggered
```

Reset: at start of next calendar day (00:00 UTC), daily counters reset automatically.

---

## Drawdown Lock

```
equity_peak = max(equity over lookback window)
current_drawdown_pct = (equity_peak - current_equity) / equity_peak * 100

if current_drawdown_pct >= drawdown_halt_pct:
    → HARD STOP: kill switch activated automatically
    → All new orders rejected
    → Manual reset required (operator must explicitly clear)
    → Log: DRAWDOWN_HALT_TRIGGERED

elif current_drawdown_pct >= drawdown_pause_pct:
    → PAUSE: no new positions
    → Existing positions continue normally
    → Auto-resumes when drawdown recovers below pause threshold
    → Log: DRAWDOWN_PAUSE_TRIGGERED
```

---

## Kill Switch

The kill switch is a boolean flag that can be set by:
1. **Operator/owner** explicitly at any time
2. **Automatically** by drawdown halt trigger
3. **Automatically** on exchange connectivity failure > 60 seconds
4. **Automatically** on data feed staleness > configured threshold

When active:
- All new order requests are rejected immediately
- No positions are closed automatically (closing is manual or via existing stops)
- Kill switch state is persisted to disk — survives restart
- Clearing requires explicit manual operator action
- Every rejection logged with `KILL_SWITCH_ACTIVE`

---

## Order Validation Flow

Every order passes this exact sequence. First failure = rejection with reason code.

```
validate_order(order) -> (approved: bool, reason: str)

1. CHECK kill_switch → if active: REJECT(KILL_SWITCH_ACTIVE)
2. CHECK trading_day_halted → if true: REJECT(DAILY_LOSS_LIMIT_REACHED)
3. CHECK drawdown_paused → if true: REJECT(DRAWDOWN_PAUSE_ACTIVE)
4. CHECK order has stop_loss → if missing: REJECT(NO_STOP_LOSS_DEFINED)
5. CHECK stop_loss is valid → stop distance > minimum_viable_distance: else REJECT(STOP_TOO_TIGHT)
6. CALCULATE position_size via fixed fractional method
7. CHECK position_size > 0 → else REJECT(POSITION_SIZE_ZERO)
8. CHECK open_positions < max_open_positions → else REJECT(MAX_POSITIONS_REACHED)
9. CHECK daily_trade_count < max_trades_per_day → else REJECT(DAILY_TRADE_LIMIT_REACHED)
10. CHECK new total_exposure <= max_total_exposure_pct → else REJECT(EXPOSURE_LIMIT_EXCEEDED)
11. CHECK correlated exposure within limits → else REJECT(CORRELATED_EXPOSURE_EXCEEDED)
12. APPROVE → return (True, "OK") with calculated position_size
```

The order object returned after approval includes the engine-calculated `position_size`.
The caller MUST use this size. Using a different size = protocol violation.

---

## Audit Log

Every risk engine decision — approve or reject — emits a structured log entry:

```json
{
  "timestamp": "ISO-8601",
  "event": "RISK_DECISION",
  "decision": "APPROVED|REJECTED",
  "reason": "OK|KILL_SWITCH_ACTIVE|NO_STOP_LOSS_DEFINED|...",
  "order_id": "uuid",
  "symbol": "BTCUSDT",
  "side": "BUY|SELL",
  "requested_quantity": 0.001,
  "approved_quantity": 0.001,
  "entry_price": 45000.0,
  "stop_price": 44100.0,
  "stop_distance_pct": 2.0,
  "risk_amount": 90.0,
  "risk_pct": 1.0,
  "equity": 9000.0,
  "daily_pnl": -45.0,
  "daily_pnl_pct": -0.5,
  "drawdown_pct": 3.2,
  "open_positions": 2,
  "kill_switch": false
}
```

Log is append-only. Never delete or modify audit log entries.

---

## Paper Trading Mode

In PAPER mode, all of the above applies identically.
The only difference: orders go to the paper execution engine, not a real exchange.

This ensures the risk engine is tested in real conditions before live deployment.
Paper mode is **not** a relaxed mode. Same limits, same rejections, same audit log.

---

## What the Risk Engine Does NOT Do

- It does NOT select strategies or signals.
- It does NOT decide when to enter or exit (that is the strategy layer).
- It does NOT adapt parameters automatically over time.
- It does NOT have a "learning" component.
- It does NOT have any Claude/AI component. It is pure deterministic code.
- It does NOT close positions when activated (kill switch stops new, not existing).
- It does NOT guarantee profits. It guarantees risk is bounded.

---

## Implementation Notes for Codex

- Implement as a standalone class `RiskEngine` with no external dependencies except config and logging.
- `RiskEngine` holds state in memory + persists critical state (kill_switch, drawdown peak, daily_pnl) to disk.
- On startup, load persisted state. If persisted state shows kill_switch=True, engine starts halted.
- Thread-safe: all state mutations protected by lock (if async/threaded environment).
- Tests MUST cover: every reject reason, boundary conditions on all % thresholds, restart persistence.
- Do NOT mock the risk engine in integration tests. Use it for real.
