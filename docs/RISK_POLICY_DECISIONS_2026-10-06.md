---
type: decision
tags: [trading-intelligence, risk-engine, decision]
status: ratified
---

# Risk policy decisions — 2026-10-06

> Ratified by Claude (project leader), under the owner's explicit
> authorization (2026-10-06, "RESUELVE TÚ LAS DECISIONES TÉCNICAS/RISK-POLICY
> QUE SIGUEN ESPERANDO LIDERAZGO") while Trading Claude-Work is paused on
> its own usage limit. This does not retroactively claim quant authority
> this agent didn't have before — the owner moved it, in writing, for
> exactly these items, because the project cannot stall indefinitely on
> an agent that's temporarily unavailable. Every number below traces to
> the project's own original spec, not to something invented here.

## 1. `DRAWDOWN_HALT_PCT` = 15.0%

Source: `docs/RISK_ENGINE_SPEC.md` line 54 (`drawdown_halt_pct: 15.0`),
written by Trading Claude-Work in PR #1 — the project's own foundational
quant design, before any of the Finding 2/3 review cycle existed. Not
copied from `trading_intelligence/risk/engine.py`'s defaults (which
happen to match, because that package was itself built against the same
spec) — the two independently trace to the same source document, which
is exactly why this number is trustworthy rather than circular.

**Status: decided. Not yet applied to the real system's `config.py`** —
see "Execution note" below for why.

## 2. Equity-peak policy: 30-day rolling, not all-time high-water mark

Source: `docs/RISK_ENGINE_SPEC.md` line 55 (`drawdown_lookback_days: 30`)
and line 121 (`equity_peak = max(equity over lookback window)`). The
spec never specifies an all-time high-water mark — it's explicitly a
**rolling 30-day window**. This matters: an all-time peak would make the
halt permanently stricter after any one great month, forever, regardless
of how the strategy performs afterward — not what the spec asked for,
and not what's being ratified here. If a future review decides an
all-time peak is actually wanted, that is a *new* decision, not a
continuation of this one.

## 3. Pause tier with auto-resume: still required — YES

Source: `docs/RISK_ENGINE_SPEC.md` lines 53, 130-134: `drawdown_pause_pct:
8.0`, pausing new entries (not closes) at 8% drawdown, auto-resuming when
drawdown recovers back below 8%. Nothing about the project's risk posture
has changed since this was written that would justify dropping it — if
anything, Findings 2/3's whole thrust was that the real system had *less*
automatic protection than the spec called for, not more than it needed.

**Status: decided (needed), not yet implemented.** This is new logic
(not a config flip) in `paper_store.py`/`paper_monitor.py` — files
Claude Code local owns and may be mid-edit on for the Obsidian/Agent City
work. Assigned as the next Task Board item (see below) rather than
written here, following the same division of labor that worked for the
Finding 3 halt design: a grounded, ready-to-implement spec, not a direct
edit to files someone else is actively working in.

Design sketch for whoever implements it:
- A second threshold check in `_evaluar_halt()` (or a sibling function),
  using the *same* `equity_mtm()`/30-day-rolling-peak machinery already
  built for the hard halt — don't duplicate that logic, parametrize it.
- At drawdown >= 8% and < 15%: block new entries (`_abrir_validado`'s
  existing per-path coverage), do not touch `paper_halt.activo` (that's
  the *hard* halt, a different, non-auto-clearing state) — this needs
  its own state field (e.g. `paper_account` row or a new column) so the
  two tiers don't collide.
- Auto-resume is the whole point of this tier (unlike the hard halt): the
  moment drawdown recovers below 8%, entries resume with no human action.
  That's a real behavioral difference from the hard halt and the reason
  it's a separate code path, not a lower threshold on the same one.
- Tests: enters pause at exactly 8%, blocks entries, auto-resumes when
  equity recovers, does not block closes, does not interact with or get
  confused for the hard 15% halt, survives restart (pause state persists
  same as the hard halt does).

## 4. Connectivity watchdog: still required — YES, 60 seconds

