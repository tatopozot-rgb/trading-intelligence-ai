"""
Runs a few seeds of tests/runner_fuzz.py (the stateful lifecycle fuzzer) and
checks that the fuzzer itself is not vacuous and can detect a regression.
`python -m tests.runner_fuzz 120` runs the deep sweep.
"""
import pytest

from tests import runner_fuzz
from trading_intelligence.execution import paper_runner

SEEDS = list(range(1, 9))


@pytest.fixture(scope="module")
def results():
    import logging

    logging.disable(logging.CRITICAL)
    try:
        return {seed: runner_fuzz.run_fuzz(seed) for seed in SEEDS}
    finally:
        logging.disable(logging.NOTSET)


@pytest.mark.parametrize("seed", SEEDS)
def test_no_invariant_is_violated(results, seed):
    assert results[seed].violations == []


def test_the_fuzzer_actually_exercises_every_event(results):
    totals: dict[str, int] = {}
    for r in results.values():
        for name, count in r.events.items():
            totals[name] = totals.get(name, 0) + count
    missing = [name for name in runner_fuzz.EVENTS if totals.get(name, 0) == 0]
    assert missing == [], f"events that never fired (vacuous fuzzer): {missing}"
    assert sum(r.entries for r in results.values()) > 0, "no entry was ever submitted"
    assert sum(r.trades for r in results.values()) > 0, "no trade ever closed"
    assert sum(r.vetoed_entries for r in results.values()) > 0, "no fill-time veto ever happened"


def test_the_fuzzer_detects_a_runner_that_fills_entries_through_a_halt(monkeypatch):
    """Switch off the pre-fill veto: the fuzzer must notice. Without this, a
    green fuzzer could just mean it checks nothing."""
    import logging

    monkeypatch.setattr(paper_runner.PaperTradingRunner, "_veto_pending_entry", lambda self, *args, **kwargs: [])
    logging.disable(logging.CRITICAL)
    try:
        found = [v for seed in range(1, 4) for v in runner_fuzz.run_fuzz(seed).violations]
    finally:
        logging.disable(logging.NOTSET)
    assert any("kill switch was active" in v or "above cap" in v or "loss-at-stop" in v for v in found), found[:3]


def test_the_fuzzer_detects_a_runner_that_executes_replayed_bars(monkeypatch):
    import logging

    class _Forgetful(dict):
        def __setitem__(self, key, value):  # never remembers the last bar
            pass

    original = paper_runner.PaperTradingRunner.__init__

    def init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self._last_bar_time = _Forgetful()

    monkeypatch.setattr(paper_runner.PaperTradingRunner, "__init__", init)
    logging.disable(logging.CRITICAL)
    try:
        found = [v for seed in range(1, 4) for v in runner_fuzz.run_fuzz(seed).violations]
    finally:
        logging.disable(logging.NOTSET)
    assert any("old bar" in v for v in found), found[:3]
