# Checkpoint — Trading Intelligence AI

> Last updated: 2026-10-05 — import in progress (no final PAPER acceptance)
> Agent: Trading Codex

## Current State

**Phase**: IMPORT & REVIEW of existing Windows PAPER program.
**Status**: Source located, isolated reproduction and publication guard passed; GitHub branch import in progress.
Branch: `codex/import-paper-baseline`; base `ccr-b66a9a9e-okj2pl` @ `1c6103f67e96f0c2ad68ffc90c1432c78b875059`.
Integration base updated to `69cbc2bc7047942fed4dae337a991e7be318eb4e` after detecting new remote work.
Preserve its `trading_intelligence/`, `tests/`, pytest.ini, requirements.txt and seven specification documents unchanged.
The imported root PAPER runtime remains separate; requirements-paper.txt and root-only test command avoid mixing suites.
Research code is not connected to the runtime or accepted as risk policy. Remote 32-test claim not independently verified;
its own breakdown totals 33, so report it as claimed evidence until reproduced. Do not sum it with 558 baseline tests.
Prior remote checkpoints/coordination preserved verbatim under docs/history/ with a historical banner.
Issue: https://github.com/tatopozot-rgb/trading-intelligence-ai/issues/2

GitHub is technical authority. Engineering copy (not authenticated Git clone):
`C:\Users\tatop\.codex\.chatgpt-projects\g-p-6a9dd44fb9348191a9ece7cc6b44c04c\trading-intelligence-ai`.
Original `C:\Users\tatop\trading-ai` and its runtime/data remain untouched. Do not develop in both copies.

## Original setup (historical)

- Created `AGENTS.md` with permanent rules for both agents
- Created `docs/AGENT_COORDINATION.md` for task tracking and file ownership
- Created `docs/CHECKPOINT.md` (this file)
- Created `CLAUDE.md` with project context for Claude agents
- Created `.github/pull_request_template.md`
- Set up Notion operations center (if connected)
- Pushed initial coordination infrastructure to repository

## Completed this block

- Found real program (47 Python modules, 43 test files, 18 Markdown); copied source/documents only, no runtime/data.
- Verified 90 original Python files byte-identical. Limited secret-pattern scan: no matches.
- Reproduced 547 tests OK in 56.717s from clean source using original venv; NOT a fresh dependency installation.
- Found existing Notion center and boards; changed upload task from owner-blocked to Codex In Progress.
- Trading Claude Work confirmed it will wait for the PR, then review; no concurrent implementation.
- Added requirements.txt, manual Windows CI, documentation index compatible with Obsidian and publication guard.
- New guard: 11 tests OK (0.097s); 120 explicit files scanned, zero findings. Full suite 558 tests OK (52.808s).
- Mission Control functional structures added in the existing Notion center: PROJECTS, AGENTS, RUNS, BLOCKERS;
  TASKS/CHECKPOINTS/DECISIONS/METRICS reused. IDs and cycle rules in docs/MISSION_CONTROL.md.
- Auxiliary hit its usage limit after writing two files; main reviewed them and tested, no retry loop. Official global
  usage read allowed work; do not equate auxiliary failure to global outage or infer Claude credits.
- Created eight-hour development heartbeat (explicit new user instruction supersedes deleted old monitors).

## Changed files

Initial import of root *.py and *.md; .gitignore, CLAUDE.md, README.md, ESTADO_PROYECTO.md,
requirements.txt, .github/workflows/paper-tests.yml, docs/{AGENT_COORDINATION,CHECKPOINT,INDEX,IMPORTACION_2026-10-05}.md.
Guard tools/check_repository.py and test_repository_safety.py completed and tested; docs/MISSION_CONTROL.md added.

## Exact next step

Guard and directed/full tests are finished. Build explicit publication manifest (never copy runtime), publish source to branch,
open PR for Issue #2 and request Trading Claude Work cross-review. Reconcile published file hashes and update Notion.
Then address findings before merge and resume the technical next step below; no reconstruction or repeated historical runs.

Technical next step retained from 30 September: read MODELO_FILLS_PAPER.md, execution_filters.py,
execution_percent.py, execution_context.py and paper_fills.py. Verify official Binance MARKET_LOT_SIZE/LOT_SIZE
and quoteOrderQty semantics, define versioned lot/dust contract with fixtures, preserve V1 evidence and persisted model.
Do not reuse LIMIT filters by analogy or modify risk/strategy to fit adverse results.

## Blockers

- Git CLI cannot authenticate noninteractively; authorized GitHub connector works. Not a user blocker.
- CI remote execution/allowance not verified; manual workflow only, do not claim remote tests passed.
- Dataset-backed historical evidence stays local; full H6c cannot be reproduced from GitHub alone yet.
- Execution realism (lot/dust, calibration), strategy out-of-sample validation, final audit still open.
- Private/Testnet/XM access is not configured; it does not block public data or fixture/PAPER development.

## Test Status

547 baseline tests OK (56.717s), then 11 new guard tests OK (0.097s), then full 558 tests OK (52.808s), 05-10-2026.
No operational session; new publication guard scans only explicit/tracked paths and does not certify complete security.
Sandbox initially denied Python process; permitted isolated execution succeeded. Mock HTTP/disk errors expected.

Command from engineering copy (existing local venv):
```powershell
$tests = @(Get-ChildItem -File -Filter 'test_*.py' | Select-Object -ExpandProperty BaseName)
& 'C:\Users\tatop\trading-ai\.venv\Scripts\python.exe' -B -m unittest @tests -q
```
Fresh checkout setup: README.md. No credentials needed for tests. No repeated suite until meaningful code/test changes.
Use the explicit root-only command after combining with the research package; the earlier discover result describes
the clean baseline before remote-package incorporation. Research tests/ uses pytest.ini and separate dependencies.

## Single unanswered question (does not block engineering)

WAIT-CLAUDE-CODE-001 exists in Notion: Trading Claude Work asked for the result of installing Claude Code.
Do not repeat or execute that user workflow in parallel. It blocks CLI setup there, not publication/testing here.
No Binance keys or MT5 installation required for current work. See docs/MISSION_CONTROL.md.

## System Health

PAPER program exists; no new session started, no account/funds accessed. Session max eight hours is not a 24/7 service.
H6c historical shared-capital sensitivities gave realized balances 87.0513 / 88.8265 from hypothetical 100,
with one open ETH position at cost (NOT mark-to-market or final account value). No profitability validated.
Full construction/audit NOT finished; final email must not be sent yet.
