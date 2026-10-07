"""
Stateful fuzzer for the PaperTradingRunner lifecycle. Not a pytest module
(name doesn't start with test_); tests/test_runner_fuzz.py runs a few seeds and
`python -m tests.runner_fuzz [N [FIRST_SEED]]` runs many.

GPT Work's PR #8 review found 12 real defects in code that had green tests:
every one was an INTERACTION (restart between approval and fill, a replayed
bar, a halt mid-lifecycle, a bookkeeping call that fails after a fill). Unit
tests written by the author test the author's mental model. This drives the
real pipeline (adversarial always-long strategy, real RiskEngine, real
PaperAdapter, correlated crash data) through a random sequence of those events
and checks, after EVERY bar, the invariants that keep capital alive:

  * cash >= 0 and equity > 0
  * every open position has a protective STOP of exactly its size
  * paper positions + pending entries never exceed max_open_positions
  * the two books reconcile -- unless a bookkeeping failure was injected, and
    while they disagree NO new entry is submitted (fail closed; they may heal later)
  * with the kill switch active at the start of a bar, no entry fills or is
    submitted during it; likewise in a bar whose risk clock could not be advanced
  * an entry that fills respects the position cap and the per-trade risk
    budget (plus the configured tolerance) at its REAL fill price
  * a restart changes no cash, position, stop or registered position, and
    leaves no pending entry or reservation behind
  * replaying an old bar changes nothing at all
  * daily counters never go negative

Synthetic data only; deterministic per seed, so any violation is reproducible.
"""
from __future__ import annotations

import logging
import random
import sys
import tempfile
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional
from unittest.mock import patch

from tests.survival_stress import INITIAL_EQUITY, SYMBOLS, _DataOnly, reckless_router
from tests.synthetic_market import make_correlated_universe
from trading_intelligence.execution.paper import PaperAdapter
from trading_intelligence.execution.paper_runner import PaperTradingRunner
from trading_intelligence.persistence.audit_log import AuditLog
from trading_intelligence.risk.engine import RiskEngine
from trading_intelligence.risk.models import RiskConfig

WARMUP = 60
EVENTS = (
    "restart", "stale_replay", "kill_on", "kill_off", "inject_confirm", "inject_close", "inject_observe", "inject_clock",
)


@dataclass
class FuzzResult:
    seed: int
    bars: int
    events: dict[str, int] = field(default_factory=dict)
    entries: int = 0
    trades: int = 0
    vetoed_entries: int = 0
    violations: list[str] = field(default_factory=list)


def _books(runner: PaperTradingRunner) -> dict[str, Any]:
    paper, risk = runner.paper, runner.risk_engine
    return {
        "cash": paper.cash,
        "positions": {s: (p.quantity, p.avg_entry_price, p.position_id) for s, p in paper.positions.items()},
        "stops": sorted(
            (o.symbol, o.stop_price, o.quantity) for o in paper.pending_orders if o.order_type == "STOP"
        ),
        "registered": sorted(
            (pid, i["symbol"], i["notional_value"]) for pid, i in risk.state.open_positions.items()
            if not i.get("reserved")
        ),
    }


def _everything(runner: PaperTradingRunner) -> dict[str, Any]:
    state = runner.risk_engine.state
    return {
        **_books(runner),
        "pending": sorted(o.client_order_id for o in runner.paper.pending_orders),
        "risk_open": dict(state.open_positions),
        "counters": (state.daily_trade_count, state.daily_turnover, state.current_day),
    }


