# Agent Coordination — Trading Intelligence AI

> Last updated: 2026-10-06T02:10:00Z

## Corrected project objective (2026-10-06)

PAPER/backtesting/walk-forward/shadow validation are internal gates, not
the destination — the goal is a complete, production-ready, deployable
system. See `AGENTS.md`'s "Project Goal" section for the full statement.
Once PAPER validates, continue immediately into LIVE-readiness
infrastructure (real adapters, dry-run, shadow mode, deployment prep) — do
not stop at "PAPER works." Only one human gate remains before real money:
`LIVE_ACTIVATION_APPROVAL`, asked once, only when everything else is done.

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
| Finding 2: add missing daily-loss-contract tests; preserve baseline (UTC-5, no clock change) | Claude Code local (review: Trading Claude-Work) | TO DO | paper_store.py, tests | Decision made 2026-10-06 (PR #3 comment 6007584364) — this was never an owner question; the WAITING_FOR_USER label here was wrong and is corrected. Full spec reconciliation tracked separately, non-blocking. |
| Finding 3: persistent automatic halt (separate from PAUSA_ENTRADAS) in common order-opening path | Claude Code local (review: Trading Claude-Work) | TO DO | risk_engine.py, paper_store.py | Decision made 2026-10-06 (PR #3 comment 6007584364) — real gap confirmed by GPT Work's independent review (6007551700). Must define equityMTM/peak-window/deposits distinct from saldo_actual first; fail-closed; never auto-clears; never blocks closes. |
| PR #5 (is_junction Linux fix) | Trading Codex (cloud) | REVIEW | tools/check_repository.py | Opened by this agent, stacked on PR #4, awaiting merge |
| Merge PR #3 → PR #4 → PR #5 chain | Pending Trading Claude-Work sign-off | BLOCKED | — | Issue #2 checklist requires cross-review before any merge |
| Notion Mission Control sync for PR #4/#5 | Trading Claude-Work or Claude Code local | BACKLOG | Notion RUNS/CHECKPOINTS | This agent logged its own RUN entries; full Mission Control sync still pending |
| Real-data backtest on BTCUSDT via new downloader | **Claude Code local** | BACKLOG | trading_intelligence/ | Downloader exists and is fully tested (mocked). Cloud container cannot reach api.binance.com (confirmed via proxy status: explicit policy 403, not a credentials issue) — needs an agent with real network access. |
| Port DryRunAdapter pattern to the real system's broker_adapters.py/execution_context.py | Claude Code local or Trading Codex (local) | BACKLOG | broker_adapters.py, execution_context.py | Reference design in trading_intelligence/execution/dry_run.py. LIVE-readiness track. |
| Port DryRunAdapter + ShadowRunner to real system | Claude Code local or Trading Codex (local) | BACKLOG | broker_adapters.py, execution_context.py | Both built and tested in trading_intelligence/execution/{dry_run,shadow}.py. Real system has no equivalent yet. |
| Run ShadowRunner continuously against live Binance data | Claude Code local | BACKLOG | — | Needs real network access (this cloud container cannot reach api.binance.com) |
| Real notification channel (Slack/email/SMS) for alerts | Unclaimed | BACKLOG | — | Pluggable AlertSink mechanism now built (trading_intelligence/monitoring/alerts.py), wired into RiskEngine. Default LoggingAlertSink only logs — a real sink is the actual remaining gap. |

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
| Fixed gap-down stop-fill bug in BacktestEngine (understated losses on crashes) | Trading Codex (cloud) | 2026-10-06 | this branch |
| trading_intelligence/backtesting/report.py (CSV + self-contained HTML report) | Trading Codex (cloud) | 2026-10-06 | this branch |
| trading_intelligence/execution/dry_run.py (DryRunAdapter — LIVE-readiness execution gate) | Trading Codex (cloud) | 2026-10-06 | this branch |
| trading_intelligence/execution/shadow.py (ShadowRunner — strategy+risk decisions on live data) | Trading Codex (cloud) | 2026-10-06 | this branch |
| trading_intelligence/monitoring/alerts.py + RiskEngine wiring (pluggable AlertSink) | Trading Codex (cloud) | 2026-10-06 | this branch |
| docs/DEPLOYMENT_RUNBOOK.md (modes, startup, crash recovery, rollback) | Trading Codex (cloud) | 2026-10-06 | this branch |
| Corrected project objective in AGENTS.md (production-ready, not PAPER-as-destination) | Trading Codex (cloud) | 2026-10-06 | this branch |

## Technical Decisions

| Decision | Rationale | Date | Agent |
|----------|-----------|------|-------|
| Real PAPER system (root flat modules) is authoritative over trading_intelligence/ | Explicit owner instruction | 2026-10-05 | Owner |
| trading_intelligence/ kept as parallel research/reference package, not deleted | No conflict; useful once real system's data layer exists | 2026-10-05 | Trading Codex (cloud) |
| Do NOT merge PR #3/#4 yet | Issue #2 checklist incomplete; Findings 2/3 unresolved | 2026-10-05 | Trading Codex (cloud) |
| is_junction() fix goes in its own PR (#5), not pushed directly to PR #3/#4 branches | Avoid simultaneous edits on branches owned by Claude Code local | 2026-10-05 | Trading Codex (cloud) |
| PAPER mode only, no martingale, no risk escalation after loss | Owner safety requirement, verified present in all reviewed code | 2026-10-05 | All |
| Finding 2: preserve baseline daily-loss contract (UTC-5, gross-loss formula); do not adopt spec defaults without an explicit migration | GPT Work's independent review found a real contract divergence, not a simple clock bug — changing it blind could reset the day's budget or mix historical baselines | 2026-10-06 | Trading Codex (cloud), per GPT Work review (PR #3 comment 6007551700) |
| Finding 3: build a persistent automatic halt separate from `PAUSA_ENTRADAS`, implemented by Claude Code local, risk thresholds set by Trading Claude-Work (not copied from trading_intelligence/risk/engine.py) | Real gap confirmed in the common order-opening path; my own package's pattern is a design reference only — architecture differs and financial thresholds are not mine to set | 2026-10-06 | Trading Codex (cloud), per GPT Work review (PR #3 comment 6007551700) |

## File Ownership (Current Sprint)

| File/Area | Owner | Status |
|-----------|-------|--------|
| trading_intelligence/ (all) | Trading Codex (cloud) + Trading Claude-Work | DONE for this sprint — 92/92 tests, ruff+mypy clean |
| Real PAPER system (root *.py) | Claude Code local | Imported via PR #3 + #4, pending merge |
| tools/check_repository.py | Trading Codex (cloud) | Fix in PR #5, pending merge |
| RISK_ENGINE_SPEC.md UTC reconciliation | Trading Claude-Work | Decision made 2026-10-06: preserve baseline now, reconcile as a separate versioned task later |
| execution_market_filters.py | Claude Code local | DONE this sprint, reviewed, no changes requested |

## Dependencies & Blockers

| Blocker | Waiting On | Impact |
|---------|-----------|--------|
| PR #3/#4/#5 merge chain | Finding 2 tests + Finding 3 implementation (Claude Code local) + Trading Claude-Work's final risk sign-off | Real system stays unmerged into `ccr-b66a9a9e-okj2pl` until resolved — unblocked from "waiting on a decision" to "waiting on implementation" as of 2026-10-06 |
| Binance API keys | Owner provides (env vars), not urgent | Cannot test live connectivity or download real historical data — not requested yet |
| XM/MetaTrader API access | Owner provides credentials | Phase 2, not blocking current work |

## Next Available Work

1. **Claude Code local**: implement Finding 3 (persistent automatic halt, see Task Board/Active Tasks above — critical, blocks the merge chain) and Finding 2's missing tests (high priority, non-blocking for other work); also still open: integrate `execution_market_filters.py` with `paper_fills.py`/`paper_store.py` per PR #4's own checkpoint note
2. **Trading Claude-Work**: set the actual drawdown/connectivity thresholds for Finding 3 (not 8%/15%/60s by default — those are placeholders from my own unrelated package) once Claude Code local has a draft; final risk sign-off on both findings before merge
3. **Trading Codex (either)**: once PR #3→#4→#5 merge, re-run `pytest tests/` to confirm `trading_intelligence/` still passes untouched
4. **Whoever syncs Notion**: Task Board now has both Finding 2 and Finding 3 as tracked tasks (Claude Code local); PR #4/#5 RUN entries from this agent are logged


## GPT Work operational addendum — 2026-10-06 (proposed cross-review)

Latest user direction: Claude is project leader and tie-breaker; GPT Work joins
as operational collaborator/reviewer, not an independent team. Existing agent
aliases remain traceable rather than multiplying executors.

Claim: Notion Agent City/evidence synchronization and independent PR #3 F2/F3
review, by GPT Work / Trading Claude-Work. No root runtime or research package
files modified; no frontend claimed without Claude's assignment. Claim and
review: Issue #2 comment 6007520212; PR #3 comment 6007551700.

Delivered: six linked Notion views over existing sources; corrected stale states;
CI research logs verified (162 tests, ruff/mypy); data contract and checkpoint in
`docs/AGENT_CITY_DATA_CONTRACT.md` and
`docs/checkpoints/GPT_WORK_AGENT_CITY_2026-10-06.md`.

Claude acknowledged the review (PR #3 comment 6007584364, commit 0503d54):
F2 baseline is preserved; F2 tests and F3 implementation assigned to Claude Code
local, then GPT Work reviews. F2 is not WAITING_FOR_USER. F3's
persistent automatic gates remain unimplemented in the root opening path;
existing HTTP/snapshot protections do not replace them. Preserve the baseline
per that decision; no new numerical policy or merge approved
by this addendum. Public historical data do not require Binance API keys.

Agent City: https://app.notion.com/p/3f102a0ff45f81678550e6b88514b55f
WAIT-NOTION-VISUAL-001 only blocks authenticated browser visual QA, not the
working connector. WAIT-CLAUDE-CODE-001 was superseded by the user's delegation;
this does not certify CLI setup. Source timestamps and authorship conflicts are
flagged in Notion; avoid treating a reported future finish as observed heartbeat.
