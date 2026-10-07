"""
Survival invariants under correlated shocks, using the bench in
tests/survival_stress.py (full pipeline, real RiskEngine and PaperAdapter,
driven by a deliberately reckless always-long strategy so there is real
exposure when each shock hits).

Small scenarios only, so the suite stays fast; the full sweep is
`python -m tests.survival_stress`. Synthetic data: this verifies the risk
machinery holds on every bar, not that any strategy has edge. It asserts
invariants, not performance: the sweep shows drawdowns well past the 15% halt
(see docs/CHECKPOINT.md section 30), so no drawdown bound is claimed here.
"""
from tests.survival_stress import Scenario, run_scenario

SMALL_SYMBOLS = ["AAAUSDT", "BBBUSDT", "CCCUSDT"]


def _run(scenario: Scenario, seed: int = 1, **overrides):
    return run_scenario(scenario, seed, symbols=SMALL_SYMBOLS, risk_overrides=overrides or None)


def _assert_not_vacuous(r) -> None:
    """A survival test that never held a position proves nothing."""
    assert r.max_exposure_pct > 5.0, f"scenario never held meaningful exposure: {r}"


class TestSurvivalInvariants:
    def test_calm_market_holds_every_invariant(self):
        r = _run(Scenario("calm", n_days=420))
        _assert_not_vacuous(r)
        assert r.violations == []

    def test_correlated_crash_holds_every_invariant_and_the_account_survives(self):
        r = _run(Scenario("crash", n_days=420, shocks={300: -0.35}))
        _assert_not_vacuous(r)
        assert r.violations == []
        assert r.final_equity_ratio > 0.5, "a -35% market crash must not take half the account"

    def test_one_position_at_a_time_is_respected_through_a_crash(self):
        r = _run(Scenario("crash", n_days=420, shocks={300: -0.35}), max_open_positions=1)
        _assert_not_vacuous(r)
        assert r.violations == []
        assert r.max_concurrent_positions <= 1

    def test_a_tighter_exposure_cap_holds_less_and_loses_less_in_a_bar(self):
        loose = _run(Scenario("crash", n_days=420, shocks={300: -0.40}), max_total_exposure_pct=40.0)
        tight = _run(Scenario("crash", n_days=420, shocks={300: -0.40}), max_total_exposure_pct=10.0)
        _assert_not_vacuous(tight)
        assert loose.violations == [] and tight.violations == []
        assert tight.max_exposure_pct <= loose.max_exposure_pct
        assert tight.worst_bar_loss_pct <= tight.max_exposure_pct + 0.5

    def test_grinding_bear_holds_every_invariant(self):
        r = _run(Scenario("bear", n_days=500, drift_window=(250, 480, -0.006)))
        _assert_not_vacuous(r)
        assert r.violations == []
