---
type: design
tags: [trading-intelligence, shadow-mode, runner, risk-engine]
status: ready-for-implementation
---

# SHADOW mode on the real runtime, and the continuous PAPER/SHADOW runner

> Written by Claude (project leader) in response to the owner's explicit
> "UNBLOCK TRADING OPERATIONS" directive, items 7-8 (port SHADOW to the
> real runtime; prepare the PAPER/SHADOW runner for continuous execution
> with the architecture's required control/confirmation). Grounded by
> reading the real system's actual files read-only (git worktree of
> `claude-code/finding-3-persistent-halt`, removed after reading) — not
> written blind. This cloud container has no network path to
> `api.binance.com`, so this is a design handoff to whoever can actually
> run and test it against live market data (Claude Code local), the same
> pattern as `docs/FINDING_3_HALT_DESIGN.md`.

## Important finding first: NO_LIVE is still architecturally true, not just policy

Read `broker_adapters.py` end to end. Its own docstring: *"Lectores PAPER
de snapshots explícitos. Sin transporte, terminal ni órdenes."* Every
adapter capability dataclass (`CapacidadesPaper`) hard-codes
`envia_ordenes: bool = field(default=False, init=False)` — there is no
code path anywhere in the real system that can send a live order. LIVE
isn't just gated by config; it doesn't exist yet as code. This item list
does not ask to build it, and nothing below adds it.

## Item 8 first, because it changes what item 7 needs to do

`system_runner.py --continuo` already is a mature continuous PAPER
runner with real control/confirmation machinery:

- `instancia_unica()`: OS-level file lock (`fcntl`/`msvcrt`), so two
  runners can never run against the same `trading.db` at once.
- `validar_arranque()`: refuses to start unless
  `paper_report.informe()['estado'] == 'OK'` — a real reconciliation
  check, not a rubber stamp.
- `PARADA` file + `--detener`/`--reanudar`: an explicit, file-based stop
  signal that survives process restarts, and requires an explicit
  `--reanudar` to clear (not an automatic retry).
- `cancelacion_sesion(...)`: a second, session-scoped cancellation path
  independent of the global `PARADA` file.
- `finalizar_trabajadores(...)`: protects shutdown from a second Ctrl+C,
  waits for the monitor thread and scanner pool to actually finish before
  returning, and still writes a final status file even if the shutdown
  itself hits an error.
- `Salud` (health) snapshotting into an atomically-written
  `runner_status.json` on every loop tick.

**This already satisfies "the control/confirmation the architecture
requires" for continuous PAPER execution.** Item 8 is not "build a
runner" — it's "give SHADOW the same runner, not a separate one," so
SHADOW inherits every one of the guarantees above for free instead of
duplicating (and potentially under-building) them.

## Item 7: what SHADOW actually needs to be

Per `trading_intelligence/execution/shadow.py`'s already-built reference
(`ShadowRunner`): run the full real decision pipeline — market data →
scanner → strategy → risk engine — and log exactly what *would* have
happened, but never take the state-mutating action. The real system's
exact injection point for this, found by reading the pipeline end to end:

```
trading_scanner.ejecutar_scanner()
  -> paper_rules.procesar_candidatos(resultados, sesion_activa)
       -> store.registrar_solicitud(plan, ...)      # records the request — fine, not a position
       -> store.ejecutar_reglas(identidad, digest, precio, ...)   # <-- THE state-mutating call
```

`store.ejecutar_reglas(...)` is the one function that actually runs
`risk_engine`'s decision and, if approved, writes a row into
`paper_trades`/`paper_account` (opens a real PAPER position). Everything
before it — the scanner, candidate generation, `registrar_solicitud` — is
already side-effect-free with respect to positions.

**Proposed shape** (for Claude Code local to implement and test against
real data — this cloud session cannot):

1. Add `store.ejecutar_reglas_shadow(identidad, digest, precio, sesion_activa, **kwargs)`,
   a sibling of `ejecutar_reglas` that:
   - Runs the exact same risk-engine evaluation (`_evaluar_halt`,
     `evaluar_riesgo`, position sizing) — SHADOW must see the same halt/
     pause/connectivity-watchdog gates PAPER sees, not a relaxed copy.
     Reuse the decision code directly; do not fork it.
   - On approval, instead of inserting into `paper_trades`/`paper_account`,
     writes a row into a new `paper_shadow_decisions` table (or reuses
     `paper_events` with a `SHADOW_ABRIRIA`/`SHADOW_RECHAZADA` event type —
     prefer reusing `evento()`'s existing audit path over a new table
     unless Claude Code local judges a queryable table is worth the
     migration) capturing: symbol, side, sizing, entry price, stop,
     the risk engine's reason code, and whether the halt/pause was active
     at decision time.
   - Never calls anything that mutates `paper_trades`, `paper_account`,
     or `paper_halt`'s `activo`/`pico_equity` fields. It MAY still feed
     `_evaluar_halt`'s own bookkeeping (the `ultimo_ok`/rolling-peak
     history) if and only if PAPER is not also running against the same
     DB at the same time — running SHADOW and PAPER concurrently against
     one `paper_equity_hist` would corrupt PAPER's real peak with
     hypothetical SHADOW equity. **Simplest safe rule: SHADOW must not
     write to `paper_equity_hist` at all** — it reads the current halt/
     pause state to decide whether it *would* be blocked, but computes
     its own notional "shadow equity" bookkeeping separately if it wants
     to track hypothetical P&L, never mixing it into PAPER's real series.
2. Add a `--sombra-paper` flag to `system_runner.py`'s `main()`, mutually
   exclusive with `--auto-paper`/`--reglas-paper`/`--prueba-claude` (same
   pattern as the existing mutual-exclusion checks), that runs
   `ejecutar_continuo(...)` with a new `sombra=True` path through
   `escanear()`/`procesar_candidatos()` calling `ejecutar_reglas_shadow`
   instead of `ejecutar_reglas`.
3. `runner_status.json`'s `modo`/`autorizacion` fields should say
   `SHADOW_PAPER` plainly — Agent City 3D and any other consumer of that
   file must never be able to confuse a SHADOW run for a real PAPER run.
4. Tests (mirroring `test_paper_halt.py`'s style, no network): SHADOW
   respects an active hard halt (logs rejection, never opens); SHADOW
   respects the 8% pause tier; SHADOW's decisions never appear in
   `paper_trades`; running SHADOW alongside a live PAPER halt/pause state
   produces identical accept/reject verdicts to what PAPER would have
   produced, given the same inputs (the whole point of SHADOW is that its
   risk verdict is trustworthy evidence toward LIVE readiness later).

## Why this is a handoff, not a direct push

Same reasoning as the `DRAWDOWN_HALT_PCT` application and the Finding 3
design note earlier this session: this touches `paper_store.py` and
`system_runner.py`, both real risk/execution files this cloud session
does not own, and it cannot be tested here (no network to Binance, and
no real `trading.db` with live-shaped data to validate the scanner/risk
pipeline against). Claude Code local has both. This document is the
grounded spec; the implementation and its tests are not written here.
