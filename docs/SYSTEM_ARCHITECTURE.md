---
type: spec
tags: [trading-intelligence, architecture]
status: reference
aliases: ["System Architecture"]
---

# System Architecture — Trading Intelligence AI

> Author: Trading claude work
> Last updated: 2026-10-05
> Status: DESIGN SPEC — Codex implements, confirms against uploaded codebase

## Overview

This architecture is designed for:
- Correctness and safety first
- PAPER trading as primary operational mode
- Clean separation of concerns (data, analysis, risk, execution)
- Testability at every layer
- Recovery after restart
- Future extension to multiple exchanges

---

## Component Map

```
┌─────────────────────────────────────────────────────────────────┐
│                      DATA LAYER                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Market Data  │  │  Historical  │  │   Reference Data     │  │
│  │  (Live WS)   │  │  (Parquet)   │  │  (ExchangeInfo/etc)  │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
└─────────┼─────────────────┼──────────────────────┼─────────────┘
          │                 │                        │
┌─────────▼─────────────────▼──────────────────────▼─────────────┐
│                     ANALYSIS LAYER                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Indicators  │  │   Scanner    │  │   Claude AI          │  │
│  │  (Technical) │  │  (Signals)   │  │   (Optional)         │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
└─────────┼─────────────────┼──────────────────────┼─────────────┘
          │                 │                        │
          └─────────────────┼────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                    STRATEGY LAYER                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │              Strategy Engine                                │ │
│  │   (generates TradeProposal — entry, stop, target, size)    │ │
│  └──────────────────────────┬─────────────────────────────────┘ │
└─────────────────────────────┼───────────────────────────────────┘
                              │ TradeProposal
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RISK ENGINE (GATE)                            │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  RiskEngine.validate_order(proposal)                       │ │
│  │  → APPROVED (with position_size) | REJECTED (with reason)  │ │
│  └──────────────────────────┬─────────────────────────────────┘ │
└─────────────────────────────┼───────────────────────────────────┘
                              │ ApprovedOrder (or rejection stops here)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  EXECUTION LAYER                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │          AbstractExchangeAdapter                          │  │
│  │  ┌─────────────────────┐  ┌──────────────────────────┐   │  │
│  │  │  BinanceSpotAdapter │  │     PaperAdapter         │   │  │
│  │  │  (real exchange)    │  │  (simulation engine)     │   │  │
│  │  └─────────────────────┘  └──────────────────────────┘   │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────┘
                              │ ExecutionResult
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│               PERSISTENCE & MONITORING LAYER                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Trade DB    │  │  Audit Log   │  │   Metrics Engine     │  │
│  │  (SQLite/PG) │  │  (append-    │  │   (P&L, Sharpe,      │  │
│  │              │  │   only file) │  │    Drawdown, etc.)   │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Responsibilities

### Data Layer

**Market Data Service**
- Connects to exchange WebSocket(s)
- Publishes normalized OHLCV candles and tick data
- Handles reconnection, data validation
- Emits: `CandleEvent(symbol, timeframe, ohlcv, timestamp)`

**Historical Data Store**
- Parquet files organized by symbol/timeframe/date
- Download manager: fetch and cache on demand
- Backfill utility: populate from exchange history API
- Never re-download data already cached

**Reference Data**
- ExchangeInfo (symbol filters, tick sizes, lot sizes)
- Fee schedules
- Refresh: cached with TTL (1 hour for exchange info, 24h for fees)

---

### Analysis Layer

**Indicators**
- Pure functions: `(data: pd.DataFrame, params: dict) -> pd.Series`
- No state, no side effects
- Vectorized where possible (pandas/numpy)
- Fully tested with known inputs/outputs

**Scanner**
- Subscribes to candle stream
- Evaluates strategies against incoming data
- Emits: `SignalEvent(strategy_id, symbol, direction, strength, metadata)`
- Rate-limited: doesn't fire signals faster than once per bar close

**Claude AI Integration (Optional, Selective)**
- Invoked only when signal passes pre-filter (don't call for weak signals)
- Used for: context analysis, risk commentary, NOT for execution decisions
- API call cost budgeted per day — turn off if daily budget exceeded
- Claude recommendation is advisory only — risk engine still has veto

---

### Strategy Layer

**Strategy Engine**
- Consumes `SignalEvent`
- Converts signal to `TradeProposal` with: entry, stop, target, rationale
- Stop loss is MANDATORY — no stop, no proposal emitted
- Position sizing calculation happens in Risk Engine (not here)
- Multiple strategies can run simultaneously (managed independently)

**TradeProposal Schema**
```python
@dataclass
class TradeProposal:
    proposal_id: str         # UUID
    strategy_id: str         # which strategy generated this
    symbol: str
    side: str                # "BUY" only for spot-long
    entry_type: str          # "MARKET" | "LIMIT"
    entry_price: Decimal     # for LIMIT; None for MARKET
    stop_price: Decimal      # REQUIRED
    target_price: Decimal    # optional but recommended
    timeframe: str           # signal timeframe
    rationale: str           # human-readable reason
    signal_strength: float   # 0.0 - 1.0
    timestamp: str           # when signal generated
