# Finding 3 — persistent automatic halt: grounded design note

> Status: design reference for Claude Code local, not an implementation and
> not a financial-policy decision. Written by Trading Codex (cloud) by
> reading the real code on `codex/import-paper-baseline` (commit `933642a`)
> read-only, via a git worktree — no file on that branch was edited.
> Supersedes nothing; the actual implementation, its tests, and the real
> threshold values remain Claude Code local's / Trading Claude-Work's call.
> Context: PR #3 comment 6007551700 (GPT Work's independent review) and
> PR #3 comment 6007584364 (this project's decision on Finding 2/3).

## What actually exists today (verified by reading the files, not assumed)

- `risk_engine.py` is **only** a position-sizing calculator
  (`calcular_riesgo_base`, `calcular_tamano_posicion`). It has no kill
  switch, no drawdown concept, and no order-validation gate at all — that
  surprised me; I had assumed parity with `trading_intelligence/risk/engine.py`
  and it is not there.
- The actual order-validation gate is `paper_store._abrir_validado`
  (`paper_store.py:252-306`), reached from both `ejecutar_respuesta`
  (Claude-reviewed path) and `ejecutar_reglas` (`REGLAS_PAPER_V1` automatic
  path) — **both** call it, so a halt added only to one path would leave the
  other unprotected.
- Inside `_abrir_validado`, the only halt-like check is the manual file flag
  (`paper_store.py:261-262`: `(config.DIRECTORIO / 'PAUSA_ENTRADAS').exists()`),
  set/cleared only by `ControlPaper.pausar()` / `.reanudar_entradas()`
  (`paper_control.py:117-127`) — a human action, never automatic.
- The daily-loss check (`paper_store.py:266-280`) uses `asegurar_dia`
  (`paper_store.py:101-106`, UTC‑5 day boundary — this is Finding 2, out of
  scope here) and compares `perdidas + estado['riesgo'] + riesgo` against
  `base * RIESGO_MAXIMO_DIARIO_PCT / 100`. This is a **daily** budget check,
  reset every day — not a drawdown-from-peak check, and not persistent
  across days.
- `obtener_capital_operativo()` (`risk_engine.py:13-19`) returns
  `cuenta()['saldo_actual']` (`paper_account.py:11-12` →
  `paper_store.cuenta()`), which is the **realized cash balance column**,
  read straight from `paper_account.saldo_actual` in SQLite. It does **not**
  include unrealized P&L on open positions. GPT Work's point stands exactly:
  `saldo_actual` is not `equityMTM`.
- A current-price fetch already exists for computing unrealized P&L:
  `market_http.precio_actual(simbolo)` (`market_http.py:176`), already used
  elsewhere in the real system. Open positions are listed via
  `paper_trades WHERE estado='ABIERTA'` (already queried in `resumen()`,
  `paper_store.py:82-92`, which has `tamano_posicion` per row).
- `paper_fills.validar_snapshot`/`MAX_EDAD_MS` (`paper_fills.py:11,44-54`)
  and `market_http`'s client only check **order-book snapshot freshness**
  (≤5000ms) — a data-quality gate for fills, not an equity/connectivity
  watchdog. GPT Work's point stands here too: these are real controls, but
  they don't substitute for the missing halt.

## What's missing (the actual gap)

No code path anywhere computes equity-from-peak drawdown, and no code path
tracks "have we lost connectivity/fresh data for too long" as a standing,
persistent state that blocks new entries until a human clears it. The only
standing, persistent block is the manual `PAUSA_ENTRADAS` file.

## Design shape (reference only — names are suggestions, not requirements)

