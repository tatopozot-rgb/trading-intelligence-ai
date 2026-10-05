# Agent Coordination — Trading Intelligence AI

> Last updated: 2026-10-05T21:45:00Z

## Current Phase: REVIEW — PR #3 and PR #4 cross-reviewed; PR #5 (fix) opened; none merged yet

Three agents are active on this project (see `AGENTS.md` for the permanent
definition — do not reintroduce a fourth "plain chat" agent in any document):
- **Trading Claude-Work** (real ChatGPT Work): cross-review, architecture, risk, quant, Notion Mission Control.
- **Trading Codex** (this agent, cloud container, no local-PC access): engineering, GitHub, CI, this review.
- **Claude Code local** (PowerShell on the owner's PC, `C:\Users\tatop\trading-ai`): did the real import (PR #3) and the MARKET lot/dust contract (PR #4).

GitHub is the shared source of truth. Check PR/issue state before assuming
what another agent has or hasn't done — do not rely on stale doc text alone.

## Active Tasks

| Task | Agent | Status | Files Affected | Notes |
|------|-------|--------|----------------|-------|
| Resolve PR #3 Finding 2 (UTC vs local-day risk reset) | Trading Claude-Work | WAITING_FOR_USER* | docs/RISK_ENGINE_SPEC.md or paper_store.py | *Needs risk-policy sign-off, not an owner question — see PR #3 review comment |
| Resolve PR #3 Finding 3 (missing drawdown/connectivity kill-switch) | Trading Claude-Work + whoever implements | BACKLOG | risk_engine.py / paper_store.py | Real gap vs spec; decide implement-now vs explicitly defer |
| PR #5 (is_junction Linux fix) | Trading Codex (cloud) | REVIEW | tools/check_repository.py | Opened by this agent, stacked on PR #4, awaiting merge |
| Merge PR #3 → PR #4 → PR #5 chain | Pending Trading Claude-Work sign-off | BLOCKED | — | Issue #2 checklist requires cross-review before any merge |
| Notion Mission Control sync for PR #4/#5 | Trading Claude-Work or Claude Code local | BACKLOG | Notion RUNS/CHECKPOINTS | This agent logged its own RUN entries; full Mission Control sync still pending |
| Real-data backtest on BTCUSDT via new downloader | **Claude Code local** | BACKLOG | trading_intelligence/ | Downloader exists and is fully tested (mocked). Cloud container cannot reach api.binance.com (confirmed via proxy status: explicit policy 403, not a credentials issue) — needs an agent with real network access. |

## Completed Tasks

| Task | Agent | Date | PR |
|------|-------|------|----|
| Initial coordination setup | Trading Codex | 2026-10-05 | #1 |
| Quantitative specs (7 documents) | Trading Claude-Work | 2026-10-05 | #1 |
| trading_intelligence/ strategy+backtesting layer | Trading Claude-Work | 2026-10-05 | #1 |
| trading_intelligence/ risk+execution layer (RiskEngine, PaperAdapter, BinanceSpotAdapter skeleton) | Trading Codex (cloud) | 2026-10-05 | #1 |
| CI for trading_intelligence/ (research-tests.yml) | Trading Codex (cloud) | 2026-10-05 | #1 |
| Real PAPER system import (47→91 modules, 547→558 tests) | Claude Code local | 2026-10-05 | #3 |
| Mission Control / Notion structures for import | Claude Code local | 2026-10-05 | #3 |
| Cross-review of PR #3 (independent Linux reproduction) | Trading Codex (cloud) | 2026-10-05 | #3 (review) |
| MARKET/LOT_SIZE/dust offline contract (fail-closed), 16 tests | Claude Code local | 2026-10-05 | #4 |
| Cross-review of PR #4 (independent Linux reproduction) | Trading Codex (cloud) | 2026-10-05 | #4 (review) |
| Fix is_junction() Linux/Mac crash in tools/check_repository.py | Trading Codex (cloud) | 2026-10-05 | #5 |
| Nomenclature correction: 3-agent structure in AGENTS.md | Trading Codex (cloud) | 2026-10-05 | this branch |
| Fixed BinanceSpotAdapter requiring credentials for public market data | Trading Codex (cloud) | 2026-10-05 | this branch |
| trading_intelligence/data/downloader.py (historical OHLCV, Parquet cache) | Trading Codex (cloud) | 2026-10-05 | this branch |

## Technical Decisions

| Decision | Rationale | Date | Agent |
|----------|-----------|------|-------|
| Real PAPER system (root flat modules) is authoritative over trading_intelligence/ | Explicit owner instruction | 2026-10-05 | Owner |
| trading_intelligence/ kept as parallel research/reference package, not deleted | No conflict; useful once real system's data layer exists | 2026-10-05 | Trading Codex (cloud) |
| Do NOT merge PR #3/#4 yet | Issue #2 checklist incomplete; Findings 2/3 unresolved | 2026-10-05 | Trading Codex (cloud) |
| is_junction() fix goes in its own PR (#5), not pushed directly to PR #3/#4 branches | Avoid simultaneous edits on branches owned by Claude Code local | 2026-10-05 | Trading Codex (cloud) |
| PAPER mode only, no martingale, no risk escalation after loss | Owner safety requirement, verified present in all reviewed code | 2026-10-05 | All |

## File Ownership (Current Sprint)

| File/Area | Owner | Status |
|-----------|-------|--------|
| trading_intelligence/ (all) | Trading Codex (cloud) + Trading Claude-Work | DONE for this sprint — 92/92 tests, ruff+mypy clean |
| Real PAPER system (root *.py) | Claude Code local | Imported via PR #3 + #4, pending merge |
| tools/check_repository.py | Trading Codex (cloud) | Fix in PR #5, pending merge |
| RISK_ENGINE_SPEC.md UTC reconciliation | Trading Claude-Work | WAITING on risk-policy decision |
| execution_market_filters.py | Claude Code local | DONE this sprint, reviewed, no changes requested |

## Dependencies & Blockers

| Blocker | Waiting On | Impact |
|---------|-----------|--------|
| PR #3/#4/#5 merge chain | Trading Claude-Work's risk/quant sign-off on Findings 2 & 3 | Real system stays unmerged into `ccr-b66a9a9e-okj2pl` until resolved |
| Binance API keys | Owner provides (env vars), not urgent | Cannot test live connectivity or download real historical data — not requested yet |
| XM/MetaTrader API access | Owner provides credentials | Phase 2, not blocking current work |

## Next Available Work

1. **Trading Claude-Work**: review PR #3 and PR #4 for risk/quant semantics; specifically rule on Finding 2 (UTC vs local day boundary) and Finding 3 (drawdown/connectivity kill-switch — implement now or defer explicitly)
2. **Claude Code local**: continue the real system's own next step (MARKET/quoteOrderQty semantics are now partly covered by PR #4 — remaining: integrate `execution_market_filters.py` with `paper_fills.py`/`paper_store.py` once review lands, per that PR's own checkpoint note "no change to LIMIT/FOK V1 paths... not done in this block")
3. **Trading Codex (either)**: once PR #3→#4→#5 merge, re-run `pytest tests/` to confirm `trading_intelligence/` still passes untouched
4. **Whoever syncs Notion**: PR #4 and #5 RUN entries from this agent are logged; full Mission Control task-board update for the market-lot-contract work is still open