```

---

### Risk Engine

Fully specified in `docs/RISK_ENGINE_SPEC.md`.

Key point: **Risk Engine is a synchronous gate, not an async filter.**
Strategy layer waits for approval before proceeding.

---

### Execution Layer

**AbstractExchangeAdapter** (see `docs/XM_METATRADER_INTEGRATION.md` for interface)

**BinanceSpotAdapter**: real exchange integration
**PaperAdapter**: wraps any adapter, intercepts orders, simulates fills

Strategy/Risk layer NEVER directly instantiates adapters. Gets adapter via dependency injection.
This allows testing with mock adapters and switching paper/live by configuration only.

---

### Persistence Layer

**Trade Database**
```
Schema (minimal):
  trades: id, strategy_id, symbol, side, entry_time, entry_price, quantity,
          exit_time, exit_price, pnl, fees, stop_price, target_price, exit_reason,
          paper_mode (bool)

  orders: id, trade_id, order_type, status, submitted_at, filled_at,
          fill_price, fill_qty, fee, exchange_order_id, paper_mode

  daily_summary: date, starting_equity, ending_equity, realized_pnl,
                 unrealized_pnl, trades_count, fees_paid, drawdown_pct

  risk_events: id, timestamp, event_type, decision, reason, order_data (JSON)
```

**Audit Log**: append-only file (JSONL format). Never truncate. Rotate daily.

**State Persistence**: JSON file for risk engine state (kill_switch, daily_pnl, drawdown_peak).
Critical: loaded on every startup.

---

## Data Flow: A Single Trade Cycle

```
1. Market Data Service receives new 1H candle close for BTCUSDT
2. Scanner evaluates strategy against updated data
3. Strategy signals: "BUY signal — MA crossover"
4. Strategy Engine creates TradeProposal with stop at recent swing low
5. Risk Engine validates:
   - Kill switch off? ✓
   - Daily limit OK? ✓
   - Position count < max? ✓
   - Calculates position size: 1% equity risk / stop distance
   - Checks exposure limits ✓
   - Returns: APPROVED, quantity = 0.05 BTC
