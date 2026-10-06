# Checkpoint — Trading Intelligence AI

> Last updated: 2026-10-05 — Finding 3 halt implemented on claude-code/finding-3-persistent-halt (pending review)
> Agent: Trading Codex

## Live status (autonomous session, 2026-10-05)

- Issue #2 open. PR #3 open: `codex/import-paper-baseline` -> `ccr-b66a9a9e-okj2pl`, not draft, not merged.
  PR #1 open: `ccr-b66a9a9e-okj2pl` -> `main` (remote specs/strategy package). Remote `main` untouched.
- Verified GitHub (private repo, read via existing git credential): PR #3 head `933642a`; import branch code is
  byte-identical to local `C:\Users\tatop\trading-ai` root `*.py` once CRLF is ignored (0 content diffs).
  Only local-only files: runtime/data (`trading.db`, `runner*.json/lock`, `claude_request*`, `DETENER_SESION_*`); not published.
- Publication guard on PR #3 tree: `tools/check_repository.py` -> 153 files, 0 findings.
- Baseline reproduced locally in `C:\Users\tatop\trading-ai` (original `.venv`): 547 tests OK (52.6s).
- PR #3 tree reproduced: 558 tests OK (54.4s). The 11 extra are `test_repository_safety`.
- "32 tests" claim (`docs/history/CHECKPOINT_CLAUDE_2026-10-05_1615.md`): NOT reproduced. Its breakdown is
  in the research package under `tests/` (pytest, separate deps), not in the root suite. Not summed with 558.
- Working copy for this session: `C:\Users\tatop\trading-intelligence-work\repo` (git clone, not the `.codex` snapshot).
  Original `C:\Users\tatop\trading-ai` was only read and executed, never modified.

### Branch `claude-code/finding-3-persistent-halt` (stacked on PR #4 `codex/market-lot-contract`, Claude Code local)

- **Finding 3 mechanism implemented**: persistent automatic drawdown halt, separate from `PAUSA_ENTRADAS`.
  - `paper_store.py`: new `paper_halt` singleton row (activo, razon, pico_equity, equity_activacion).
    `equity_mtm()` = realized balance + unrealized P&L using the same formula as `calcular_resultado_cierre`.
    `_evaluar_halt()` is the single decision point, called from `_abrir_validado` (covers both Claude and
    `REGLAS_PAPER_V1` entry paths). Activation is committed even though the entry is rejected (returns
    `registrada: False`); an already-active halt raises.
  - `paper_monitor.revisar_operaciones()` also calls `evaluar_riesgo()` every cycle, isolated in try/except,
    so the peak is captured from MTM even with no entry attempts. Closing positions is never gated.
  - `liberar_halt(confirmado=True)` is the only exit; refused while drawdown is still at or above the threshold.
    Nothing auto-clears on restart or price recovery.
  - Fail-closed: missing/corrupt halt row, unapproved threshold, or any price failure blocks new entries.
    A price failure does NOT activate the halt (it is not evidence of drawdown).
  - Events `HALT_ACTIVADO`, `HALT_LIBERADO`, `HALT_INICIALIZADO` in `paper_events`.
- **Threshold is NOT approved**: `config.DRAWDOWN_HALT_PCT = None`. While unset, the PAPER runner opens no new
  entries (by design). Trading Claude-Work must supply the value. Spec placeholders (8%/15%) are not used.
- **Decisions taken for Trading Claude-Work to ratify or change**:
  1. Peak = all-time high-water mark of equity (most conservative). The spec's 30-day rolling lookback is not implemented.
     Consequence: one bad quote that spikes MTM ratchets the peak permanently; recovery then requires a human decision.
  2. Only the persistent halt is implemented. Drawdown pause with auto-resume (spec tier 1) and the connectivity
     watchdog (spec 60 s) are NOT implemented.
  3. Liberation does not reset the peak.
- **Known limitations**: open positions are valued at the public ticker price, also for depth-model (`modelo_fill_paper`)
  positions, not at the executable book. The valuation runs inside the BEGIN IMMEDIATE transaction, so slow HTTP can hold
  the SQLite write lock (timeout 10 s). `paper_report` and `ControlPaper` do not yet expose the halt state or a clear action.
- **Finding 2 tests**: `DailyLossContractTests` pins the baseline UTC-5 day boundary (04:59 UTC vs 05:00 UTC) and checks
  that losses before the cutoff count against the previous local day's budget. Contract preserved; no clock change.
- **Test fixtures**: legacy PAPER test setups now inject `DRAWDOWN_HALT_PCT=50.0` and a deterministic
  `_precio_para_equity` (100.0). Without the injection, tests hit the real Binance ticker; one run produced a
  ~34 000 "price" and a nonsense peak. This is why the fixtures change.
- Full root suite: **621 passed, 1 failed** (622 collected; baseline 605 + 1 failed, plus 16 new). The failure is
  `test_paper_control::test_launcher_venv_real_con_sonda...`, pre-existing and environmental: it copies `pyvenv.cfg`
  from the system Python prefix, which is not a venv. Not caused by this change.
- Lint: `ruff --select E,F,W` reports the same 4 pre-existing findings in `paper_monitor.py` as HEAD; none new.
- `config.py` is mixed-EOL in HEAD. The diff was rebuilt from HEAD bytes so it shows only the 5 added lines.

### Branch `codex/market-lot-contract` (commit `a33f4e2`, PR #4 open -> `codex/import-paper-baseline`, not draft, not merged)

- New `execution_market_filters.py` (`MARKET_FILTERS_OFFLINE_V1`): offline MARKET quantity contract, fail-closed.
  Requires both MARKET_LOT_SIZE and LOT_SIZE; rejects `quoteOrderQty`; rejects MIN_NOTIONAL/NOTIONAL applying
  to MARKET (needs a reference price); remainder helper `remanente_de_lote` reports dust, never rounds an order.
- New `test_execution_market_filters.py`: 16 tests OK (0.004s).
- Full suite on this branch: 574 tests OK (56.465s) = 558 + 16.
- Official Binance docs (developers.binance.com filters page) confirm LOT_SIZE/MARKET_LOT_SIZE rules and
  MIN_NOTIONAL/NOTIONAL `applyToMarket` flags. They do NOT specify quoteOrderQty validation, nor whether LOT_SIZE
  also applies to MARKET orders. Those points are therefore conservative (reject) and remain UNVERIFIED.
- `execution_filters.py`, `execution_percent.py`, `paper_fills.py`, `paper_store.py`, `risk_engine.py`, V1 evidence: unchanged.

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

1. DONE: PR #4 opened (`codex/market-lot-contract` -> `codex/import-paper-baseline`; does not touch `main` or PR #3 merge state).
2. Request Trading Claude Work cross-review of PR #3 (migration, risk/architecture) and of the new MARKET contract
   (quantitative/fill-semantics review). No merge until review.
3. Then decide, with review input, how the MARKET contract integrates with `paper_fills.py`. Not done in this block:
   no change to LIMIT/FOK V1 paths, no persisted-model change, no quoteOrderQty support.
4. Still open: Notion update for PR #3 (Mission Control), and whether the cross-review requires PR #3 fixes first.

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
Session re-run 05-10-2026: root baseline 547 OK (52.6s, original venv); PR #3 tree 558 OK (54.4s);
branch `codex/market-lot-contract` 574 OK (56.5s) = 558 + 16 new MARKET contract tests.
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
