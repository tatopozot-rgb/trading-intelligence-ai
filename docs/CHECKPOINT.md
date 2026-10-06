---
type: checkpoint
tags: [trading-intelligence, checkpoint]
status: living
aliases: ["Checkpoint"]
---

# Checkpoint — Trading Intelligence AI

> Last updated: 2026-10-06T04:00:00Z
> Agent: Trading Codex (cloud session)
> Branch: `ccr-b66a9a9e-okj2pl` @ commit `5e101ad`
> PRs: #1 (specs, open), #3 (real PAPER import, open, NOT merged), #4 (MARKET lot contract, open, NOT merged), #5 (is_junction fix, open, NOT merged), #6 (Agent City handoff, MERGED)
> Other branches: `claude-code/finding-3-persistent-halt` (Claude Code local, Finding 2/3 implemented, reviewed, no PR yet)

## IMPORTANT — corrected project objective (2026-10-06)

**PAPER, backtesting, walk-forward, and shadow validation are internal
validation gates, not the destination.** The goal is a complete,
production-ready, deployable system. See the "Project Goal" section at the
top of `AGENTS.md` for the full statement. In practice this means: once
PAPER is validated enough, continue immediately into LIVE-readiness
infrastructure (real adapters, dry-run, shadow mode, deployment prep) —
never stop at "PAPER works." The only human gate before real trading is a
single `LIVE_ACTIVATION_APPROVAL` ask, made once, only when architecture,
risk, quant validation, security, tests, CI, crash recovery, and
cross-agent review are genuinely all done. We are not there yet — PR #3
Findings 2/3 are still open and no strategy has passed out-of-sample
validation.

## IMPORTANT — three-agent structure (corrected nomenclature)

Per explicit owner correction, there are exactly **three** agents on this
project — see `AGENTS.md` for the permanent definition:
1. **Trading Claude-Work** — the real ChatGPT Work agent (cross-review, architecture, risk, quant, Notion Mission Control). Any older doc saying "Trading claude work" (lowercase, no hyphen) means this same agent, never a plain chat session.
2. **Trading Codex** (this agent) — cloud container (`/home/user/trading-intelligence-ai`), **no access to the owner's local Windows PC**.
3. **Claude Code local** — runs via PowerShell on the owner's PC, has real access to `C:\Users\tatop\trading-ai`. Did the actual codebase import (PR #3) and the MARKET lot/dust contract (PR #4).

GitHub is the shared source of truth between all three. Check PR/issue state
before assuming what another agent has or hasn't done.

## Current State

**Phase**: REVIEW — real PAPER runtime imported via PR #3, cross-reviewed, not yet merged.
**Status**: Two parallel, non-conflicting bodies of code now exist on this branch:
1. `trading_intelligence/` — a research/backtesting package built from the specs in PR #1 (indicators, strategy, backtest engine, **and now a full RiskEngine + PaperAdapter + BinanceSpotAdapter skeleton**, built independently before PR #3's existence was known to this session).
2. The **real PAPER system** (root-level flat modules: `risk_engine.py`, `paper_store.py`, `paper_fills.py`, etc.) — sitting on branch `codex/import-paper-baseline`, proposed via PR #3 against this branch. **This is the authoritative system per explicit owner instruction** ("el programa real existente es la autoridad"). `trading_intelligence/` should be treated as a reference/validation harness, not a replacement.

## What Was Done This Session (Trading Codex — cloud)

### 1. Risk/execution layer for `trading_intelligence/` (built before PR #3 was discovered)
- `trading_intelligence/risk/models.py` — `RiskConfig` (validated at construction), `RiskState` (JSON-persisted, atomic write)
- `trading_intelligence/risk/engine.py` — `RiskEngine`: full 11-step validation per `docs/RISK_ENGINE_SPEC.md` (kill switch, daily loss halt, drawdown pause/halt, stop validation, fixed-fractional sizing, position/exposure/correlated-exposure limits), connectivity watchdog, audit logging
- `trading_intelligence/persistence/audit_log.py` — append-only JSONL audit log, daily rotation
- `trading_intelligence/execution/base.py` — `AbstractExchangeAdapter` interface
- `trading_intelligence/execution/order_models.py` — `OrderRequest`, `OrderResult`, `Position`, `AccountInfo`
- `trading_intelligence/execution/paper.py` — `PaperAdapter`: wraps a market-data adapter, intercepts orders, next-bar fills (MARKET/LIMIT/STOP with gap-through slippage), position accounting, state persistence
- `trading_intelligence/execution/binance.py` — `BinanceSpotAdapter` skeleton: lazy client construction, lot/tick/notional filter rounding, credential-gated (raises `BinanceCredentialsMissing` cleanly when no API keys — never crashes construction)
- 60 new tests (`test_risk_engine.py` ×30, `test_paper_adapter.py` ×12, `test_binance_adapter.py` ×18), all passing
- Fixed a real bug found via these tests: RSI formula produced NaN when all bars are gains (division by zero avg_loss) — now correctly returns RSI=100
- Fixed a real infinite-loop bug in `PaperAdapter.on_new_bar`: mutating `self.pending_orders` while iterating it
- Fixed a real bug where STOP orders were filling unconditionally through the generic MARKET/LIMIT path instead of only via gap-through stop-trigger logic
- `pyproject.toml` (ruff + mypy config), `.github/workflows/research-tests.yml` (ubuntu-latest, pytest+ruff+mypy, triggers on `trading_intelligence/`/`tests/` changes only)
- **92/92 tests passing, ruff clean, mypy clean** on the full `trading_intelligence/` package