6. Execution (Paper mode): PaperAdapter queues order for next bar open
7. Next bar opens at $45,000: paper fill at $45,022.50 (5bps slippage)
8. Fee deducted: 0.1% = $22.51
9. Position created in Trade DB
10. Risk Engine state updated: +1 open position, exposure updated
11. Audit log entry written
12. Metrics engine updated: unrealized P&L displayed
```

---

## Module Structure (Recommendation for Codex)

```
trading_intelligence/
├── __init__.py
├── config/
│   ├── __init__.py
│   ├── settings.py          # Config loader (env vars + yaml)
│   └── risk_params.yaml     # Default risk parameters
│
├── data/
│   ├── __init__.py
│   ├── market_data.py       # Live WebSocket data service
│   ├── historical.py        # Historical data store
│   ├── downloader.py        # Fetch and cache historical data
│   └── models.py            # CandleEvent, TickEvent dataclasses
│
├── analysis/
│   ├── __init__.py
│   ├── indicators.py        # Pure indicator functions
│   ├── scanner.py           # Signal scanner
│   └── claude_ai.py         # Optional AI analysis module
│
├── strategy/
│   ├── __init__.py
│   ├── base.py              # AbstractStrategy class
│   ├── models.py            # TradeProposal, SignalEvent
│   └── strategies/
│       ├── ma_crossover.py  # Dual MA strategy
│       └── ...              # Other strategies
│
├── risk/
│   ├── __init__.py
│   ├── engine.py            # RiskEngine (main class)
│   ├── models.py            # RiskDecision, RiskState dataclasses
│   └── state.py             # RiskState persistence
│
├── execution/
│   ├── __init__.py
│   ├── base.py              # AbstractExchangeAdapter
│   ├── paper.py             # PaperAdapter
│   ├── binance.py           # BinanceSpotAdapter
│   └── order_models.py      # OrderRequest, OrderResult
│
├── persistence/
│   ├── __init__.py
│   ├── database.py          # SQLite/Postgres abstraction
│   ├── audit_log.py         # Append-only audit log
│   └── models.py            # DB schema models
│
├── monitoring/
│   ├── __init__.py
│   ├── metrics.py           # P&L, Sharpe, drawdown calculation
│   └── notion_sync.py       # Sync metrics to Notion
│
├── backtesting/
│   ├── __init__.py
│   ├── backtest_engine.py   # Backtest runner
│   ├── report.py            # Report generation
│   └── walk_forward.py      # Walk-forward analysis
│
└── main.py                  # System entry point
```

---

## Startup Sequence

```python
def startup():
    1. Load and validate config (fail if invalid risk params)
    2. Load risk engine state from persistence (kill_switch etc)
    3. Connect to exchange (or validate paper mode)
    4. Sync server time (Binance)
    5. Load exchangeInfo and cache
    6. Verify API key permissions (no withdrawal permission check)
    7. Load open positions from DB, reconcile with exchange
    8. Initialize metric engine with historical P&L
    9. Start market data feed
    10. Start scanner
    11. Log: SYSTEM_STARTED with full state summary
    12. Begin main loop
```

---

## Restart Recovery

On any restart (crash or planned):
1. Load risk engine state → if kill_switch was active, it remains active
2. Load open positions from DB
3. Reconcile open positions against exchange (paper: trust DB)
4. Resume from last known state — no trades missed (stops were on exchange)
5. Log: SYSTEM_RESUMED

---

## Testing Strategy

```
Unit tests:
  - RiskEngine: every reject reason, all threshold boundaries
  - Indicators: known input/output pairs
  - PaperAdapter: fill model correctness
  - Position accounting: P&L calculations
  - Config validation: invalid params caught

Integration tests:
  - Full trade cycle (signal → risk → paper execution → DB record)
  - Restart recovery: write state, restart, verify continuation
  - Daily limit enforcement end-to-end
  - Kill switch end-to-end

Backtesting validation:
  - Run backtest on 30 days of known data
  - Run paper engine on same 30-day replay
  - Results must match within rounding tolerance
```

---

## What Claude AI Does (and Doesn't Do)

**Does**:
- Provides narrative analysis of a trade setup when requested
- Identifies potential concerns about a signal (fundamental context)
- Summarizes market regime based on data patterns
- Reviews risk parameters when asked
- Generates human-readable reports

**Does NOT**:
- Override risk engine decisions
- Generate trade signals autonomously in production
- Access trading API directly
- Know account balances (summary only, not raw)
- Make final entry/exit decisions
