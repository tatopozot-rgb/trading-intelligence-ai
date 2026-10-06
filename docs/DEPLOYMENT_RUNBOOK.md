# Deployment Runbook — Trading Intelligence AI

> Author: Trading Codex (cloud session)
> Status: LIVING DOCUMENT — reflects the research package (`trading_intelligence/`) today;
> must be reconciled with the real PAPER system's own operational docs
> (`ENTORNO_Y_DIAGNOSTICO.md`, `CONTINUAR_CON_CLAUDE.md`) once PR #3/#4/#5 merge.
> This is operational reference, not a roadmap — it describes how to run and
> recover the system as it exists now.

## Modes

| Mode | Moves money? | Sends real orders? | Config |
|------|-------------|---------------------|--------|
| **PAPER** | No | No (simulated fills) | Default. `BinanceSpotAdapter` used read-only for market data; `PaperAdapter` simulates fills. |
| **DRY_RUN** | No | No (validated, logged, never sent) | Wrap any real adapter in `DryRunAdapter`. Exercises real auth/connectivity/filters end-to-end. |
| **LIVE** | **Yes** | **Yes** | Requires `LIVE_ACTIVATION_APPROVAL` from the owner. Not available until that gate is explicitly granted. |

There is no code path from PAPER or DRY_RUN to LIVE without a human
explicitly swapping the adapter — no config flag silently escalates.

## Environment Variables

| Variable | Required for | Notes |
|----------|---------------|-------|
| `BINANCE_API_KEY` / `BINANCE_SECRET_KEY` | Trading/account endpoints only | Public market data (klines, ticker, ping) needs none — see `docs/BINANCE_INTEGRATION_NOTES.md`. **Spot & Margin Trading + Read Info only. Withdrawals permission must NEVER be enabled.** |
| `BINANCE_TESTNET` | Optional | `"true"`/`"false"`; defaults to constructor arg if unset. |
| `BINANCE_BASE_URL` | Optional override | For testnet/alternate endpoints. |

Never commit these to the repository. `tools/check_repository.py` (real
system) scans for this; `trading_intelligence/` has no equivalent yet —
rely on `.gitignore` and manual review until one exists.

## Startup Sequence (`trading_intelligence/` adapters)

1. Construct `BinanceSpotAdapter()` — safe with or without credentials.
2. For public-data-only use (backtesting, the downloader): call methods
   directly, no `connect()` needed.
3. For live/account use: call `.connect()` — this requires credentials,
   pings, syncs server time, loads exchangeInfo, verifies SPOT permission.
4. Construct `RiskEngine(config, state_path, audit_log)` — on startup, if
   persisted state shows `kill_switch=True`, it starts halted. This is
   correct; do not "fix" it by deleting the state file.
5. For PAPER: wrap the connected adapter in `PaperAdapter(market_data_adapter=adapter, ...)`.
   For DRY_RUN: wrap it in `DryRunAdapter(live_adapter=adapter)` instead.
6. Every order must go through `RiskEngine.validate_order()` before reaching
   either wrapper — neither wrapper re-implements risk checks.

## Restart / Crash Recovery

- `RiskEngine` state (`RiskState`) persists to disk as JSON with atomic
  write-then-rename — a crash mid-write leaves the previous valid state
  intact, never a half-written file.
- `PaperAdapter` state (cash, positions) persists the same way, same guarantee.
- On restart: both reload from their state files automatically on
  construction. If `kill_switch` was active, it stays active — clearing it
  requires `RiskEngine.clear_kill_switch(operator_confirmation=True)`, an
  explicit human action, never automatic.
- If a state file is missing or unreadable: `RiskState.load`/`PaperAdapter`
  constructors start from defaults rather than crashing — on a real
  deployment, treat an unexpectedly-missing state file as an incident to
  investigate (was it deleted? disk issue?), not a routine restart.

## Audit Trail

`AuditLog` (`trading_intelligence/persistence/audit_log.py`) writes
append-only JSONL, rotated daily (`audit_YYYY-MM-DD.jsonl`), one line per
risk decision (approve or reject) with full context (equity, drawdown,
daily P&L, reason code). Never delete or edit these files; if a decision
looks wrong, it is investigated from the log, not altered.

## Known Gaps Before LIVE Can Be Considered (tracked, not exhaustive)

- Real system's `risk_engine.py`/`paper_store.py` (the authoritative
  implementation) does not yet have automatic drawdown pause/halt or a
  connectivity-watchdog kill switch — only the manual `PAUSA_ENTRADAS` file
  switch. See PR #3 review Finding 3. `trading_intelligence/risk/engine.py`
  has these; the two implementations are not yet reconciled.
- No strategy has passed full out-of-sample validation per
  `docs/STRATEGY_VALIDATION_FRAMEWORK.md` — "do not trade" remains correct
  until one does.
- XM/MetaTrader adapter is Phase 2, not started.
- **Alerting**: `trading_intelligence/monitoring/alerts.py` gives `RiskEngine`
  a pluggable `AlertSink` (kill switch, drawdown halt/pause, daily-loss
  limit all fire through it). Default `LoggingAlertSink` only writes to
  logs — no real notification channel (Slack/email/SMS) is wired in yet.
  Swap in a real sink (and the real system's `risk_engine.py`, once
  reconciled, should get the same mechanism) before unattended LIVE operation.
- `DryRunAdapter` and `ShadowRunner` exist in `trading_intelligence/` only;
  the real system's own `broker_adapters.py`/`execution_context.py` have no
  equivalent wrapper yet.

## Rollback

- Reverting to a previous commit/branch is always safe for `trading_intelligence/`
  — it has no running state outside the JSON/JSONL files described above,
  which are forward-compatible (older code reading newer state files
  ignores unknown fields; this has not yet been tested against a real
  schema change, so treat any `RiskState`/`PaperAdapter` schema change as
  requiring a migration note here).
- The real system's SQLite database (`trading.db`) is the harder rollback
  case: a code rollback does not roll back the database. Any schema change
  there needs its own migration plan before deployment — not yet written.