### 2. Discovered and audited PR #3 (real PAPER system import)
Posted a full cross-review on PR #3 (see GitHub). Independently reproduced on Linux
(the import was done/tested on Windows):
- **549/558 tests reproduced** in 14.7s on Linux, Python 3.11, fresh `pip install pandas requests`
- **No secrets found** (independent grep confirms their own scan)
- Confirmed `trading_intelligence/`, `tests/`, `pytest.ini`, `requirements.txt`, `pyproject.toml` are **untouched** by PR #3 — no conflict
- Confirmed: no martingale, no risk-escalation-after-loss anywhere in the real sizing/re-entry logic
- Confirmed: SQLite `BEGIN IMMEDIATE` transactions throughout `paper_store.py` give real atomicity/crash-recovery; UUID + plan-hash gives idempotency against duplicate/replayed requests
- Confirmed: manual file-based kill switch (`PAUSA_ENTRADAS`) correctly blocks only new entries, not existing positions
- **Finding 1 (trivial, not blocking)**: `tools/check_repository.py::_linked()` calls `Path.is_junction()`, which doesn't exist on `PosixPath` → 14 test errors on Linux (all isolated to the new safety-guard tool, zero impact on trading logic or their actual Windows CI)
- **Finding 2 (needs a decision, not blocking this PR)**: `docs/RISK_ENGINE_SPEC.md` specifies daily-loss reset at 00:00 UTC; the real code (`paper_store.asegurar_dia`) resets on local UTC-5 day boundary. Needs explicit sign-off — either the spec or the code should change, not silently diverge.
- **Finding 3 (real gap vs spec, not previously flagged by either session)**: no automatic drawdown pause/halt (8%/15% equity-peak per spec) and no connectivity-watchdog auto-kill-switch (>60s per spec) exist in the real system — only the manual file-based kill switch. This is genuine unimplemented spec coverage, distinct from the already-known MARKET/quoteOrderQty/lot/dust gap.
- **Did NOT merge PR #3** — Issue #2's checklist isn't fully checked yet and the PR's own checkpoint says "address findings before merge." Left for cross-review resolution (Finding 2 in particular needs Trading Claude-Work's input per AGENTS.md: "Risk engine changes require review from Trading Claude-Work").
- Posted one comment on Issue #2 flagging that the actual local-PC import (criterion 1 of the issue) is something this cloud session cannot do itself — not repeating that per the WAITING_FOR_USER rule.

### 3. Documentation correction
- My own Session 2 test count breakdown had an arithmetic bug: wrote "21/21" for indicators when it's actually 20 (20+7+5=32, matching the stated 32 total — the total was always right, only the per-file line was wrong). Corrected below.

