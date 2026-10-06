# Agent Coordination — Trading Intelligence AI

> Last updated: 2026-10-05

## Current Phase: IMPORT & REVIEW — existing PAPER baseline

Existing code found at `C:\Users\tatop\trading-ai`: 547 tests reproduced 05-10-2026 in a clean source copy.
Engineering copy: `C:\Users\tatop\.codex\.chatgpt-projects\g-p-6a9dd44fb9348191a9ece7cc6b44c04c\trading-intelligence-ai`.
Branch `codex/import-paper-baseline`, based on `ccr-b66a9a9e-okj2pl` at `1c6103f67e96f0c2ad68ffc90c1432c78b875059`.
Issue: https://github.com/tatopozot-rgb/trading-intelligence-ai/issues/2
No merge until cross-review. The old no-code setup description is historical, not the program's current state.

## Active Tasks

| Task | Agent | Status | Files Affected | Notes |
|------|-------|--------|----------------|-------|
| Coordination infrastructure | Trading Codex | DONE | AGENTS.md, docs/*, .claude/*, .github/* | Initial setup |
| Notion operations center | Trading Codex | DONE | — | Existing center verified; update rather than duplicate |
| Import baseline, dependency declaration, safety guard, manual CI | Trading Codex | IN PROGRESS | root source/tests/docs, .github, tools/check_repository.py | No operational logic changes; Issue #2 |
| Architecture/risk cross-review | Trading Claude Work | WAITING FOR PR | read-only source and PR comments | Task confirmed no concurrent implementation |
| MARKET lot/dust offline contract | Trading Codex | IN REVIEW (PR #4, branch `codex/market-lot-contract`, stacked on PR #3) | execution_market_filters.py, test_execution_market_filters.py | Offline only; fail-closed; quoteOrderQty and LOT_SIZE-on-MARKET unverified in official docs; no paper_fills change |
| Finding 3: persistent automatic drawdown halt (separate from PAUSA_ENTRADAS; fail-closed; never auto-clears; closes unaffected) | Claude Code local (review: Trading Claude-Work) | REVIEW — branch `claude-code/finding-3-persistent-halt` (stacked on PR #4). Mechanism done; threshold NOT approved, so entries are blocked (fail-closed) until Trading Claude-Work sets `config.DRAWDOWN_HALT_PCT` | paper_store.py, paper_monitor.py, config.py, test_paper_halt.py | Mechanism only. Threshold `DRAWDOWN_HALT_PCT` is None until Trading Claude-Work approves a value: entries stay blocked while unset (fail-closed). Connectivity watchdog and pause/auto-resume tiers NOT in this change. |
| Finding 2: daily-loss contract tests (UTC-5 day boundary, baseline preserved) | Claude Code local (review: Trading Claude-Work) | REVIEW — same branch; 2 contract tests added | test_paper_halt.py | Tests only; no clock or formula change |
| Real-data BTCUSDT 1D backtest + walk-forward (research only) | Claude Code local | DONE — NO-GO: 11 trades (<30 minimum), 0 walk-forward folds (IS Sharpe < 0.5). Defect registered: downloader silently uses testnet by default; owner Trading Codex, not fixed here | — | Results in docs/CHECKPOINT.md |

## Handoff — Claude Code local

| Task | Status | Files | Notes |
|------|--------|-------|-------|
| Finding 3 persistent drawdown halt | DONE (mechanism), REVIEW | paper_store.py, paper_monitor.py, config.py, test_paper_halt.py, test_paper_system.py, test_paper_cash.py, test_paper_depth.py, test_paper_report.py, test_runner_inbox.py | `DRAWDOWN_HALT_PCT=None`: entries blocked until Trading Claude-Work approves a value |
| Finding 2 daily-loss contract tests | DONE, REVIEW | test_paper_halt.py | Baseline UTC-5 preserved |
| Halt exposure in paper_report and ControlPaper | DONE, REVIEW | paper_report.py, paper_control.py, test_paper_doctor.py | Read-only; clear action not exposed |
| BTCUSDT 1D research run | DONE, NO-GO | docs only | 11 trades; 0 walk-forward folds |

Full root suite: 624 passed, 1 pre-existing environmental failure (test_launcher_venv / pyvenv.cfg). Flaky: test_paper_ui_controls.

Tasks for TRADING CODEX:
- `BinanceSpotAdapter` defaults to `testnet=True`; the downloader inherits it and can silently return incomplete testnet history. Fix without breaking public downloads.

Tasks for CLAUDE LEADER / RISK:
- Decide whether the pause tier with auto-resume is still required (not implemented).
- Decide whether the 60 s connectivity watchdog is still required (not implemented).
- Review equity valued at public ticker/depth price vs. the executable book.
- Set `DRAWDOWN_HALT_PCT` and ratify the all-time high-water peak policy.

Safety: CAPITAL_USD unchanged; LIVE not enabled; no private credentials; Binance read-only (public data).
`C:\Users\tatop\trading-ai` is NOT a git repo and must not be modified accidentally.

Free files: everything not listed above. Released by this session: paper_report.py, paper_control.py, test_paper_doctor.py.

## Completed Tasks

| Task | Agent | Date | PR |
|------|-------|------|----|
| Initial coordination setup | Trading Codex | 2026-10-05 | — |
| Specs and research package received from remote work | Trading Claude Work | 2026-10-05 | prior #1 / commit 69cbc2b |

Remote work added seven specs, indicators, Dual MA candidate and backtest/walk-forward package before import.
Preserved unchanged in the integration base. Full prior coordination and proposed decisions are archived in
docs/history/COORDINATION_CLAUDE_2026-10-05_1615.md. Proposed defaults/strategy are NOT user-approved runtime changes.
Do not reconstruct the existing root risk/planner/store to match a draft package without a concrete audit finding.
Next cross-review includes reconciling these contracts and correcting the false dependency on API keys for public history.

## Technical Decisions

| Decision | Rationale | Date | Agent |
|----------|-----------|------|-------|
| Binance Spot as first exchange adapter | Most common, best documented API, owner's primary account | 2026-10-05 | Trading Codex |
| XM/MetaTrader as second adapter | Separate adapter pattern, no coupling with Binance | 2026-10-05 | Trading Codex |
| PAPER mode only until explicit authorization | Safety requirement from owner | 2026-10-05 | Both |

## File Ownership (Current Sprint)

Trading Codex owns import changes, docs/CHECKPOINT.md, docs/AGENT_COORDINATION.md, .gitignore,
requirements.txt, .github/workflows/paper-tests.yml and docs/INDEX.md/IMPORTACION_2026-10-05.md.
Codex delegated only tools/check_repository.py and test_repository_safety.py to its bounded internal reviewer.
That auxiliary hit a usage limit after writing files; main inspected/tested them (11 tests OK; full suite 558 OK).
Do not re-trigger the auxiliary just to retry its quota. Main now owns both files for any follow-up corrections.
Trading Claude Work reviews without editing these files. After findings, Codex patches and tests before integration.

## Dependencies & Blockers

| Blocker | Waiting On | Impact |
|---------|-----------|--------|
| Git CLI authentication | Not configured | Use already-authorized GitHub connector; does NOT block import/review |
| Remote Windows CI | Availability/included allowance not verified | Workflow manual, local results kept distinct |
| Binance private/Testnet access | Future authorization/configuration | Public data and offline/PAPER tests do NOT require keys |
| XM/MetaTrader account/terminal | Future platform validation | Pure separate snapshot adapter already exists; no account connection yet |

## Next Available Work

1. Codex finishes import safety checks and opens PR linked to Issue #2.
2. Trading Claude Work reviews migration and bounded risk/architecture findings; no broad rebuild or parameter selection.
3. Codex fixes findings and runs changed-area tests before merge. Then resume versioned MARKET lot/dust fill contract,
   preserving V1 evidence and existing LIMIT contracts. Historic H6c is complete and negative, not to be repeated or optimized post hoc.

## Operational coordination

Notion: https://app.notion.com/p/3f002a0ff45f81c58fecc00ba9221812
User added Mission Control orchestration: main coordinates existing tasks/agents without pretending to change the
underlying model/platform. Trading Claude Work retains quantitative review; Codex engineering. Registry/rules:
docs/MISSION_CONTROL.md. WAIT-CLAUDE-CODE-001 tracks a CLI installation-result question in the other task;
do not repeat it. Publication/tests do not depend on that answer. One record per WAITING_FOR_USER.
New development heartbeat every eight hours explicitly authorized 05-10-2026:
`trading-intelligence-continuidad-cada-8-horas`. No old hourly/five-hour monitors or continuous goals.
This is development continuity, never an operational trading-session trigger. Pause when genuinely blocked on user;
remain quiet for unchanged state and stop/delete after final acceptance gates, not after partial completion.
