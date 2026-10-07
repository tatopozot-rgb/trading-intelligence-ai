---
type: coordination
tags: [trading-intelligence, coordination, agents]
status: living
aliases: ["Agent Coordination"]
---

# Agent Coordination — Trading Intelligence AI

> Last updated: 2026-10-06T13:52:00Z

## "Automated trading company" directive (2026-10-06) — triage and stance

Owner directive: execution is the product, LIVE is the eventual goal
(within hard limits, PAPER/SHADOW as validation not destination), the
system should route by detected market regime instead of running one
fixed strategy, and the project should run as a small agent company.
Triage, so this doesn't become another markdown-only architecture doc:

- **Built, not just designed**: Regime Engine + Strategy Router
  (`trading_intelligence/regime/`, `trading_intelligence/strategy/router.py`)
  — confirmed via a real gap check that neither existed anywhere, in
  either codebase, before today. See Active Tasks / Completed Tasks.
- **LIVE connection prep (Binance/XM)**: handed to Claude Code local as a
  concrete, scoped task (Active Tasks) — real network access and
  real-money account connections are not something this cloud session
  can or should do. No credentials are to be requested, entered, or
  stored by any agent; that step is the owner's alone.
- **Hard LIVE risk limits** (`LIVE_CAPITAL_USD`, `MAX_RISK_PER_TRADE`,
  `MAX_DAILY_LOSS`, `MAX_DRAWDOWN`, `MAX_OPEN_POSITIONS`,
  `ALLOWED_INSTRUMENTS`, `MAX_LEVERAGE`): **genuinely WAITING_FOR_USER**,
  not something this agent will ratify the way the PAPER drawdown
  thresholds were. Those PAPER numbers existed in the project's own
  `docs/RISK_ENGINE_SPEC.md` already — ratifying them was applying a
  decision the project had already made in writing. There is no
  equivalent source for how many real dollars the owner wants exposed;
  inventing one would be exactly the "decisión de riesgo no autorizada"
  this project's own safety posture exists to prevent. Per `CLAUDE.md`,
  fail-closed (no LIVE entries) until the owner sets these explicitly.
- **"Empresa de agentes" (Foundry/HR/Academy/Operations Supervisor)**:
  not building decorative bureaucracy for a project with three real
  agents. The directive's own rule — "no crear agentes decorativos,"
  optimize for useful output per token/cost/time/error — argues against
  standing up named role-play infrastructure with no throughput behind
  it. What already does this job: Notion's AGENTS/Task Board rows track
  who's doing what; GitHub review is the actual QA/Red Team function;
  this document and `docs/CHECKPOINT.md` are the actual knowledge
  layer. If and when a fourth real executor exists, formalize roles
  then — not before.
- **Agent City life-sim expansion**: Claude Code local's domain (local
  filesystem, Computer Use, Obsidian, the 3D app) — this cloud session
  reviews what gets pushed (see the `lib/model.mjs` finding) but does
  not build the city itself.

## Corrected project objective (2026-10-06)

PAPER/backtesting/walk-forward/shadow validation are internal gates, not
the destination — the goal is a complete, production-ready, deployable
system. See `AGENTS.md`'s "Project Goal" section for the full statement.
Once PAPER validates, continue immediately into LIVE-readiness
infrastructure (real adapters, dry-run, shadow mode, deployment prep) — do
not stop at "PAPER works." Only one human gate remains before real money:
`LIVE_ACTIVATION_APPROVAL`, asked once, only when everything else is done.

## Current Phase: REVIEW — PR #3 and PR #4 cross-reviewed; PR #5 (fix) opened; none merged yet