### 4. Discovered, reviewed, and fixed PR #4 and opened PR #5 (second session block, same day)
- **PR #4** (`codex/market-lot-contract`, stacked on PR #3, by Claude Code local): adds `execution_market_filters.py` — offline MARKET lot/dust contract, fail-closed (rejects `quoteOrderQty` outright, requires both `MARKET_LOT_SIZE` and `LOT_SIZE`, rejects `MIN_NOTIONAL`/`NOTIONAL` unless explicitly flagged as not applying to MARKET). 16 new tests.
  - Independently reproduced on Linux: 565/574 tests (549+16; the 9-test gap is the same already-documented Tkinter/Windows-only platform gap from the PR #3 review, not a new regression).
  - Read the full 104-line module: no bugs found. Correctly cites what official Binance docs do and don't confirm (quoteOrderQty semantics and LOT_SIZE-on-MARKET applicability are explicitly left unverified/conservative, matching their own docstring).
  - Confirmed it does NOT touch `risk_engine.py`, `paper_store.py`, `paper_fills.py` — orthogonal to PR #3 Findings 2/3, which remain open and still block the final merge per Issue #2.
  - Posted a COMMENT review on GitHub: no changes requested; final semantic sign-off left to Trading Claude-Work per AGENTS.md review protocol.
- **PR #5** (`codex/fix-is-junction-linux`, stacked on PR #4, opened by this agent): fixes Finding 1 from the PR #3 review — `tools/check_repository.py::_linked()` called `Path.is_junction()`, which doesn't exist on `PosixPath` (Windows-only, Python ≥3.12 only). One-line `getattr` guard. Verified: 14 errors → 0 on Linux; only 2 residual failures remain, both pure environment gaps (no tkinter installed in this container), unrelated to the fix. Opened as its own PR (not pushed directly to PR #3/#4's branches) to respect the no-simultaneous-edit rule, since those branches are owned by Claude Code local.

### 5. Fixed a real bug in BinanceSpotAdapter + built the historical data downloader
- **Bug found and fixed**: `BinanceSpotAdapter` required credentials for *every* operation, including `get_current_price`, `get_ohlcv`, `is_connected` — but `docs/BINANCE_INTEGRATION_NOTES.md` explicitly states klines/ticker/exchangeInfo/ping are public, no API key needed. Only account/trading endpoints should require credentials. Fixed: `_get_client()` no longer requires credentials to construct; `submit_order`, `get_position`, `get_account_info` now explicitly call `_require_credentials()`; `is_connected()` and the new `verify_public_connectivity()` work with zero credentials. Updated/added tests accordingly (22 tests in `test_binance_adapter.py`, up from 18).
- **`trading_intelligence/data/downloader.py`** — `HistoricalDataDownloader`: downloads and caches OHLCV to Parquet (`data/historical/{symbol}/{interval}/{YYYY-MM}.parquet`), paginates the public klines endpoint by close-time per `docs/BINANCE_INTEGRATION_NOTES.md`'s example, never re-downloads a cached month unless `force=True`, de-duplicates overlapping bars. Uses `BinanceSpotAdapter` with **zero credentials** (public data only — consistent with the owner's explicit instruction not to request Binance API keys).
- 11 new tests (`test_downloader.py`), all mocked (no real network calls): caching, forced re-download, pagination by close-time, empty-response handling, no-duplicate-bars, multi-month range spanning, missing-cache error.
- **107/107 tests passing, ruff clean, mypy clean** on the full `trading_intelligence/` package (up from 92).
- **Nomenclature correction** (this update): per explicit owner correction, rewrote `AGENTS.md` to define exactly three agents (Trading Claude-Work = real ChatGPT Work, Trading Codex = this agent, Claude Code local = PowerShell session on the owner's PC) and corrected all "Trading claude work" references in this file and `docs/AGENT_COORDINATION.md` to "Trading Claude-Work".

### 6. 8-hour checkpoint session: found and fixed a real correctness bug, built the report generator
No new activity from PR #3/#4/#5 or Issue #2 since the last session (all SHAs unchanged) — nothing new to review there. Used the time for independent engineering work that doesn't touch files claimed by the other two agents:

- **Bug found and fixed**: `BacktestEngine._stop_fill_price()` always filled stop-outs at `stop_price * (1 - 2x slippage)`, even on a real gap-down where the bar's open itself was already below the stop. This understates losses on exactly the trades that matter most (crashes) — the kind of backtest optimism `docs/PAPER_TRADING_SIMULATION_SPEC.md`'s "Core Principle: Pessimistic Assumptions" explicitly warns against. My own `PaperAdapter` already had the correct gap-through logic (fill at the bar's open when it gapped below the stop); `BacktestEngine` didn't match it. Fixed `_stop_fill_price()` to take `bar_open` and use it when the bar gapped through.
- Added two deterministic, exact-price tests (`TestStopFillEdgeCases` in `test_backtest_engine.py`) using a new `_FixedSignalStrategy` test double that fires one controlled signal at a chosen bar — not random synthetic data. One proves a normal stop touch on the entry bar itself fills at `stop*(1-2x slippage)`; the other proves a real gap-down fills at the bar's open, and is **off by ~25 points** from the old (wrong) formula on the test's numbers — this is the magnitude of optimism the bug was producing.
- **`trading_intelligence/backtesting/report.py`**: CSV export (`write_csv_report` — trades.csv, equity_curve.csv) and a self-contained HTML report (`generate_html_report`/`write_html_report`) with an inline-SVG equity curve — no new dependencies (no matplotlib/plotly, consistent with the project's minimal-dependency style). The HTML report always carries an explicit disclaimer pointing to `docs/STRATEGY_VALIDATION_FRAMEWORK.md` — it must never read as a profitability claim.
- 11 new tests (`test_report.py`): CSV round-trip, HTML structure, HTML-escaping (XSS safety on the title), empty-trades/empty-equity-curve edge cases.
- **120/120 tests passing, ruff clean, mypy clean** (up from 107).

### 7. First LIVE-readiness infrastructure, per the corrected objective (same session, continued)
- **`trading_intelligence/execution/dry_run.py`** — `DryRunAdapter`: wraps any real `AbstractExchangeAdapter` (e.g. `BinanceSpotAdapter`). All read-only methods (market data, account info, position, connectivity) pass through to the wrapped adapter — so auth, connectivity, and real market data genuinely get exercised. `submit_order`/`cancel_order` are intercepted: validated against the wrapped adapter's own exchange-side filters (lot size, tick size, min notional, when available — degrades gracefully if the wrapped adapter has none) and logged, but **never forwarded**. This is the execution gate for "build and test everything that doesn't move money" — not a replacement for `RiskEngine` approval, which must still happen upstream.
- Added `"DRY_RUN"` to the shared `OrderStatus` type (`execution/order_models.py`) so a dry-run result is never mistaken for a real `SUBMITTED` order.
- 15 new tests (`test_dry_run_adapter.py`): read-only passthrough, order-never-forwarded (asserts the wrapped adapter's `submit_order` raises if ever called), every exchange-side rejection reason, graceful degradation when the wrapped adapter has no filter helpers at all.
- **`docs/DEPLOYMENT_RUNBOOK.md`** (new): modes (PAPER/DRY_RUN/LIVE) and how code never silently escalates between them, required env vars, startup sequence, restart/crash recovery guarantees (atomic state writes, kill-switch persistence), audit trail policy, known gaps before LIVE can be considered, rollback notes (including that the real system's SQLite DB is the harder rollback case — no migration plan exists yet).
- Updated `AGENTS.md` with the corrected project objective at the top, so Trading Claude-Work and Claude Code local see it on their next read.
- **135/135 tests passing, ruff clean, mypy clean** (up from 120).

### 8. ShadowRunner — the other half of "implement shadow mode" (same session, continued)
- **`trading_intelligence/execution/shadow.py`** — `ShadowRunner`: runs the real strategy and the real `RiskEngine` against REAL current market data (via `get_ohlcv`/`get_current_price` — public, no credentials), and records what the system WOULD have decided. Distinct from `PaperAdapter` (simulated fills on historical/replay data) and from `DryRunAdapter` (validates a constructed order against exchange filters) — `ShadowRunner` never constructs an `OrderRequest` or calls any order method at all. Equity is supplied by the caller via an `equity_fn` callable (no real account query), so it works identically whether backed by a real funded account later or a configured notional baseline now.
- 8 new tests (`test_shadow_runner.py`), including an adapter that raises `AssertionError` if `submit_order`/`cancel_order`/`get_position`/`get_account_info` are ever called — proving `ShadowRunner` only ever touches public market data, and one proving `equity_fn` is actually wired through to the real `RiskEngine`'s position sizing (larger equity -> larger approved quantity).
- **143/143 tests passing, ruff clean, mypy clean** (up from 135).
- Both halves of "shadow mode" named in the corrected objective are now built in `trading_intelligence/`: `DryRunAdapter` (exchange-side order validation, never sends) and `ShadowRunner` (strategy+risk decisions on live data, never constructs an order at all). Neither exists yet in the real system — porting them is listed under Next Available Work.

### 9. Alerting for critical risk events (closes a documented gap, same session, continued)
- **`trading_intelligence/monitoring/alerts.py`** — `AlertSink` protocol, `LoggingAlertSink` (default — always available, no credentials, no new dependency), `CompositeAlertSink` (fan out to multiple sinks; one sink failing — caught and logged — never blocks the others, so an alerting bug can't silence every channel), `NullAlertSink` (for tests).
- Wired into `RiskEngine` (`alert_sink` constructor param, defaults to `LoggingAlertSink()`): fires `CRITICAL` on kill-switch activation (manual, connectivity-loss, config-startup, and drawdown-halt all funnel through the single `_set_kill_switch` choke point) and on `DRAWDOWN_HALT_TRIGGERED`; fires `WARNING` on `DRAWDOWN_PAUSE_TRIGGERED` and `DAILY_LOSS_LIMIT_REACHED` — each exactly once per trigger, not re-fired on every subsequent call while the condition persists.
- 14 new tests (`test_alerts.py`) proving each exact firing condition, no double-firing, and that a real notification channel (Slack/email/SMS) can be swapped in later purely by implementing `AlertSink` — `RiskEngine` itself never has to change again.
- **157/157 tests passing, ruff clean, mypy clean** (up from 143).
- Updated `docs/DEPLOYMENT_RUNBOOK.md`'s Known Gaps accordingly: alerting now has a real pluggable mechanism (still logging-only by default — no Slack/email/SMS wired in yet, that remains the actual gap before unattended LIVE operation).

### 10. Crash-simulation tests — "simulación de fallos; crash/restart test" from the final checklist (same session, continued)
- **`tests/test_crash_recovery.py`** (5 tests): directly simulates the exact crash window the atomic write pattern (write `.tmp`, then `rename`/`replace`) exists to protect against — writes corrupt/truncated content to the `.tmp` file and confirms the real state file is completely untouched, loads cleanly, and `RiskEngine`/`PaperAdapter` recover their last-good state on a simulated restart. Also confirms a stray leftover `.tmp` from a previous crash doesn't interfere with the next successful save, and that a genuinely-missing state file (first-ever cold start) is handled as the normal case, not an error.
- This is a different (stronger) claim than the existing happy-path save/load round-trip tests already in `test_risk_engine.py`/`test_paper_adapter.py` — those prove persistence works; these prove it survives the process dying mid-write.
- **162/162 tests passing, ruff clean, mypy clean** (up from 157).

### 11. GPT Work's review arrived; decided Finding 2/3; closed real gaps found along the way (same day, continued)

GPT Work (Trading Claude-Work) posted an independent Finding 2/3 review on
PR #3 (comment 6007551700) and opened PR #6 (an Agent City Notion handoff),
then paused on its own usage limit. None of this blocks the project — per
the owner's explicit instruction, continued autonomously rather than
waiting on either GPT Work or Claude Code local (neither of whom had
produced new commits yet):

- **Decided Finding 2/3's integration path** (PR #3 comment 6007584364):
  preserve the baseline daily-loss contract (UTC-5 cutoff) rather than
  silently adopting the spec's defaults; assigned Finding 2's missing
  tests and Finding 3's persistent-halt implementation to Claude Code
  local, with real thresholds left to Trading Claude-Work. Corrected a
  stale `WAITING_FOR_USER` label on Finding 2 in `AGENT_COORDINATION.md` —
  it was a team decision, never an owner question.
- **Merged PR #6** (GPT Work's handoff): docs-only (`AGENT_CITY_DATA_CONTRACT.md`,
  a GPT Work checkpoint, a coordination addendum), no runtime/financial
  changes, no conflicts with this branch's own edits.
- **`docs/FINDING_3_HALT_DESIGN.md`**: read the real `paper_store.py`/
  `risk_engine.py`/`paper_control.py`/`paper_fills.py`/`market_http.py` on
  `codex/import-paper-baseline` (933642a) read-only via a git worktree (no
  file there touched). Confirms GPT Work's review exactly — `risk_engine.py`
  is only a position-sizing calculator with no kill switch at all; the real
  gate is `paper_store._abrir_validado`, checking only the manual
  `PAUSA_ENTRADAS` file and the daily budget; `obtener_capital_operativo()`
  reads `saldo_actual` (realized cash), never open-position unrealized P&L.
  Gives Claude Code local the concrete `paper_halt` table shape, an
  `equity_mtm()` function using the existing `market_http.precio_actual`,
  and the fail-closed/never-auto-clears requirements — not an
  implementation or a threshold decision.
- **Agent City V1**: published a real-data snapshot dashboard
  (https://claude.ai/artifact/98zjB7JbToV2ernTsjdLKD) per GPT Work's PR #6
  handoff explicitly asking Claude to assign this owner. Built from this
  session's own GitHub/Notion reads; discloses that Notion's bulk query
  hit a workspace usage limit while building it rather than guessing at
  the full Task Board; links out to live sources for anything unverified.
  A snapshot, not a live feed — regenerate it rather than treating it as
  continuously accurate.
- **Obsidian-ready docs**: added YAML frontmatter (type/tags/status/aliases)
  to every doc under `docs/` and a new `docs/INDEX.md` (Obsidian MOC)
  linking them by category. Purely additive — no existing prose, links, or
  structure changed; `[[wikilinks]]` in the index render as harmless plain
  text on GitHub.
- **Found and fixed a real test-coverage gap**: `trading_intelligence/backtesting/walk_forward.py`
  had zero tests — the module that computes go/no-go for the strategy
  validation gate, exactly what `CLAUDE.md` requires tests for. Added 23
  tests: pure `WalkForwardFold`/`WalkForwardReport` aggregation logic
  against hand-built fake results (exact threshold/edge-case coverage,
  independent of what a real backtest happens to produce), plus
  `run_anchored_walk_forward` end-to-end against the real `BacktestEngine`
  + `DualMACrossover` on synthetic data (proves the anchored window
  anchors, the IS<0.5 skip-OOS branch works, `max_folds` bounds the loop,
  and the full pipeline runs together — makes no claim about GO vs NO-GO
  on synthetic data, which would prove nothing about real edge).
- **191/191 tests passing, ruff clean, mypy clean** (up from 168 — 6 for
  `WebhookAlertSink`, 23 for `walk_forward.py`).

### 12. Reviewed Claude Code local's Finding 2/3 delivery; fixed the real bug it found (same day, continued)

Claude Code local delivered on `claude-code/finding-3-persistent-halt`
(stacked on PR #4) — no PR opened yet. Reviewed both commits line-by-line:

- **Finding 3** (`44eb425`): a `paper_halt` singleton table, `equity_mtm()`
  (realized balance + unrealized P&L via the same formula the close path
  uses), `_evaluar_halt()` as the single decision point called from
  `_abrir_validado` (covers the Claude and `REGLAS_PAPER_V1` entry paths
  by construction), fail-closed on missing/corrupt state or an
  unapproved threshold, never auto-clears (`liberar_halt` requires
  explicit confirmation **and** re-verifies the drawdown has actually
  recovered below the threshold — not just the confirmation flag).
  `config.DRAWDOWN_HALT_PCT = None` by design — real risk thresholds stay
  Trading Claude-Work's call, not copied from `trading_intelligence/`'s
  own reference defaults. `test_paper_halt.py` (220 lines) covers every
  scenario the design note asked for, including some I hadn't thought to
  ask for (price failure blocks entry without activating the halt; the
  monitor's own risk-evaluation failure never blocks closing a position).
  **No bugs found.**
- **Finding 2** (same commit): pins the 05:00 UTC daily-loss cutoff and
  that losses count against the local day, preserving the baseline
  contract exactly as decided. **No bugs found.**
- **Real-data research** (`a58437b`): ran `trading_intelligence/`'s
  `DualMACrossover` against real BTCUSDT 1D klines (2019–2026, 2830
  bars) via the real network access this cloud session doesn't have.
  Result: 11 trades (below the 30-trade minimum), 0 walk-forward folds
  (IS Sharpe < 0.5 throughout) — correctly recorded as **NO-GO**, no
  profitability claim. This is also the first real confirmation that the
  walk-forward harness fixed in section 11 actually runs against real
  data, not just synthetic fixtures.
- **Found a real bug in my own code and reported it without touching the
  file**: `HistoricalDataDownloader`'s default adapter inherited
  `BinanceSpotAdapter`'s `testnet=True` default, so the research run
  above originally pulled 28 bars of testnet history instead of the
  requested mainnet range, silently. Fixed now (`ad20161`): the
  downloader's own default is `testnet=False` explicitly, and
  `download_range()` gained a second defense — a large requested range
  (≥180 expected bars) returning under 10% of that is flagged by name as
  the testnet signature rather than silently accepted. 9 new tests.
- **198/198 tests passing, ruff clean, mypy clean** (up from 191).

### 13. Another real gap found the same way: AuditLog didn't match its own docstring (same day, continued)

Same audit pattern that caught `walk_forward.py`: `AuditLog` had no
dedicated test file at all — only incidental coverage via
`test_risk_engine.py`'s one audit-logging test, which exercises
`RiskEngine`'s call site, not `AuditLog`'s own contract. Its `append()`
docstring claimed failures are "re-raised as RuntimeError after being
written to stderr-equivalent" — the code never did either. A raw
`OSError` (disk full, permissions, directory removed) would propagate
unconverted and unlogged, and since `RiskEngine` calls
`audit_log.append()` at both its call sites with no `try`/`except`, that
would have crashed order validation outright with no record that the
audit write even failed. Fixed to match the documented contract exactly:
log at CRITICAL first, then raise `RuntimeError` with the original
`OSError` chained — never silently lost. 15 new tests (round-trip, daily
rotation via the real `append()` path, Decimal/dataclass JSON encoding,
sorted keys, the failure-handling fix itself).
**213/213 tests passing, ruff clean, mypy clean** (up from 198).

### 14. A third real bug, found reading risk/engine.py line-by-line against its own spec (same day, continued)

`validate_order()`'s step 4 does two unrelated checks under one reason
code: whether `stop_price` is set, and whether the resolved
`entry_price` (falls back to `reference_price` for MARKET orders) is
positive. A non-positive `reference_price` — bad feed, data glitch — was
rejected as `REASON_NO_STOP_LOSS_DEFINED`, which is simply false: the
stop *is* defined; the entry/reference price is what's invalid. That
wrong reason would go straight into the audit log, hiding the real cause
from anyone debugging a rejected order afterward. This exact branch had
no test coverage. Added `REASON_INVALID_REFERENCE_PRICE` and 3 tests
(zero/negative reference_price on a MARKET proposal, non-positive
entry_price set directly on a LIMIT-style proposal).
**216/216 tests passing, ruff clean, mypy clean** (up from 213).

### 15. A fourth, more serious bug: PaperAdapter was double-charging the entry fee on every sell (same day, continued)

Continuing the line-by-line audit into `execution/paper.py` against
`PAPER_TRADING_SIMULATION_SPEC.md`. `_apply_sell()` credited cash with
`entry_cost + realized_pnl` instead of the sale's actual proceeds.
`realized_pnl` already subtracts `entry_fee_share` once (correctly);
adding `entry_cost` back on top double-charges that same fee share —
cash ends up under-credited by `entry_fee_share` on **every single
sell**, partial or full. Verified numerically before touching anything:
a realistic $5,000 BTC round trip was off by exactly the entry fee's
dollar amount ($5.00). The one existing test on this path asserted only
`cash > 10000` — far too weak to catch it.

Fixed to the simplest correct form: `cash += proceeds` — the entry cost
was already fully debited at `_apply_buy()`, so there is nothing separate
to "give back" at exit beyond what the sale actually paid out.
`realized_pnl` itself was always correct and is unchanged. Added two
precise tests (full sell, partial sell) that reconcile cash against a
plain buy-then-sell ledger, which would have caught this immediately.

**The same arithmetic error was in `PAPER_TRADING_SIMULATION_SPEC.md`'s
own pseudocode** (it double-subtracted `exit_fee` too) — corrected there
as well, so nothing else gets implemented against the wrong formula.

Checked whether the real PAPER system shares this pattern: it doesn't —
`paper_store.cerrar()` uses a different model entirely (adds net
`resultado_usd` once at close; never debits the full cost basis from
`saldo_actual` at open), so this bug was confined to this research
package. Flagging the spec correction for Trading Claude-Work's eventual
review since it touches a document it authored, even though the fix is
plain arithmetic (verified numerically), not a policy call.

**218/218 tests passing, ruff clean, mypy clean** (up from 216).

### 16. The same double-fee bug, found in the sibling BacktestEngine too (same day, continued)

Once one fill-simulation engine turned out to double-charge the entry
fee, checked the other one for the same pattern — found it.
`BacktestEngine.run()` deducted `entry_fee` from `equity` immediately at
entry, then added `BacktestTrade.pnl` (which already nets out both fees)
at close: every trade in every backtest paid the entry fee twice.
Verified numerically before touching anything (a $1,000 round trip was
short by exactly the entry fee), then confirmed the fix mechanically by
temporarily reintroducing the old line against the new tests — both
failed by exactly the entry fee, then passed once removed.

This one is more consequential than the PaperAdapter fix: it silently
understated every backtest's performance (Sharpe, profit factor, final
equity are all computed from this same equity curve), proportional to
trade count and fee rate — exactly the shape of bug that could fail a
real, viable strategy against `STRATEGY_VALIDATION_FRAMEWORK.md`'s gate
for a reason unrelated to its actual edge.

**This means the BTCUSDT 1D research result in section 12 (11 trades,
Sharpe 0.35, PF 6.91, NO-GO) was computed under the buggy engine.** The
NO-GO conclusion itself is essentially certain to still hold — 11 trades
is already below the 30-trade minimum regardless of what fixing the fee
double-count does to Sharpe/PF — but the exact numbers reported there are
approximate, not the corrected engine's output. Re-running it isn't
urgent (the conclusion doesn't change), but whoever next runs a real
walk-forward should know the engine changed since that run.

Fix: `entry_fee` is no longer deducted from equity at entry;
`BacktestTrade.pnl` (unchanged, already correct) is now the only place
equity moves per trade. `entry_fee` is still stored on the trade for fee
reporting, unaffected. 2 new tests reconciling `final_equity` against a
plain ledger (winning and losing trade).

**220/220 tests passing, ruff clean, mypy clean** (up from 218).

## What's Next

**For whichever agent picks this up next:**
1. **Claude Code local**: Finding 2/3 are implemented and reviewed (section 12) — open a formal PR against `codex/market-lot-contract` when ready, so Trading Claude-Work has something to approve on.
2. **Trading Claude-Work** (currently paused on its own usage limit — not a project blocker): set the real drawdown threshold for `config.DRAWDOWN_HALT_PCT` (not copied from `trading_intelligence/risk/engine.py`'s own defaults) and give final risk sign-off on Findings 2/3 plus PR #4's MARKET contract. This is the only thing left before the PR #3→#4→#5 chain can merge.
3. Once that sign-off lands and the chain merges: decide whether `trading_intelligence/` continues as a parallel research package or becomes the validation/backtesting layer calling into the real system's modules.
4. `trading_intelligence/`'s walk-forward harness has now run once against real BTCUSDT data (section 12, via Claude Code local's network access) — correctly NO-GO on 11 trades. Next real-data work: try shorter timeframes or other candidates for more trades, per Claude Code local's own suggestion — that's Trading Claude-Work's call, not an engineering default.
   **This cloud container still cannot reach `api.binance.com`** — confirmed via the egress proxy status; not a credentials issue. Claude Code local is the right agent for any further real-data runs.
5. LIVE-readiness track (per the corrected objective): the real system's `broker_adapters.py`/`execution_context.py`/`exchange_context.py` have no dry-run or shadow-mode equivalent yet — `trading_intelligence/execution/dry_run.py` (`DryRunAdapter`) and `trading_intelligence/execution/shadow.py` (`ShadowRunner`) are reference designs that could be ported there once the chain merges.
6. Next LIVE-readiness step for whoever picks this up: wire `ShadowRunner` to actually run continuously against live Binance public data (needs an agent with real network access); `trading_intelligence/monitoring/alerts.py` now has a real `WebhookAlertSink` (section 11) — wiring an actual webhook URL still needs the owner to supply one.
7. **Obsidian vault package** prepared in `obsidian-vault-package/` (section 11) — still waiting on Claude Code local to place it in the owner's real vault (this cloud session has no filesystem/Computer Use access to do it directly).

## Blockers

- **PR #3/#4/#5 merge chain**: Finding 2/3 implementation is done and reviewed (no bugs found) — now waiting only on Trading Claude-Work's risk/quant sign-off and a formal PR. Nothing further blocks engineering work in the meantime.
- **Binance API keys not configured** — not required for public market data or PAPER mode; needed only for live trading authorization later (explicitly not requested yet)
- **XM/MetaTrader credentials unknown** — Phase 2, separate adapter, not blocking current PAPER work

## Test Status

**`trading_intelligence/` package: 220/220 tests passing**, ruff clean, mypy clean.
```
tests/test_indicators.py       20/20 PASS
tests/test_ma_crossover.py      7/7  PASS
tests/test_backtest_engine.py   9/9  PASS  (7 + 2 for the entry-fee double-charge fix)
tests/test_risk_engine.py      33/33 PASS  (30 + 3 for the entry/reference-price reason-code fix)
tests/test_paper_adapter.py    14/14 PASS  (12 + 2 for the cash double-fee fix)
tests/test_binance_adapter.py  22/22 PASS
tests/test_downloader.py       18/18 PASS  (11 + 7 for the testnet-default fix)
tests/test_report.py           11/11 PASS
tests/test_dry_run_adapter.py  15/15 PASS
tests/test_shadow_runner.py     8/8  PASS
tests/test_alerts.py           20/20 PASS  (14 + 6 for WebhookAlertSink)
tests/test_crash_recovery.py    5/5  PASS
tests/test_walk_forward.py     23/23 PASS  (new — was 0 before section 11)
tests/test_audit_log.py        15/15 PASS  (new — was 0 before section 13)
```

**Real PAPER system (PR #3, `codex/import-paper-baseline`): 549/558 tests**,
independently reproduced on Linux in 14.7s (14 errors, all the same isolated
`is_junction()` portability bug in the safety-guard tool; 20 skips, likely
Tkinter/Windows-UI tests degrading gracefully on headless Linux).

## Documents Ready for Codex to Implement Against

| Document | Purpose | Priority | Status |
|----------|---------|----------|--------|
| docs/RISK_ENGINE_SPEC.md | RiskEngine | CRITICAL | Implemented in `trading_intelligence/`; real system has a simpler/different variant — see Findings 2/3 |
| docs/PAPER_TRADING_SIMULATION_SPEC.md | PaperAdapter | HIGH | Implemented in `trading_intelligence/`; real system's `paper_fills.py` is more sophisticated (real order-book depth walking, not flat bps) |
| docs/BINANCE_INTEGRATION_NOTES.md | BinanceSpotAdapter | HIGH | Skeleton implemented in `trading_intelligence/`, credential-gated |
| docs/SYSTEM_ARCHITECTURE.md | Module structure | HIGH | `trading_intelligence/` follows it; real system uses a flat-module layout instead |
| docs/XM_METATRADER_INTEGRATION.md | XM adapter (Phase 2) | MEDIUM | Not started |
| docs/STRATEGY_VALIDATION_FRAMEWORK.md | Backtest framework | HIGH | Walk-forward implemented in `trading_intelligence/` |
| docs/INITIAL_STRATEGY_CANDIDATES.md | Strategy order | MEDIUM | MA Crossover implemented |

## Code Integration Notes

- `trading_intelligence/strategy/models.py`'s `RiskDecision` stub now has a real counterpart: `trading_intelligence.risk.engine.RiskEngine.validate_order()` returns it populated.
- Before merging PR #3, re-run the full `trading_intelligence/` test suite (`pytest tests/ -v`) to confirm it still passes untouched (it should — PR #3 doesn't touch those paths).
- Do not assume the real system's `risk_engine.py` and `trading_intelligence/risk/engine.py` are interchangeable — they implement different (and currently diverging) policies. Reconcile per Findings 2/3 before treating either as final.
