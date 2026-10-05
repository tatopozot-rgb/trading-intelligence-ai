# CLAUDE.md — Trading Intelligence AI

## Project Overview

AI-powered trading system for cryptocurrency and forex markets. Includes data acquisition, market scanning, analysis, trade planning, risk engine, PAPER trading, monitoring, and persistence.

## Architecture

- **Exchange Adapters**: Binance Spot (primary), XM/MetaTrader (secondary) — separate adapters, no coupling
- **Risk Engine**: Deterministic, non-bypassable. No martingale. No automatic risk increase for loss recovery.
- **Mode**: PAPER ONLY until explicitly authorized by owner
- **AI Integration**: Claude used selectively for analysis, not for execution decisions that bypass risk engine

## Key Constraints

- Never execute real trades, move funds, or enable withdrawals without explicit owner authorization
- Risk engine decisions are final — Claude cannot override them
- Daily loss limits, position size limits, and exposure limits are enforced at engine level
- All fills must account for fees, slippage, and realistic execution

## Agent Coordination

- Read `AGENTS.md` for roles and rules
- Read `docs/CHECKPOINT.md` before starting work
- Update `docs/AGENT_COORDINATION.md` when claiming tasks
- GitHub is the source of truth

## Development

- Python is the primary language (confirm after codebase upload)
- Tests required for: risk engine, order execution, position management
- Type hints required
- Logging: DEBUG (dev), INFO (ops), WARNING/ERROR (issues)

## Platforms

| Platform | Status | Notes |
|----------|--------|-------|
| Binance Spot | Primary | First implementation target |
| XM/MetaTrader | Secondary | Separate adapter, investigate viable integration |