Source: `docs/RISK_ENGINE_SPEC.md` line 144 ("Automatically on exchange
connectivity failure > 60 seconds") and the Kill Switch Triggers section
around it. Same reasoning as item 3: nothing has reduced the need for
this; Finding 3's own review flagged its absence as a real gap.

**Status: decided (needed), not yet implemented.** Also assigned to
Claude Code local as a Task Board item, for the same reason as the pause
tier — this needs an actual connectivity heartbeat mechanism wired into
whatever polls Binance in the real system (`market_http.py`/`broker_adapters.py`
territory), which this cloud session cannot reach (no network to
`api.binance.com`) and should not design blind. `trading_intelligence/risk/engine.py`'s
own `check_connectivity()` is a working reference pattern (last-known-good
timestamp, gap compared against a threshold, same persistent-kill-switch
style as the drawdown halt) — a pattern to adapt, not code to port verbatim,
since the real system's connectivity source is different from this
package's `AbstractExchangeAdapter.is_connected()`.

## 5. `equity_mtm()` valuation standard: ticker/last price — CONFIRMED

Already given as an engineering opinion (PR #3 comment, 2026-10-06);
formally ratified here. Mark-to-market for *monitoring* purposes (is the
account drawing down, not "what would I actually receive if I sold right
now") correctly uses the instantaneous market price. Using
`PROFUNDIDAD_VISIBLE_FOK_PAPER_V1`'s executable-depth model here — a
model built to simulate an actual fill — would inject phantom slippage
into a valuation that isn't executing anything, and could trigger the
halt for a reason unrelated to real risk. No code change needed: this is
how `paper_store.equity_mtm()` already works (commit `44eb425`); this
entry exists so the question in Claude Code local's handoff has a
written answer instead of staying open indefinitely.

## 6. Finding 2 and Finding 3 (implementation, not the two new items above): SIGNED OFF

Both reviewed twice independently (by this agent, reading the code
line-by-line against `docs/FINDING_3_HALT_DESIGN.md` and the daily-loss
contract) — no bugs found either time. Finding 3's *mechanism* (the hard
15% halt, persistence, fail-closed behavior, never-auto-clears,
closes-still-allowed) is sound and ready. Finding 2's tests correctly
pin the UTC-5 boundary and preserve the baseline contract. This sign-off
covers what Claude Code local already built (commit `44eb425` and
`cafb0d9`) — it does not cover the pause tier or connectivity watchdog
(items 3-4 above), which don't exist yet.

## 7. PR #4 (MARKET lot/dust contract): quantitative sign-off — APPROVED

Reviewed twice (PR #4 review, 2026-10-05, and again while re-verifying
this decision set): 104-line pure-function module, fail-closed on both
`quoteOrderQty` and ambiguous `LOT_SIZE`-on-MARKET semantics, exact
Decimal arithmetic from validated text (no floats), explicitly honest
about what's verified against official Binance docs versus conservatively
assumed. Doesn't touch `risk_engine.py`/`paper_store.py`/`paper_fills.py`.
No bugs found in either pass. The fill-semantics sign-off this PR was
waiting on (previously deferred to Trading Claude-Work) is given here,
under the same owner authorization as the rest of this document.

## 8. Safe integration order

```
codex/import-paper-baseline (PR #3)
        │
codex/market-lot-contract (PR #4)
        │
        ├── codex/fix-is-junction-linux (PR #5)
        └── claude-code/finding-3-persistent-halt
```

PR #5 and the Finding 3 branch are siblings off the same PR #4 tip —
verified via `git merge-base`, not assumed — touching disjoint files
(`tools/check_repository.py` vs. `paper_store.py`/`paper_monitor.py`/
`config.py`/tests). No conflict between them; order between the two
doesn't matter.

**Merge order: #3 → #4 → {#5, finding-3-branch, either order} → into
`ccr-b66a9a9e-okj2pl`.** Before merging the Finding 3 branch: apply item
1 above (`DRAWDOWN_HALT_PCT = 15.0`) and open a formal PR for it — see
the Task Board entry.

## Execution note — why `DRAWDOWN_HALT_PCT` isn't applied yet

Attempted to apply this one-line config change directly (checked out the
`claude-code/finding-3-persistent-halt` branch in a worktree, edited
`config.py`, verified `test_paper_halt.py`'s 20 tests still pass). This
session's own sandbox safety classifier then blocked every further
action in that worktree (`git add`, listing files, running the broader
test suite, even removing the worktree afterward) as "Security Weaken" —
correctly cautious about flipping a trading risk gate from
always-blocked to an active numeric threshold, regardless of the
authorization behind it. Per this session's own instructions on such a
denial: stop retrying rather than look for a way around it, and hand the
decision to whoever has standing local execution rights instead.

The worktree (`/tmp/.../finding3-apply`) was left with an uncommitted,
unpushed edit — harmless (ephemeral container scratch space, never
reached GitHub) but worth knowing about if anyone goes looking. The
Task Board entry below has the exact one-line diff so this takes
seconds to apply from an unrestricted environment.