def run_fuzz(seed: int, n_bars: int = 200, symbols: Optional[list[str]] = None) -> FuzzResult:
    symbols = symbols or SYMBOLS[:3]
    rng = random.Random(seed)
    shocks = {rng.randrange(WARMUP + 20, n_bars - 10): -rng.uniform(0.15, 0.35) for _ in range(rng.randint(0, 2))}
    frames = make_correlated_universe(symbols, n_bars, seed=seed, shocks=shocks)
    config = RiskConfig(
        max_position_size_pct=10.0,
        max_open_positions=rng.choice([1, 2, 3]),
        daily_loss_limit_pct=rng.choice([2.0, 4.0]),
        max_fill_risk_overshoot_pct=rng.choice([0.0, 25.0, 100.0]),
    )
    trailing = rng.choice([None, 0.10])
    result = FuzzResult(seed=seed, bars=n_bars, events={e: 0 for e in EVENTS})
    tag = f"seed {seed}"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        def build() -> PaperTradingRunner:
            risk = RiskEngine(config, root / "risk.json", AuditLog(root / "audit"))
            paper = PaperAdapter(_DataOnly(), INITIAL_EQUITY, root / "paper.json")
            return PaperTradingRunner(reckless_router, risk, paper, trailing_stop_pct=trailing)

        runner = build()
        tainted = False  # a bookkeeping failure fired: the books may legitimately disagree from now on

        def violation(i: int, msg: str) -> None:
            result.violations.append(f"{tag} bar {i}: {msg}")

        for i in range(WARMUP, n_bars):
            frames_now = {s: f.iloc[: i + 1] for s, f in frames.items()}
            roll = rng.random()
            injected: Optional[str] = None

            if roll < 0.04:
                result.events["restart"] += 1
                before = _books(runner)
                runner = build()
                if _books(runner) != before:
                    violation(i, f"restart changed the books: {before} -> {_books(runner)}")
                if [o for o in runner.paper.pending_orders if o.order_type != "STOP"]:
                    violation(i, "restart left a pending non-STOP order")
                if runner.risk_engine.reservation_ids():
                    violation(i, "restart left a reservation behind")
            elif roll < 0.08 and i > WARMUP + 1:
                result.events["stale_replay"] += 1
                before_all = _everything(runner)
                old = {s: f.iloc[: rng.randint(WARMUP, i)] for s, f in frames.items()}
                steps = runner.process_bars(old)
                if any(st.action != "STALE_BAR_IGNORED" for st in steps):
                    violation(i, f"an old bar was not ignored: {[st.action for st in steps]}")
                if _everything(runner) != before_all:
                    violation(i, "replaying an old bar changed state")
            elif roll < 0.11:
                if runner.risk_engine.state.kill_switch:
                    runner.risk_engine.clear_kill_switch(operator_confirmation=True)
                    result.events["kill_off"] += 1
                else:
                    runner.risk_engine.activate_kill_switch("fuzz")
                    result.events["kill_on"] += 1
            elif roll < 0.20:
                # Only inject where the call will actually happen this bar, or the event is vacuous.
                options = ["observe"]
                if runner._pending_entries:
                    # the interesting failures only exist while an entry is queued: weight them up
                    options = ["observe"] + ["confirm", "clock"] * 4
                if runner.paper.positions:
                    options += ["close"]
                injected = rng.choice(options)

            kill_at_start = runner.risk_engine.state.kill_switch
            equity_pre = runner.paper.last_known_equity()
            fired: list[str] = []

            def boom(name: str):
                def _raise(*args: Any, **kwargs: Any) -> None:
                    fired.append(name)
                    raise OSError(f"fuzz-injected {name} failure")
                return _raise

            ctx = []
            if injected == "confirm":
                ctx.append(patch.object(runner.risk_engine, "confirm_reservation", side_effect=boom("confirm")))
            elif injected == "close":
                ctx.append(patch.object(runner.risk_engine, "register_position_closed", side_effect=boom("close")))
            elif injected == "clock":
                ctx.append(patch.object(runner.risk_engine, "advance_clock", side_effect=boom("clock")))
            elif injected == "observe":
                ctx.append(patch.object(runner.risk_engine, "observe_equity", side_effect=boom("observe")))
            for c in ctx:
                c.start()
            try:
                steps = runner.process_bars(frames_now)
            except Exception as exc:  # the runner must absorb these; an escape is itself a finding
                violation(i, f"process_bars raised {type(exc).__name__}: {exc}")
                for c in ctx:
                    c.stop()
                break
            finally:
                for c in ctx:
                    try:
                        c.stop()
                    except RuntimeError:
                        pass

            for name in fired:
                result.events[f"inject_{name}"] += 1
                if name in ("confirm", "close"):
                    tainted = True

            submitted = [st for st in steps if st.action == "ENTRY_SUBMITTED"]
            result.entries += len(submitted)
            result.vetoed_entries += sum(1 for st in steps for n in st.notes if "FILL_" in n)
            paper, risk = runner.paper, runner.risk_engine
            equity = paper.get_account_info().equity

            if paper.cash < 0:
                violation(i, f"negative cash {paper.cash}")
            if equity <= 0:
                violation(i, f"non-positive equity {equity}")
            for sym, pos in paper.positions.items():
                stop = runner._stop_order_for(sym)
                if stop is None:
                    violation(i, f"{sym} is open without a protective STOP")
                elif stop.quantity != pos.quantity:
                    violation(i, f"{sym} STOP size {stop.quantity} != position {pos.quantity}")
            if len(paper.positions) + len(runner._pending_entries) > config.max_open_positions:
                violation(i, f"{len(paper.positions)} open + {len(runner._pending_entries)} pending "
                             f"> max {config.max_open_positions}")
            problems = runner.reconcile()
            if problems and not tainted:
                violation(i, f"books disagree with no failure injected: {problems[0]}")
            if submitted and problems:
                # Fail closed: an entry may only be submitted while the books agree. They may
                # legitimately disagree for a while after an injected failure, and heal later
                # (the orphan position closes, a restart releases its reservation).
                violation(i, f"an entry was submitted while the books disagree: {problems[0]}")
            if not tainted and not problems:
                orphan = set(risk.reservation_ids()) - {p.order_id for p in runner._pending_entries.values()}
                if orphan:
                    violation(i, f"reservations with no pending entry: {sorted(orphan)}")
            if "clock" in fired:
                filled_buys = [f for st in steps for f in st.fills if f.side == "BUY" and f.status == "FILLED"]
                if filled_buys:
                    violation(i, "an entry filled in a bar whose risk clock could not be advanced")
            if kill_at_start:
                bought = [f for st in steps for f in st.fills if f.side == "BUY" and f.status == "FILLED"]
                if bought or submitted:
                    violation(i, "an entry was filled or submitted while the kill switch was active")
            st0 = risk.state
            if st0.daily_trade_count < 0 or Decimal(st0.daily_turnover) < 0:
                violation(i, f"negative daily counters {st0.daily_trade_count} / {st0.daily_turnover}")

            for st in steps:
                for f in st.fills:
                    if f.side != "BUY" or f.status != "FILLED" or f.fill_price is None:
                        continue
                    stop = runner._stop_order_for(st.symbol)
                    if stop is None or stop.stop_price is None:
                        continue  # stopped out inside its own fill bar
                    fee = Decimal(str(config.taker_fee_rate))
                    loss_at_stop = f.filled_quantity * (f.fill_price - stop.stop_price) \
                        + 2 * fee * f.filled_quantity * f.fill_price
                    allowed = equity_pre * Decimal(str(config.max_risk_per_trade_pct)) / 100 \
                        * (1 + Decimal(str(config.max_fill_risk_overshoot_pct)) / 100)
                    if loss_at_stop > allowed * Decimal("1.000001"):
                        violation(i, f"{st.symbol} filled with loss-at-stop {loss_at_stop:.2f} > allowed {allowed:.2f}")
                    cap = equity_pre * Decimal(str(config.max_position_size_pct)) / 100
                    if f.filled_quantity * f.fill_price > cap * Decimal("1.000001"):
                        violation(i, f"{st.symbol} filled {f.filled_quantity * f.fill_price:.2f} above cap {cap:.2f}")
        result.trades = len(runner.closed_trades)
    return result


def main(n_seeds: int, start: int = 1) -> int:
    logging.disable(logging.CRITICAL)
    totals: dict[str, int] = {}
    bad = 0
    for seed in range(start, start + n_seeds):
        r = run_fuzz(seed)
        bad += len(r.violations)
        for k, v in r.events.items():
            totals[k] = totals.get(k, 0) + v
        print(f"seed {seed:>3}: entries {r.entries:>3} trades {r.trades:>3} vetoed {r.vetoed_entries:>3} "
              f"violations {len(r.violations)}", flush=True)
        for v in r.violations[:3]:
            print(f"    VIOLATION: {v}", flush=True)
    print(f"\nevents injected: {totals}\ntotal violations: {bad}", flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 10, int(sys.argv[2]) if len(sys.argv) > 2 else 1))