Four real agents are active on this project as of 2026-10-06 (see `AGENTS.md`
for the permanent definition of the original three — do not reintroduce a
"plain chat" agent in any document; the fourth below is a real, spawned
Claude Code Remote session, not a decorative role):
- **Trading Claude-Work / GPT Work** (real ChatGPT Work): cross-review, architecture, risk, quant, Notion Mission Control. Proved this role concretely this session via PR #7's independent review (12 real bugs found across the watchdog, Agent City, and the research pipeline — all independently verified before any were acted on).
- **Trading Codex** (this agent, cloud container, no local-PC access): engineering, GitHub, CI, risk-policy decisions under owner authorization, project leadership/coordination.
- **Claude Code local** (PowerShell on the owner's PC, `C:\Users\tatop\trading-ai`): real import (PR #3), MARKET lot/dust contract (PR #4), Finding 2/3, Agent City 3D, the only agent with real Binance network access. Currently has 7 queued items — see Active Tasks.
- **Quant/Strategy** (Claude Code Remote cloud session, `session_013NRgckXg3s5ATkCcrUe6KN`, spawned 2026-10-06T13:48Z): built and honestly validated a Bollinger Band mean-reversion strategy for `Regime.RANGE`, the one real gap in `StrategyRouter.default_router()`'s coverage. Spawned in response to the owner's explicit "activate more real agents" directive, against a real, verified, previously-unclaimed backlog item — not a decorative role. Result: **NO-GO** (insufficient OOS sample size, real economic cause identified — see `docs/CHECKPOINT.md` section 28). Task complete and reported, not a failure to retry. Tracked in Notion's AGENTS database.

**Named roles the owner asked about that are NOT separately staffed, with
the honest reason** (per the owner's own "no inventes trabajo, no crees
agentes decorativos" rule): *Supervisor* = Trading Codex's own function;
*QA/Red Team* + *Mission Control* = GPT Work's function, already proven
active; *Execution*/*Risk* (real-system side) + *Infra/Recovery* +
*Knowledge* (Obsidian/Agent City) = Claude Code local's function, already
at 7 queued tasks; *Portfolio* = no real backlog yet (one strategy covering
one regime — nothing to allocate across); *Market Watch* = needs live
Binance network access, which only Claude Code local's real PC has among
all active agents, and it's already at capacity.

GitHub is the shared source of truth. Check PR/issue state before assuming
what another agent has or hasn't done — do not rely on stale doc text alone.

## Active Tasks

| Task | Agent | Status | Files Affected | Notes |
|------|-------|--------|----------------|-------|
| Finding 2: daily-loss-contract tests; preserve baseline (UTC-5, no clock change) | Claude Code local — delivered on branch `claude-code/finding-3-persistent-halt` (commit `44eb425`) | **SIGNED OFF** (Claude, 2026-10-06, under owner authorization — see `docs/RISK_POLICY_DECISIONS_2026-10-06.md` §6) | paper_store.py, test_paper_halt.py | Correctly pins the 05:00 UTC cutoff and that losses count in the local day. No PR opened yet for this branch — open one against `codex/market-lot-contract` now that sign-off exists. |
| Finding 3: persistent automatic halt (separate from PAUSA_ENTRADAS) in common order-opening path | Claude Code local — delivered on branch `claude-code/finding-3-persistent-halt` (commit `44eb425`) | **SIGNED OFF** (Claude, 2026-10-06, same doc §6); `DRAWDOWN_HALT_PCT` value ratified at 15.0 (§1) but **not yet applied** to the real `config.py` | paper_store.py, paper_monitor.py, config.py, test_paper_halt.py | Follows `docs/FINDING_3_HALT_DESIGN.md` precisely and adds real care beyond it (e.g. `liberar_halt` re-verifies actual drawdown recovery, not just confirmation). See new task below: applying `DRAWDOWN_HALT_PCT=15.0` is assigned to Claude Code local — Trading Codex's own attempt was blocked by its sandbox's own safety classifier on a live risk-config write (not a permissions denial from the user). |
| ~~Apply `DRAWDOWN_HALT_PCT=15.0`; implement pause tier + watchdog~~ | Claude Code local | **DONE** — commit `1533690` on `claude-code/finding-3-persistent-halt` | config.py, paper_store.py, test_paper_halt.py | Implements `docs/RISK_POLICY_DECISIONS_2026-10-06.md` in full: 15% halt, 8% pause with auto-resume, 30-day rolling peak via new `paper_equity_hist` table, 60s connectivity watchdog via new `ultimo_ok` column. 26 tests, all passing. Reviewed read-only by Trading Codex — see the new bug row below found during that review. |
| **NEW — blocking the merge:** Fix watchdog `ultimo_ok IS NULL` grace-period bypass | **Claude Code local** | TO DO, **verified fix ready to apply** | paper_store.py (`inicializar()`, `liberar_halt()`) | Found and verified by Trading Codex (cloud) reviewing commit `1533690` (checkpoint section 19). A fresh/migrated `paper_halt` row has `ultimo_ok IS NULL`; the watchdog treats `NULL` as an infinite gap, which always exceeds 60s — so a single transient price-feed failure on a position that predates this migration (or any restart where `ultimo_ok` is unset) triggers an immediate *persistent* halt instead of the intended 60s grace window. Reproduced mechanically in an isolated worktree test; confirmed none of the 26 existing tests cover the `NULL` state (all manually set `ultimo_ok` to a controlled past value first). **Fix verified working, diff ready**: backfill any `NULL` `ultimo_ok` to "now" on every `inicializar()` call (idempotent, touches only `NULL` rows); set it at initial row creation too; have `liberar_halt()` refresh it on its own successful valuation. Reran `test_paper_halt.py` (26/26 pass) and the full root suite (176 tests; only the pre-existing tkinter-on-headless-Linux gap, unrelated) against the fix. Not pushed — same category of live risk-file change that hit this session's sandbox block earlier. Full diff in `docs/CHECKPOINT.md` section 19. **DONE when:** the diff is applied, `test_paper_halt.py` passes including a new test for the `ultimo_ok IS NULL` case, and it's pushed to `claude-code/finding-3-persistent-halt`. |
| **NEW — deeper than the row above, found by GPT Work's independent cross-review, verified by Trading Codex (cloud):** fix `_abrir_validado` discarding a successful valuation on an unrelated rejection | **Claude Code local** | TO DO | paper_store.py (`_abrir_validado`, `conectar`) | `_abrir_validado` (line 279) calls `_evaluar_halt`, which writes `ultimo_ok` on success — but that write shares one transaction with the rest of the function (`with conectar() as con:`). A LATER, unrelated rejection (e.g. the duplicate-open-symbol check, lines 297-298) raises `ValueError`, and Python's sqlite3 `with con:` rolls back the *whole* transaction on any exception, discarding the just-recorded successful valuation along with the rejected order. Repro (in `reviews/gpt_work/test_watchdog_review.py`'s `test_rejected_duplicate_does_not_discard_successful_feed_observation`): valid valuation at t0; a rejected duplicate-symbol entry attempt at t+59 that itself re-validates successfully before being rejected; a genuine feed outage at t+61 incorrectly reads as a 61-second gap instead of 2 seconds, triggering a persistent halt. The `ultimo_ok IS NULL` fix above does not touch this path — a system that successfully values the market on every call, but always alongside some unrelated rejection, would never accumulate a fresh `ultimo_ok`. Needs a real architectural fix, not a quick patch: SQLite doesn't support opening a second connection mid-transaction without self-deadlocking (the outer transaction already holds the write lock), so the cleanest approach is likely a `SAVEPOINT` around just the later validation checks (duplicate symbol, capital, daily loss, etc.) — rolling back only the savepoint on their failure, not the whole transaction, so `ultimo_ok`'s write (made before the savepoint) survives. **DONE when:** a new regression test (adapted from GPT Work's repro) passes, the existing halt suite still passes, and a rejected order never gets partially committed (atomicity of the trade-rejection path itself must not regress while fixing this). |
| **NEW — found by GPT Work's independent cross-review, verified by Trading Codex (cloud):** Agent City `lib/model.mjs` accepts future timestamps as "fresh" | **Claude Code local** | TO DO | agent-city-3d/lib/model.mjs | Both `syncOk`'s `snapAge` check and the `recientes` event filter compute `ahoraMs - Date.parse(timestamp)` and compare `< WINDOW` — a *future* timestamp makes this negative, which is trivially less than any positive window, so a future-dated snapshot or event incorrectly passes as fresh/recent. Repro in `reviews/gpt_work/agent_city_acceptance.test.mjs`. **DONE when:** age is validated as finite and non-negative (or an explicit, documented bounded clock-skew allowance is added instead of silently accepting any future date), and the acceptance test's "future snapshot/event" cases pass. |
| **NEW — found by GPT Work's independent cross-review, verified by Trading Codex (cloud):** Agent City paints `WORKING` from a snapshot's raw documented state with no event cross-check | Claude Code local | TO DO | agent-city-3d/lib/model.mjs | `let estado = syncOk ? estadoDoc : "STALE"` trusts the snapshot's own `state` field directly (including a literal `"WORKING"` string) whenever no event matches one of the explicit branches — contradicting the file's own header comment that WORKING requires a real `AGENT_WORKING`/`TASK_STARTED` event. Repro in `reviews/gpt_work/agent_city_acceptance.test.mjs`'s "WORKING text in a snapshot is not a qualifying observed work event" case. **DONE when:** that acceptance test passes, and the original 12 model tests still pass (don't break the already-correct event-driven WORKING path while fixing the documented-state fallback). |
| **NEW:** Port SHADOW mode to the real runtime; confirm continuous-runner control/confirmation | Claude Code local | TO DO, **design ready** | paper_rules.py, paper_store.py, system_runner.py | Owner directive items 7-8. Full grounded design (read the real files read-only first) in `docs/SHADOW_MODE_AND_CONTINUOUS_RUNNER_DESIGN.md`: exact SHADOW injection point (`paper_rules.procesar_candidatos`'s call to `store.ejecutar_reglas` is the one state-mutating step), a proposed `ejecutar_reglas_shadow` sibling, explicit rule against SHADOW polluting `paper_equity_hist`, and a `--sombra-paper` runner flag. Also confirms `system_runner.py --continuo` already satisfies item 8's control/confirmation requirements (single-instance lock, startup reconciliation check, file-based stop/resume, protected shutdown, health snapshots) — SHADOW should reuse it, not get a separate runner. Also confirmed (worth recording): `broker_adapters.py` has no code path that can send a live order at all — NO_LIVE is architecturally true, not just policy. Cloud session has no network to Binance and doesn't own these files; cannot implement or test this itself. **DONE when:** `ejecutar_reglas_shadow` exists, is tested (no network required — mock price functions, same pattern as `test_paper_halt.py`), `--sombra-paper` runs via `system_runner.py --continuo` without ever writing to `paper_trades`/`paper_account`/`paper_equity_hist`, and `runner_status.json` reports `SHADOW_PAPER` while it's active. |
| ~~Push missing `agent-city-3d/lib/model.mjs`~~ | Claude Code local | **DONE** — commit `7913bb0` on `claude-code/agent-city-3d-mvp` | agent-city-3d/lib/model.mjs | Confirmed present on the branch after the follow-up push; not independently re-verified by Trading Codex that `node --test` now passes (owner reports 12/12 passing with Chrome-headless validation). |
| **NEW:** Binance/XM LIVE connection prep — adapter skeletons only, no credentials | Claude Code local | TO DO | broker_adapters.py, new XM/MT5 adapter module | Real network access and real-money account connections are Claude Code local's domain, not this cloud session's. Scope: build/extend the adapter shape for login/session/balances/market-data/positions/execution/reconciliation/trading-permissions as code structure and tests (mockable, no live calls required to test) — do NOT request, enter, prompt for, or store any credential, API key, password, 2FA code, passkey, or OAuth token anywhere (not in code, config, GitHub, Notion, Obsidian, or logs). The moment actual account connection is needed, that step is WAITING_FOR_USER by name, per the owner's own directive — not something any agent attempts around. Withdrawals must be impossible to enable from this code path, full stop. **DONE when:** adapter skeletons exist with mockable tests covering login/session/balances/market-data/positions/execution/reconciliation shape, no credential-handling code path exists anywhere in them, and the task hands off cleanly to a WAITING_FOR_USER checkpoint for actual account connection — not partway into it. |
| **WAITING_FOR_USER / risk review — surfaced by the survival bench, NOT decided by any agent:** survival-policy questions | Owner, with GPT Work (risk) and Claude Code local (root runtime) | OPEN | `docs/CHECKPOINT.md` section 30; `trading_intelligence/risk/engine.py`, `trading_intelligence/execution/paper_runner.py`; root `paper_store.py` for the 30-day peak | (1) enable a trailing stop (built, opt-in; cut mean max drawdown 34.7% -> 23.0%); (2) measure exposure at market value, not entry notional (real exposure reached 30-55% vs a 20% cap) — BUILT opt-in (`exposure_basis`) and MEASURED in section 33: it barely helps (mean max DD 34.7% -> 34.2%, peak exposure unchanged at 54.8%) because it only gates new entries; recommendation is not to spend a decision on it; (3) add a 365-day/all-time drawdown guard (a 30-day peak let 41% and 51% bleeds through without halting; this revisits the 30-day choice in `RISK_POLICY_DECISIONS_2026-10-06.md`); (4) should the halt reduce/close exposure or stay entry-only as the spec says; (5) position-size cap: reject (today) or clamp (spec wording) — with spec defaults the engine rejects every stop tighter than ~20%, so it effectively never trades. All change risk-relevant behavior, so none is an engineering default. **Claude Code local:** check whether findings 2 and 3 also hold for the root system's 30-day peak. |
| **WAITING_FOR_USER — not an engineering decision:** Hard LIVE risk limits | Owner | BLOCKED on the owner, correctly | config.py (future) | `LIVE_CAPITAL_USD`, `MAX_RISK_PER_TRADE`, `MAX_DAILY_LOSS`, `MAX_DRAWDOWN`, `MAX_OPEN_POSITIONS`, `ALLOWED_INSTRUMENTS`, `MAX_LEVERAGE` have no existing spec value to ratify (unlike the PAPER drawdown thresholds, which already existed in `docs/RISK_ENGINE_SPEC.md`) — these are real-money numbers only the owner can set. Fail-closed (no LIVE entries) until set explicitly. See "Automated trading company directive" note above. |
| Fix GPT Work's runner lifecycle + reservation findings (PR #8, `55547d6`) | Trading Codex (cloud) | **DONE** — commit `1e052cd` | paper.py, paper_runner.py, risk/engine.py, risk/models.py, tests | 12 of 14 checks failed at `a0941e3` and all 12 were real (one was a hole in my own earlier idempotency fix). Lifecycle 6/6 and reservation 8/8 now pass, plus the four earlier research suites (36/36). 59 new tests, 15 mutants all killed, 424 passing, ruff+mypy clean. Details and the new `max_fill_risk_overshoot_pct` (default 25.0, owner may tune) in `docs/CHECKPOINT.md` section 31. **GPT Work: please revalidate from the source SHA, not from this row.** |
| Stateful lifecycle fuzzer (`tests/runner_fuzz.py`) + fix for the order-dependent fill checks it found | Trading Codex (cloud) | **DONE** — commit `b02dfec` | tests/runner_fuzz.py, tests/test_runner_fuzz.py, paper_runner.py | Proactive: nothing new from other agents this cycle. Fuzzer detects the pre-fix code (373 violations / 30 seeds) and finds nothing on the fixed code (0 / 160 seeds); it found one real defect (fill vetting depended on symbol order, one equity snapshot per timestamp now). 436 tests, ruff+mypy clean. **GPT Work:** the model of failure here is mine; please attack what it does not cover (listed in `docs/CHECKPOINT.md` section 32). |
| Opt-in market-value exposure basis (survival-policy question 2), built and measured | Trading Codex (cloud) | **DONE** — see `docs/CHECKPOINT.md` section 33 | risk/engine.py, risk/models.py, paper.py, paper_runner.py, tests | Default unchanged. 10 new tests, 7/7 mutants killed, 446 passing, ruff+mypy clean. Result is negative: it barely moves drawdown or peak exposure; trailing stop (question 1) is the lever that does. |
| Cancel queued entries when the risk clock fails before the fill (GPT Work `2557b6f`) | Trading Codex (cloud) | **DONE** — see `docs/CHECKPOINT.md` section 34 | paper_runner.py, tests | Real fail-open, fixed. GPT Work's lifecycle suite 7/7, reservation 8/8; fuzzer extended and detects the reverted fix on its own; 449 tests, ruff+mypy clean. **GPT Work: please rerun from the new SHA.** |
| **WAITING_FOR_USER — not an engineering decision:** ratify `RiskConfig.max_fill_risk_overshoot_pct` (currently 25.0, PROPOSED by cloud, not approved) | Owner, with GPT Work (risk) | OPEN | `docs/CHECKPOINT.md` section 34 (table of what each value means); `risk/models.py`, `risk/engine.py::validate_fill` | A fill is vetoed when loss-at-stop exceeds the per-trade risk budget by more than this percentage. 25% permits a 1.25% modeled loss at the stop for 1% risk (~1.3% adverse gap on a 5% stop). 0% is unusable (ordinary slippage + fees already add ~1%). Not changed by any agent. |
| Fix HistoricalDataDownloader silently defaulting to testnet | Trading Codex (cloud) | DONE | trading_intelligence/data/downloader.py | Real bug Claude Code local found via its own BTCUSDT research run (commit `a58437b`) — reported it rather than touching a file it didn't own. Fixed in `ad20161`: explicit `testnet=False` default + a sanity check in `download_range()`. 198/198 tests, ruff+mypy clean. |
| ~~Place the prepared Obsidian vault package~~ | Claude Code local | **DONE** (confirmed via GitHub issue #2 comment 6017450133: notes/canvas are at `C:\Users\tatop\TATO`, checkpoint generated, SHA `2170d8e`) | `obsidian-vault-package/` → owner's real vault | Not independently re-verified by Trading Codex (no filesystem access); taking Claude Code local's own confirmed report at face value, same as any other agent's completed-task claim. Do not re-ask for this. |
| **NEW — found by GPT Work's independent review of `sync_agent_city.py`, not yet independently verified by Trading Codex (no access to that file from this cloud session):** 3 bugs in the Notion→Agent City sync script | Claude Code local | TO DO | `C:\Users\tatop\agent-city-sync\sync_agent_city.py` | Per GitHub issue #2 comment 6017450133 (4 isolated tests on pure functions only, 1 PASS/3 FAIL, sync daemon itself never run): (1) the Completed Tasks table has no `Status` column, so it reads as `NOT_SYNCED` instead of `DONE`; (2) the literal string `"DONE"` isn't normalized, same `NOT_SYNCED` misreport; (3) `last_result` picks the FIRST historical result (e.g. an old "92/92" test count) instead of the most recent evidence (e.g. "262/262"). **DONE when:** the 4 isolated tests pass (GPT Work says it will publish the pure-function harness in a follow-up PR) and the fix doesn't touch any Obsidian-generated note directly (source/parser fix only). |
| PR #5 (is_junction Linux fix) | Trading Codex (cloud) | REVIEW | tools/check_repository.py | Opened by this agent, stacked on PR #4, awaiting merge |
| Merge PR #3 → PR #4 → {PR #5, finding-3-persistent-halt} → `ccr-b66a9a9e-okj2pl` | Trading Codex (cloud) — sign-off given 2026-10-06 | **CORRECTION (2026-10-06T14:xx, re-checked live via GitHub API):** PR #4 and #5 are individually `mergeable_state: clean` against their own stacked bases, but **PR #3 is `mergeable_state: dirty`** against current `ccr-b66a9a9e-okj2pl` (this branch has moved far ahead since PR #3 opened). The sign-off and safe-order analysis in `docs/RISK_POLICY_DECISIONS_2026-10-06.md` §8 are still valid for the *stack's internal order* — but "ready to execute" overstated it: the stack cannot land until (a) Claude Code local's watchdog fix lands on `claude-code/finding-3-persistent-halt` (per the row above) and (b) someone (Claude Code local, as PR #3's author/branch-owner) merges current `main`/`ccr-b66a9a9e-okj2pl` into `codex/import-paper-baseline` to resolve the conflict — not something Trading Codex should do unilaterally on another agent's branch. | — | Do not merge until both resolve. GitHub is re-checked live, not assumed from this doc. |
| Notion Mission Control sync for PR #4/#5 | Trading Claude-Work or Claude Code local | BACKLOG | Notion RUNS/CHECKPOINTS | This agent logged its own RUN entries; full Mission Control sync still pending |
| Real-data backtest on BTCUSDT via new downloader | **Claude Code local** | BACKLOG | trading_intelligence/ | Downloader exists and is fully tested (mocked). Cloud container cannot reach api.binance.com (confirmed via proxy status: explicit policy 403, not a credentials issue) — needs an agent with real network access. |
| **NEW:** Real-data PAPER replay through `PaperTradingRunner` | **Claude Code local** | BACKLOG, ready to run | `trading_intelligence/execution/paper_runner.py` (built, tested), `trading_intelligence/data/downloader.py` | Needs real network (cloud container gets 403 from api.binance.com). Download BTCUSDT klines with `HistoricalDataDownloader` (explicit `testnet=False`), then `PaperTradingRunner(default_router(), RiskEngine(RiskConfig(), state, AuditLog(dir)), PaperAdapter(adapter, Decimal('10000'), state_path)).run_replay('BTCUSDT', df)`. Report closed trades, `runner.reconcile()` (must be `[]`) and any `ENTRIES_BLOCKED`/`RISK_ERROR_NO_ORDER` steps. Expect few or zero trades: `default_router()`'s only strategy has a recorded real-data NO-GO (checkpoint section 12) — this run tests the wiring on real bars, it is not a profitability claim. **DONE when:** a real-data replay completes with consistent books and the result is recorded in the checkpoint. |
| Port DryRunAdapter pattern to the real system's broker_adapters.py/execution_context.py | Claude Code local or Trading Codex (local) | BACKLOG | broker_adapters.py, execution_context.py | Reference design in trading_intelligence/execution/dry_run.py. LIVE-readiness track. |
| Port DryRunAdapter + ShadowRunner to real system | Claude Code local or Trading Codex (local) | BACKLOG | broker_adapters.py, execution_context.py | Both built and tested in trading_intelligence/execution/{dry_run,shadow}.py. Real system has no equivalent yet. |
| Run ShadowRunner continuously against live Binance data | Claude Code local | BACKLOG | — | Needs real network access (this cloud container cannot reach api.binance.com) |
| ~~Build and validate a mean-reversion strategy for `Regime.RANGE`~~ | **Quant/Strategy** (cloud session, `session_013NRgckXg3s5ATkCcrUe6KN`) | **DONE — NO-GO** (honest result, see `docs/CHECKPOINT.md` section 28) | `trading_intelligence/strategy/strategies/bollinger_reversion.py` (new), `trading_intelligence/analysis/indicators.py`, `trading_intelligence/strategy/router.py` (new `router_with_range_reversion()`, `default_router()` itself untouched), `tests/test_bollinger_reversion.py` (new), `tests/test_indicators.py`, `tests/test_strategy_router.py`, `tests/test_walk_forward.py` | Built `BollingerReversion` (Bollinger Band + RSI oversold-bounce mean reversion, long-only, ATR stop), validated it honestly through `run_anchored_walk_forward(router_factory=...)` on a RANGE-only router config + ~4 years of realistic synthetic daily data. **Result: NO-GO** — 0 OOS trades, 0 folds completed; a RANGE-gated full backtest produced exactly 1 trade in ~4 years. Real cause identified (not just "insufficient data"): of 25 standalone signals, only 4 (16%) coincide with a confirmed `RANGE` bar — 16 land in `TREND_DOWN`, 3 in `BREAKOUT_DOWN` — because genuine low-ADX `RANGE` bars correlate with low realized volatility on this data, making a 2σ Bollinger breach intrinsically rare while actually ranging. Not re-tuned after seeing this number, per `docs/STRATEGY_VALIDATION_FRAMEWORK.md`'s own rule. 321/321 tests passing on the merged branch (21 new from this task), ruff+mypy clean. `router_with_range_reversion()` is NOT promoted into `default_router()` — its own docstring states the NO-GO explicitly. Next real attempt (not undertaken now) would need a volatility-relative trigger (e.g. ATR-scaled Keltner-style bands) calibrated specifically within already-confirmed-RANGE bars, per the checkpoint's own "what would be needed" note. |
| ~~Remediate the `TREND_UP`/`BREAKOUT_UP` NO-GO~~ | **Quant/Validation** (background subagent; hit this session's rate limit mid-task, work reviewed/verified/finished by Trading Codex rather than discarded) | **DONE — honest NO-GO, not promoted** (commit `11b959b` + docs commit, 2026-10-06) | `trading_intelligence/backtesting/backtest_engine.py` (real Sharpe-annualization bug fixed), `trading_intelligence/strategy/router.py` (`candidate_router_trend_4h`, NOT wired into `default_router()`), `tests/synthetic_market.py` (new GARCH+regime-switching generator), `tests/test_trend_following_4h_candidate.py` | Full verdict in `docs/STRATEGY_CANDIDATE_TREND_4H_VALIDATION.md` and checkpoint section 26. The frequency hypothesis (too few 1D crossover opportunities) is **confirmed** on raw trade count (15/15 seeds clear 30 trades at 4h vs. 15/15 failing at 1D) but the full walk-forward GO/NO-GO is **NO-GO in 5/5 sampled seeds** — fixing total trade count didn't fix each OOS fold's own trade count. Real, useful negative evidence: rules out "it's purely a frequency problem," narrows the real cause toward edge quality or walk-forward fold-sizing. Not recommended for a real-data trial as-is. Separately found and fixed a real bug along the way: Sharpe annualization was hardcoded to `sqrt(365)` regardless of actual bar frequency, silently wrong for any sub-daily series — now infers from the equity curve's own index. 280/280 + 7/7 new tests passing, ruff+mypy clean. |

## Completed Tasks

| Task | Agent | Date | PR |
|------|-------|------|----|
| Survival hardening + correlated multi-asset stress bench (`RiskEngine.observe_equity`, position reservations, symbol-parameterized routers, multi-asset `PaperTradingRunner`, opt-in trailing stop, `tests/survival_stress.py`). Bench held every invariant on 60 runs; it also showed exposure caps drifting to 30-55% (cap 20%) and a 30-day drawdown peak letting 41-51% bleeds through | Trading Codex (cloud) | 2026-10-07 | this branch, commits `cd8e512`, `e7384f4`; see `docs/CHECKPOINT.md` section 30 — 365 tests, mutation-checked, ruff+mypy clean. Synthetic data; policy questions listed there are NOT decided |
| Built `PaperTradingRunner` (`trading_intelligence/execution/paper_runner.py`): the missing router → RiskEngine → PaperAdapter link with position registration, protective STOP, fail-closed reconciliation and restart recovery. Also independently confirmed section 27's 7 fixes by running GPT Work's own PR #8 harnesses (PaperAdapter 5/5, RiskEngine 5/5, Binance 6/6, pipeline 6/6) | Trading Codex (cloud) | 2026-10-07 | this branch, see `docs/CHECKPOINT.md` section 29 — 15 new tests (329/329 total), mutation-checked, ruff+mypy clean. Proves wiring/accounting integrity on synthetic data, not profitability; real-data replay needs Claude Code local's network access |
| Fixed 7 real bugs found by GPT Work's independent cross-review (PR #8 draft): PaperAdapter idempotency/pending-order persistence/gap-fill affordability (4), RiskEngine stop-direction/stop-positivity/daily-turnover enforcement (3) | Trading Codex (cloud) | 2026-10-07 | this branch, see `docs/CHECKPOINT.md` section 27 — 293/293 tests (up from 276), ruff+mypy clean |
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
| Decided Finding 2/3 integration path (preserve baseline contract; assign halt implementation); corrected stale WAITING_FOR_USER label | Trading Codex (cloud) | 2026-10-06 | this branch (PR #3 comment 6007584364) |
| WebhookAlertSink — real notification channel (Slack/generic JSON), stdlib only | Trading Codex (cloud) | 2026-10-06 | this branch |
| Grounded Finding 3 design note (read real paper_store.py/risk_engine.py read-only) | Trading Codex (cloud) | 2026-10-06 | this branch (`docs/FINDING_3_HALT_DESIGN.md`) |
| Merged PR #6 (Agent City Notion handoff, docs-only, no conflicts) | Trading Codex (cloud) | 2026-10-06 | #6 |
| Agent City web MVP (V1) — real-data snapshot dashboard | Trading Codex (cloud) | 2026-10-06 | https://claude.ai/artifact/98zjB7JbToV2ernTsjdLKD — static snapshot, not live-polling; discloses the Notion query-limit gap instead of guessing at Task Board totals; relink/regenerate periodically, don't treat as a live feed |
| Regime Engine (`trading_intelligence/regime/detector.py`) + Strategy Router (`trading_intelligence/strategy/router.py`) | Trading Codex (cloud) | 2026-10-06 | this branch — 25 new tests, 245/245 total, ruff+mypy clean. Confirmed via a real gap check this didn't exist anywhere before; `default_router()` honestly covers only TREND_UP (the one strategy this project actually has validated) |
| Post-Trade Learning (`trading_intelligence/learning/regime_performance.py`) | Trading Codex (cloud) | 2026-10-06 | this branch — 8 new tests, 253/253 total, ruff+mypy clean. Tags BacktestEngine's trades with the regime detector's output at each trade's own entry bar (no lookahead); produces plain-language per-regime performance notes, never an auto-applied threshold change (see docs/CHECKPOINT.md section 21 for why) |
| Wired Regime Engine + Strategy Router into `BacktestEngine` (optional `router=` mode, backward-compatible) — a real, runnable end-to-end pipeline | Trading Codex (cloud) | 2026-10-06 | this branch — 5 new tests, 259/259 total, ruff+mypy clean. Ran it on real synthetic data (not just unit tests), found `default_router()`'s original TREND_UP-only coverage produced zero trades despite real signals existing, diagnosed why (ADX trend confirmation lags the crossover event), and fixed it by adding BREAKOUT_UP coverage — grounded in the actual crossover-bar evidence, not guessed. See `docs/CHECKPOINT.md` section 22 |
| Extended walk-forward validation to regime-aware `StrategyRouter` configs (`router_factory=`) | Trading Codex (cloud) | 2026-10-06 | this branch — 3 new tests, 262/262 total, ruff+mypy clean. See `docs/CHECKPOINT.md` section 23 |
| Fixed 5 real bugs found by GPT Work's independent cross-review (PR #7): position-sizing cash cap, `_close_trade` honoring configured fee, missing final equity-curve settlement, `tag_trades_with_regime` fill-bar lookahead, `StrategyRouter` NaN/inf confidence | Trading Codex (cloud) | 2026-10-06 | this branch, commit `29067d2` — 7 new tests, 269/269 total, ruff+mypy clean; cross-checked against GPT Work's own independent `reviews/gpt_work/test_pipeline_review.py` (6/6 pass). See `docs/CHECKPOINT.md` section 24 |
| Fixed 4 real Binance-readiness bugs found by GPT Work's independent review: `canTrade` never checked, `locked` balance ignored, session-verified flag never checked before `submit_order`, MARKET-order minNotional silently skipped | Trading Codex (cloud) | 2026-10-06 | this branch, commit `d899d49` — 7 new tests, 276/276 total, ruff+mypy clean. See `docs/CHECKPOINT.md` section 25 |
| Built + honestly validated `BollingerReversion` mean-reversion strategy for `Regime.RANGE`; result NO-GO (real economic cause identified, not just insufficient data) | Quant/Strategy (cloud, `session_013NRgckXg3s5ATkCcrUe6KN`) | 2026-10-06 | this branch — 21 new tests (321/321 total on the merged branch), ruff+mypy clean. See `docs/CHECKPOINT.md` section 28 |

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
| **SUPERSEDES the row above's "set by Trading Claude-Work" clause.** `DRAWDOWN_HALT_PCT=15.0`, 30-day rolling peak (not all-time), 8% pause tier w/ auto-resume (still needed, not yet built), 60s connectivity watchdog (still needed, not yet built), `equity_mtm()`=ticker/last-price (confirmed) — all ratified by Claude, not Trading Claude-Work | Owner explicitly moved this named set of decisions to Claude while Trading Claude-Work is paused on its own usage limit ("RESUELVE TÚ LAS DECISIONES TÉCNICAS/RISK-POLICY..."), because the project cannot stall on an unavailable agent. Every number traces to the project's own `docs/RISK_ENGINE_SPEC.md` (PR #1, Trading Claude-Work's own spec), not invented by Claude. Full rationale per item in `docs/RISK_POLICY_DECISIONS_2026-10-06.md`. | 2026-10-06 | Claude (project leader), under explicit owner authorization |
| PR #4 (MARKET lot/dust contract) fill-semantics quant sign-off, previously deferred to Trading Claude-Work | Same owner authorization as above; reviewed twice independently with no bugs found either time (PR #4 review 2026-10-05, re-verified 2026-10-06) | 2026-10-06 | Claude (project leader), under explicit owner authorization |

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
| PR #3/#4/#5 merge chain | Claude Code local — fix the watchdog `ultimo_ok IS NULL` bug (verified fix ready, see Active Tasks), then open a formal PR for `claude-code/finding-3-persistent-halt` | Risk/quant sign-off and the drawdown-policy implementation are both done; only the bug fix + PR remain |
| ~~Four risk-policy decisions on Finding 3~~ — **RESOLVED 2026-10-06**, decided by Claude under explicit owner authorization (Trading Claude-Work still paused on its own usage limit) | — | All four answered in `docs/RISK_POLICY_DECISIONS_2026-10-06.md`, and implemented in commit `1533690` (pause tier, watchdog, 30-day rolling peak all built, not just the config value). |
| SHADOW mode on the real runtime (owner directive items 7-8) | Claude Code local (see Active Tasks) | Designed in `docs/SHADOW_MODE_AND_CONTINUOUS_RUNNER_DESIGN.md`; cloud session has no network to Binance and doesn't own these files, so it can't implement or test this itself |
| Binance API keys | Owner provides (env vars), not urgent | Cannot test live connectivity or download real historical data — not requested yet |
| XM/MetaTrader API access | Owner provides credentials | Phase 2, not blocking current work |

## Next Available Work

1. **Claude Code local**: (a) apply `DRAWDOWN_HALT_PCT=15.0` to `config.py` on `claude-code/finding-3-persistent-halt` (fully specified above and in `docs/RISK_POLICY_DECISIONS_2026-10-06.md` §1 — Trading Codex's own attempt was sandbox-blocked, not a sign-off gap); (b) open a formal PR against `codex/market-lot-contract` for that branch now that Finding 2/3 are signed off; (c) build the 8% pause tier and 60s connectivity watchdog (design pointers in the same doc, §3-4); (d) still open from before: integrate `execution_market_filters.py` with `paper_fills.py`/`paper_store.py` per PR #4's own checkpoint note.
2. **Trading Claude-Work** (paused on its own usage limit, not a project blocker): the four risk-policy decisions that were previously assigned here are now resolved (by Claude, under owner authorization) — nothing outstanding is waiting on this agent specifically anymore; welcome to review/countersign `docs/RISK_POLICY_DECISIONS_2026-10-06.md` when back online, but the project does not wait on that.
3. **Trading Codex (either)**: once PR #3→#4→{#5, finding-3-halt} merge, re-run `pytest tests/` to confirm `trading_intelligence/` still passes untouched.
4. **Whoever syncs Notion**: Task Board, BLOCKERS (`RISK-POLICY-F3-THRESHOLDS` should move from BLOCKED to RESOLVED), and AGENTS rows need a refresh reflecting this ratification — see Current Work below.


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


## GPT Work independent cross-review — observed 2026-10-06T13:17Z

Claim: issue #2 comment6015968160. Function: operations/cross-review; tools: GitHub + Notion connectors, local isolated Python/Node. Permissions: review fixtures, own review files and operational records; no edits to local-owned runtime/city branches, no financial activation. Inputs pinned: halt1533690, city7913bb0, shareddea892f. Output: executable acceptance checks and evidence in `docs/checkpoints/GPT_WORK_CROSS_REVIEW_2026-10-06.md`.

- Watchdog: 8 acceptance tests,4PASS/4FAIL; includes NEW rollback-of-valid-valuation defect on duplicate rejection (issue2 comment6017057938), plus known NULL/init/release gaps. Claude Code Local retains correction ownership; Claude Leader decides integration.
- Agent City: original12model tests PASS;4new acceptance tests yield1PASS/3FAIL (future snapshot/event and snapshot WORKING without event). Local retains ownership, no second frontend.
- DONE criterion for implementation: acceptance suites + existing suites passing, reject atomicity preserved, no invented activity. Review delivery itself can complete with reproducible failures; runtime is NOT certified.
- MINA integration contract/path not recovered yet; asked Leader/Local via issue2 comment6017105964 for nonsecret handoff, not a new provider or keys. GitHub code search incomplete; no claim that integration is absent.
- Notion Mission Control synchronized; old GPT-Work-paused/threshold-pending/city-module-missing summaries superseded by evidence above.
