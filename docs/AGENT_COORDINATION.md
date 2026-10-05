# Agent Coordination — Trading Intelligence AI

> Last updated: 2026-10-05T21:15:00Z

## Current Phase: REVIEW — PR #3 (real PAPER system import) cross-reviewed, not merged

Two sessions both named "Trading Codex" are active on this project in different
environments: a **local** session on the owner's PC (`C:\Users\tatop\trading-ai`,
opened PR #3) and a **cloud** session (this one, no local-PC access). GitHub is
the shared source of truth between them — check PR/issue state before assuming
what "the other session" has or hasn't done.

## Active Tasks

| Task | Agent | Status | Files Affected | Notes |
|------|-------|--------|----------------|-------|
| Resolve PR #3 Finding 2 (UTC vs local-day risk reset) | Trading claude work | WAITING_FOR_USER* | docs/RISK_ENGINE_SPEC.md or paper_store.py | *Needs risk-policy sign-off, not a blocking user question — see PR #3 review |
| Resolve PR #3 Finding 3 (missing drawdown/connectivity kill-switch) | Trading Codex (either) | BACKLOG | risk_engine.py / paper_store.py | Real gap vs spec; decide implement-now vs defer |
| Fix is_junction() Linux portability bug | Trading Codex (either) | BACKLOG | tools/check_repository.py | Trivial one-line fix, not blocking current Windows CI |
| Merge PR #3 | Either, after findings resolved | BLOCKED | — | Issue #2 checklist requires cross-review first |
| MARKET/quoteOrderQty/lot/dust filter contract | Trading Codex (local, has context) | BACKLOG | execution_filters.py, execution_percent.py, paper_fills.py | Already flagged by PR #3's own checkpoint as next step |
| Historical data downloader | Trading claude work | BACKLOG | trading_intelligence/data/downloader.py | Lower priority now that real system is authoritative |

## Completed Tasks

| Task | Agent | Date | PR |
|------|-------|------|----|
| Initial coordination setup | Trading Codex | 2026-10-05 | #1 |
| Quantitative specs (7 documents) | Trading claude work | 2026-10-05 | #1 |
| trading_intelligence/ strategy+backtesting layer (indicators, MA crossover, backtest engine, walk-forward) | Trading claude work | 2026-10-05 | #1 |
| trading_intelligence/ risk+execution layer (RiskEngine, PaperAdapter, BinanceSpotAdapter skeleton) | Trading Codex (cloud) | 2026-10-05 | #1 |
| CI for trading_intelligence/ (research-tests.yml) | Trading Codex (cloud) | 2026-10-05 | #1 |
| Real PAPER system import (47→91 modules, 547→558 tests) | Trading Codex (local) | 2026-10-05 | #3 |
| Mission Control / Notion structures for import | Trading Codex (local) | 2026-10-05 | #3 |
| Cross-review of PR #3 (independent Linux reproduction) | Trading Codex (cloud) | 2026-10-05 | #3 (review) |

## Technical Decisions

| Decision | Rationale | Date | Agent |
|----------|-----------|------|-------|
| Real PAPER system (root flat modules) is authoritative over trading_intelligence/ | Explicit owner instruction: "no reconstruir desde cero, el programa real es la autoridad" | 2026-10-05 | Owner |
| trading_intelligence/ kept as parallel research/reference package, not deleted | No conflict (PR #3 doesn't touch it); useful for independent validation/backtesting once real system's data layer exists | 2026-10-05 | Trading Codex (cloud) |
| Do NOT merge PR #3 yet | Issue #2 checklist incomplete; cross-review just posted, needs resolution first | 2026-10-05 | Trading Codex (cloud) |
| PAPER mode only, no martingale, no risk escalation after loss | Owner safety requirement, verified present in both codebases | 2026-10-05 | Both |

## File Ownership (Current Sprint)

| File/Area | Owner | Status |
|-----------|-------|--------|
| trading_intelligence/ (all) | Trading Codex (cloud) + Trading claude work | DONE for this sprint — 92/92 tests, ruff+mypy clean |
| Real PAPER system (root *.py) | Trading Codex (local) | Imported via PR #3, pending merge |
| tools/check_repository.py is_junction fix | Unclaimed | BACKLOG |
| RISK_ENGINE_SPEC.md UTC reconciliation | Trading claude work | WAITING on risk-policy decision |

## Dependencies & Blockers

| Blocker | Waiting On | Impact |
|---------|-----------|--------|
| PR #3 merge | Resolution of Findings 2 & 3 (see CHECKPOINT.md) | Real system stays on its own branch until resolved |
| Binance API keys | Owner provides (env vars), not urgent | Cannot test live connectivity or download real historical data |
| XM/MetaTrader API access | Owner provides credentials | Phase 2, not blocking current work |

## Next Available Work

1. **Either Trading Codex session**: fix the `is_junction()` portability bug (trivial), or pick up the MARKET/quoteOrderQty/lot/dust filter contract work already flagged as next by PR #3's checkpoint
2. **Trading claude work**: weigh in on PR #3 Finding 2 (UTC vs local day boundary for daily loss reset) and Finding 3 (whether to add automatic drawdown/connectivity kill-switches to the real system now)
3. **Whoever merges PR #3**: re-run `pytest tests/` afterward to confirm `trading_intelligence/` still passes untouched
