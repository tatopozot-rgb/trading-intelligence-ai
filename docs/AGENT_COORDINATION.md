# Agent Coordination — Trading Intelligence AI

> Last updated: 2026-10-05

## Current Phase: SETUP — Awaiting Codebase Upload

The existing codebase from `C:\Users\tatop\trading-ai` will be uploaded to this repository.
Until then, agents prepare coordination infrastructure and operational tooling.

## Active Tasks

| Task | Agent | Status | Files Affected | Notes |
|------|-------|--------|----------------|-------|
| Await codebase upload | Both | BLOCKED | All | Owner will push from local PC |
| Audit uploaded codebase | Trading Codex | WAITING | TBD | Start immediately when code arrives |
| Implement RiskEngine | Trading Codex | WAITING | trading_intelligence/risk/ | Spec in docs/RISK_ENGINE_SPEC.md |
| Implement PaperAdapter | Trading Codex | WAITING | trading_intelligence/execution/paper.py | Spec in docs/PAPER_TRADING_SIMULATION_SPEC.md |
| Implement BinanceSpotAdapter | Trading Codex | WAITING | trading_intelligence/execution/binance.py | Notes in docs/BINANCE_INTEGRATION_NOTES.md |

## Completed Tasks

| Task | Agent | Date | PR |
|------|-------|------|----|
| Initial coordination setup | Trading Codex | 2026-10-05 | — |
| Notion operations center | Trading Codex | 2026-10-05 | — |
| Risk Engine Specification | Trading claude work | 2026-10-05 | — |
| Strategy Validation Framework | Trading claude work | 2026-10-05 | — |
| Paper Trading Simulation Spec | Trading claude work | 2026-10-05 | — |
| XM/MetaTrader Integration Research | Trading claude work | 2026-10-05 | — |
| Binance Integration Notes | Trading claude work | 2026-10-05 | — |
| Initial Strategy Candidates | Trading claude work | 2026-10-05 | — |
| System Architecture Design | Trading claude work | 2026-10-05 | — |

## Technical Decisions

| Decision | Rationale | Date | Agent |
|----------|-----------|------|-------|
| Binance Spot as first exchange adapter | Most common, best documented API, owner's primary account | 2026-10-05 | Trading Codex |
| XM/MetaTrader as second adapter | Separate adapter pattern, no coupling with Binance | 2026-10-05 | Trading Codex |
| PAPER mode only until explicit authorization | Safety requirement from owner | 2026-10-05 | Both |

## File Ownership (Current Sprint)

No files claimed yet — awaiting codebase upload.

## Dependencies & Blockers

| Blocker | Waiting On | Impact |
|---------|-----------|--------|
| Codebase upload | Owner pushes from local PC | Cannot start engineering work |
| Binance API keys | Owner provides (env vars) | Cannot test exchange connectivity |
| XM/MetaTrader API access | Owner provides credentials | Cannot implement XM adapter |

## Next Available Work

Once codebase arrives:
1. **Trading Codex**: Audit code vs docs/SYSTEM_ARCHITECTURE.md, identify gaps, set up CI, implement RiskEngine per docs/RISK_ENGINE_SPEC.md, implement PaperAdapter per docs/PAPER_TRADING_SIMULATION_SPEC.md, implement BinanceSpotAdapter per docs/BINANCE_INTEGRATION_NOTES.md
2. **Trading claude work**: Review uploaded risk engine code, validate against spec, validate quantitative logic, begin backtesting Candidate 1 (MA Crossover) per docs/STRATEGY_VALIDATION_FRAMEWORK.md
3. Both: Create GitHub Issues for identified gaps after audit
