# Agent Coordination — Trading Intelligence AI

> Last updated: 2026-10-05

## Current Phase: SETUP — Awaiting Codebase Upload

The existing codebase from `C:\Users\tatop\trading-ai` will be uploaded to this repository.
Until then, agents prepare coordination infrastructure and operational tooling.

## Active Tasks

| Task | Agent | Status | Files Affected | Notes |
|------|-------|--------|----------------|-------|
| Coordination infrastructure | Trading Codex | DONE | AGENTS.md, docs/*, .claude/*, .github/* | Initial setup |
| Notion operations center | Trading Codex | IN PROGRESS | — | Setting up project tracking |
| Await codebase upload | Both | BLOCKED | All | Owner will push from local PC |

## Completed Tasks

| Task | Agent | Date | PR |
|------|-------|------|----|
| Initial coordination setup | Trading Codex | 2026-10-05 | — |

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
1. **Trading Codex**: Audit code, document architecture, identify gaps, set up CI
2. **Trading claude work**: Review risk model, validate quantitative logic, assess strategy
3. Both: Create issues for identified work items