1. **Define `equity_mtm(con)` first, as its own small function**, separate
   from `cuenta()`'s `saldo_actual`:
   ```python
   def equity_mtm(con, precio_fn):
       saldo = con.execute('SELECT saldo_actual FROM paper_account WHERE id=1').fetchone()[0]
       abiertas = con.execute(
           "SELECT simbolo, entrada, tamano_posicion FROM paper_trades WHERE estado='ABIERTA'"
       ).fetchall()
       no_realizado = math.fsum(
           (precio_fn(f['simbolo']) - f['entrada']) / f['entrada'] * f['tamano_posicion']
           for f in abiertas
       )
       return saldo + no_realizado
   ```
   `precio_fn` defaults to `market_http.precio_actual`; tests inject a
   fixture instead of hitting the network. If any `precio_fn` call fails or
   returns stale/invalid data, **fail closed** (treat as "cannot evaluate
   drawdown right now" — see point 4), never silently fall back to
   `saldo_actual`.

2. **A new persistent state file/table, separate from `PAUSA_ENTRADAS`.**
   `PAUSA_ENTRADAS` is a human on/off switch with no reason attached; this
   needs its own record so the two never get confused or accidentally
   cleared together. A new SQLite table (`paper_halt`, alongside the
   existing `paper_days`/`paper_flows` pattern in `paper_store.inicializar`)
   is more consistent with this codebase's existing atomicity story than a
   second flag file:
   ```sql
   CREATE TABLE IF NOT EXISTS paper_halt (
     id INTEGER PRIMARY KEY CHECK (id = 1),
     activo INTEGER NOT NULL, razon TEXT NOT NULL,
     pico_equity REAL, fecha_activacion TEXT, fecha_actualizacion TEXT NOT NULL
   );
   ```
   Written inside the same `BEGIN IMMEDIATE` transaction as the check that
   triggers it — this codebase already has that pattern throughout
   `paper_store.py`, so a new halt table gets the same crash-safety for free
   without inventing a second persistence mechanism (no new atomic-tmp-file
   needed, unlike `trading_intelligence/risk/models.py`'s `RiskState`, which
   solved the same problem with JSON because it has no SQLite database to
   piggyback on — that pattern is a reference for *why* persistence must be
   transactional, not a reason to copy JSON files into a codebase that
   already has transactional SQLite).

3. **Check it inside `_abrir_validado`, right next to the `PAUSA_ENTRADAS`
   check (`paper_store.py:261-262`)**, so both automatic (`ejecutar_reglas`)
   and reviewed (`ejecutar_respuesta`) paths are covered by construction —
   there is exactly one opening path to patch, not two:
   ```python
   halt = con.execute('SELECT activo, razon FROM paper_halt WHERE id=1').fetchone()
   if halt and halt['activo']:
       raise ValueError(f'Halt de riesgo activo: {halt["razon"]}')
   ```
   This must **never** gate closing an existing position — only new entries,
   same as `PAUSA_ENTRADAS` today. Closing logic lives elsewhere (not in
   `_abrir_validado`) and this review did not find it in scope here; confirm
   it before wiring anything, rather than assuming symmetry with opening.

4. **Fail-closed on incomplete data, not fail-open.** If `equity_mtm` can't
   be computed (price fetch fails, stale snapshot, DB read error), the
   correct behavior per the decision on PR #3 is to **block new entries**,
   the same as an active halt — not to silently proceed as if drawdown were
   fine. This is the opposite of `paper_fills.validar_snapshot`'s role
   (which *rejects a fill* on stale data); here the absence of fresh data
   must reject a *new entry*, for the same underlying reason GPT Work gave:
   unknown is never "healthy."

5. **Never auto-clear.** Nothing in `system_runner.py`/`ControlPaper` should
   ever clear `paper_halt.activo` on restart or on connectivity recovery —
   only an explicit human action (a new `ControlPaper`-style method
   requiring `confirmado=True`, mirroring `reanudar_entradas`'s existing
   pattern at `paper_control.py:122-127`) may clear it. This is the same
   guarantee `trading_intelligence/risk/engine.py`'s
   `clear_kill_switch(operator_confirmation=True)` gives, for the same
   reason: a kill switch that clears itself isn't one.

6. **Thresholds are explicitly not part of this note.** Whatever triggers
   `paper_halt.activo = 1` (an 8%/15%-style drawdown-from-peak number, a
   connectivity-loss duration, or both) is a financial-policy decision for
   Trading Claude-Work, not an engineering default — GPT Work's review
   already said not to copy `trading_intelligence/risk/engine.py`'s
   `drawdown_pause_pct`/`drawdown_halt_pct`/`max_connectivity_gap_seconds`
   defaults in as approved policy for the real system. Tests can and should
   use explicit fixture values and must reject operation when the real
   configuration is absent, per GPT Work's PR #6 comment.

## Tests this needs (restating GPT Work's list against the real file layout)

- `paper_halt` activation at the exact configured threshold (fixture value,
  not 8%/15%), using `equity_mtm` computed from fixture prices, not real
  network calls.
- Corrupted/missing `paper_halt` row (simulate with a fresh/corrupted DB,
  the same way `tests/test_crash_recovery.py` in this cloud session's
  `trading_intelligence/` simulates a corrupt `.tmp` file — same principle,
  different storage) → fails closed, blocks entries.
- Restart (fresh process, same `config.BASE_DATOS`) preserves an active halt.
- Stale/incomplete price data when computing `equity_mtm` → blocks entries,
  does not fall back to `saldo_actual`.
- Both `ejecutar_respuesta` and `ejecutar_reglas` are blocked identically by
  an active halt — no bypass through either path.
- Closing an existing position is still possible while halted (once the
  real close path is identified — not confirmed in this note).
- Clearing the halt requires the explicit `confirmado=True` call; a bare
  restart or reconnect never clears it.

## What I did not do

I did not write any code against `paper_store.py`/`risk_engine.py` — those
are Claude Code local's files per `docs/AGENT_COORDINATION.md`'s file
ownership table, and this cloud container has no way to run or validate
against the real system's actual runtime/DB anyway. This note exists so
Claude Code local can implement directly instead of re-deriving the same
line-by-line reading I just did.
