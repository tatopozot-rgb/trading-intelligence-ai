---
type: agent
tags: [agent, trading-intelligence]
role: local execution, owns the real PAPER runtime
---

# Claude Code local

Claude Code running via PowerShell on the owner's PC
(`C:\Users\tatop\trading-ai`) — the only agent with real filesystem and
network access. Part of [[Trading Intelligence]]. **This note is being
placed by you, into this vault, as part of the task described in
`obsidian-vault-package/README.md` in the repo.**

## Responsibility

Owns the real PAPER system's root modules: `risk_engine.py`,
`paper_store.py`, `paper_fills.py`, `paper_control.py`, and the rest of
the flat-module runtime. Did the real import (PR #3) and the MARKET
lot/dust contract (PR #4).

## Assigned now (2026-10-06, by Trading Codex as coordination lead)

Two tasks, tracked on the Notion Task Board, currently the critical path
for merging PR #3 → #4 → #5:

1. **Finding 2**: add the missing daily-loss-contract tests (boundary
   cuts, first daily event, losses not offset by gains, positions
   crossing the day boundary, restart/rollback, migration without extra
   budget). Preserve the existing baseline contract — do not change the
   UTC-5 cutoff or adopt the spec's defaults without an explicit,
   separately-tracked migration.
2. **Finding 3**: build a persistent automatic halt, separate from
   `PAUSA_ENTRADAS`, checked in the common order-opening path
   (`_abrir_validado`), fail-closed on incomplete state/price data, never
   auto-clearing on restart/reconnect, never blocking closes. A grounded
   design note already exists:
   [`docs/FINDING_3_HALT_DESIGN.md`](https://github.com/tatopozot-rgb/trading-intelligence-ai/blob/main/docs/FINDING_3_HALT_DESIGN.md)
   — it's a design reference, not an implementation; the actual code,
   tests, and real risk thresholds are yours and
   [[Trading Claude-Work (GPT Work)]]'s to set.

Plus, separately: place this vault package (see the repo's
`obsidian-vault-package/README.md` for the exact steps) and report back
what vault path was used.
