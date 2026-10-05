# Agent Coordination — Trading Intelligence AI

> Last updated: 2026-10-05T16:15:00Z

## Current Phase: SETUP — Pre-codebase (strategy layer implemented)

The existing codebase from `C:\Users\tatop\trading-ai` will be uploaded to this repository.
Core strategy/backtesting layer is now implemented. Awaiting owner's codebase upload.

## Active Tasks

| Task | Agent | Status | Files Affected | Notes |
|------|-------|--------|----------------|-------|
| Await codebase upload | Both | BLOCKED | All | Owner will push from local PC |
| Audit uploaded codebase | Trading Codex | WAITING | TBD | Start immediately when code arrives |
| Implement RiskEngine | Trading Codex | WAITING | trading_intelligence/risk/ | Spec in docs/RISK_ENGINE_SPEC.md |
| Implement PaperAdapter | Trading Codex | WAITING | trading_intelligence/execution/paper.py | Spec in docs/PAPER_TRADING_SIMULATION_SPEC.md |
| Implement BinanceSpotAdapter | Trading Codex | WAITING | trading_intelligence/execution/binance.py | Notes in docs/BINANCE_INTEGRATION_NOTES.md |
| Set up CI (GitHub Actions) | Trading Codex | WAITING | .github/workflows/ | pytest + mypy + ruff |
| Historical data downloader | Trading claude work | NEXT | trading_intelligence/data/downloader.py | Needs Binance API keys |
| Run real-data backtest | Trading claude work | NEXT | — | BTCUSDT 1D 2019–2024, needs downloader |
| Walk-forward on Dual MA | Trading claude work | NEXT | — | After real-data backtest |

## Completed Tasks

| Task | Agent | Date | PR |
|------|-------|------|----|
| Initial coordination setup | Trading Codex | 2026-10-05 | #1 |
| Notion operations center | Trading Codex | 2026-10-05 | #1 |
| Risk Engine Specification | Trading claude work | 2026-10-05 | #1 |
| Strategy Validation Framework | Trading claude work | 2026-10-05 | #1 |
| Paper Trading Simulation Spec | Trading claude work | 2026-10-05 | #1 |
| XM/MetaTrader Integration Research | Trading claude work | 2026-10-05 | #1 |
| Binance Integration Notes | Trading claude work | 2026-10-05 | #1 |
| Initial Strategy Candidates | Trading claude work | 2026-10-05 | #1 |
| System Architecture Design | Trading claude work | 2026-10-05 | #1 |
| Python package structure | Trading claude work | 2026-10-05 | #1 |
| Indicator functions (all) | Trading claude work | 2026-10-05 | #1 |
| Strategy models (TradeProposal etc.) | Trading claude work | 2026-10-05 | #1 |
| AbstractStrategy base class | Trading claude work | 2026-10-05 | #1 |
| DualMACrossover strategy | Trading claude work | 2026-10-05 | #1 |
| BacktestEngine (next-bar model) | Trading claude work | 2026-10-05 | #1 |
| Walk-forward analysis module | Trading claude work | 2026-10-05 | #1 |
| 32 tests (all passing) | Trading claude work | 2026-10-05 | #1 |

## Technical Decisions

| Decision | Rationale | Date | Agent |
|----------|-----------|------|-------|
| Binance Spot as first exchange adapter | Most common, best documented API, owner's primary account | 2026-10-05 | Trading Codex |
| XM/MetaTrader as second adapter | Separate adapter pattern, no coupling with Binance | 2026-10-05 | Trading Codex |
| PAPER mode only until explicit authorization | Safety requirement from owner | 2026-10-05 | Both |
| python-binance for Binance adapter | Best coverage of Binance-specific features | 2026-10-05 | Trading claude work |
| Parquet for historical data storage | ~10× smaller than CSV, efficient time-series reads | 2026-10-05 | Trading claude work |
| Fixed fractional position sizing in backtest | Mirrors RiskEngine spec — backtest must match live | 2026-10-05 | Trading claude work |
| Anchored walk-forward (not simple train/test) | Per STRATEGY_VALIDATION_FRAMEWORK.md — avoids data snooping | 2026-10-05 | Trading claude work |

## File Ownership (Current Sprint)

| File | Owner | Status |
|------|-------|--------|
| trading_intelligence/analysis/indicators.py | Trading claude work | DONE |
| trading_intelligence/strategy/models.py | Trading claude work | DONE |
| trading_intelligence/strategy/base.py | Trading claude work | DONE |
| trading_intelligence/strategy/strategies/ma_crossover.py | Trading claude work | DONE |
| trading_intelligence/backtesting/backtest_engine.py | Trading claude work | DONE |
| trading_intelligence/backtesting/walk_forward.py | Trading claude work | DONE |
| trading_intelligence/risk/engine.py | Trading Codex | PENDING |
| trading_intelligence/execution/paper.py | Trading Codex | PENDING |
| trading_intelligence/execution/binance.py | Trading Codex | PENDING |

## Dependencies & Blockers

| Blocker | Waiting On | Impact |
|---------|-----------|--------|
| Codebase upload | Owner pushes from local PC | Cannot reconcile with existing code |
| Binance API keys | Owner provides (env vars) | Cannot test exchange connectivity or download real data |
| XM/MetaTrader API access | Owner provides credentials | Cannot implement XM adapter |

## Next Available Work

Once codebase arrives:
1. **Trading Codex**: Audit code vs docs/SYSTEM_ARCHITECTURE.md, identify gaps, set up CI, implement RiskEngine, PaperAdapter, BinanceSpotAdapter
2. **Trading claude work**: Implement data downloader, run first real-data backtest on BTCUSDT, walk-forward analysis on Dual MA Crossover
3. Both: Create GitHub Issues for identified gaps after audit
