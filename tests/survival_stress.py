"""
Survival stress bench: runs the FULL pipeline (PaperTradingRunner with the
real RiskEngine and PaperAdapter) over a universe of correlated synthetic
assets under shocks, and reports whether capital survived and whether every
safety invariant held on every single bar.

Not a pytest module (name doesn't start with test_); tests/test_survival_stress.py
runs small scenarios from it, and `python -m tests.survival_stress` runs the
full sweep. Synthetic data only: this measures whether the risk machinery
holds, NOT whether any strategy has edge.

The default router almost never trades (its one strategy has a recorded
NO-GO), so running it through a crash proves nothing: no exposure, no test.
The bench therefore defaults to `reckless_router`, a deliberately terrible
strategy that buys every symbol whenever it is flat, with a fixed 10% stop,
and re-enters right after every stop-out. That is the worst case for
survival -- maximum exposure, revenge-style re-entry -- so what keeps
capital alive is the RiskEngine's limits, not the strategy's good behaviour.

Invariants checked on every timestamp:
  * cash >= 0 and equity > 0
  * the RiskEngine's and PaperAdapter's books reconcile (empty problem list)
  * open positions never exceed the configured max_open_positions
  * after the kill switch trips, no new entry is ever submitted
  * single-bar equity loss <= the previous bar's market exposure plus the
    notional of any entry that filled during the bar (+ fee tolerance):
    long-only spot can lose at most the value of what it holds.
    Note the configured exposure cap is NOT this bound: RiskEngine measures
    exposure at ENTRY notional, so a position that appreciates can grow far
    past the cap. `max_exposure_pct` reports how far that actually goes.
"""
from __future__ import annotations

import logging
import sys
import tempfile
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from tests.synthetic_market import make_correlated_universe
from trading_intelligence.execution.base import AbstractExchangeAdapter
from trading_intelligence.execution.paper import PaperAdapter
from trading_intelligence.execution.paper_runner import PaperTradingRunner
from trading_intelligence.persistence.audit_log import AuditLog
from trading_intelligence.regime.detector import Regime
from trading_intelligence.risk.engine import RiskEngine
from trading_intelligence.risk.models import RiskConfig
from trading_intelligence.strategy.base import AbstractStrategy
from trading_intelligence.strategy.models import TradeProposal
from trading_intelligence.strategy.router import StrategyRouter

INITIAL_EQUITY = Decimal("10000")
SYMBOLS = ["AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT"]
FEE_TOLERANCE_PCT = 0.5
# Every limit is RiskConfig's own default except the per-position cap. With the
# defaults (1% risk per trade, 5% position cap), fixed-fractional sizing exceeds
# the cap for any stop tighter than ~20% and the engine REJECTS, so nothing would
# ever trade. A 10% stop sizes to ~9.8% of equity; a 10% cap lets it through.
BENCH_RISK_DEFAULTS = {"max_position_size_pct": 10.0}


class _DataOnly(AbstractExchangeAdapter):
    def submit_order(self, order):
        raise AssertionError("paper must never forward orders")

    def cancel_order(self, client_order_id):
        raise AssertionError("not used")

    def get_position(self, symbol):
        return None

    def get_account_info(self):
        raise AssertionError("not used")

    def get_current_price(self, symbol):
        return Decimal("1")

    def get_ohlcv(self, symbol, timeframe, limit=500):
        return pd.DataFrame()

    def is_connected(self):
        return True

    def get_exchange_name(self):
        return "data_only"


class RecklessLong(AbstractStrategy):
    """Always proposes a long with a fixed-percentage stop; never exits on its
    own. Adversarial by design -- see the module docstring."""

    def __init__(self, symbol: str, stop_pct: float = 0.10):
        super().__init__("reckless", symbol, "1d", {})
        self.stop_pct = Decimal(str(stop_pct))

    def on_bar(self, data):
        close = Decimal(str(float(data["close"].iloc[-1])))
        return TradeProposal(
            strategy_id="reckless", symbol=self.symbol, side="BUY", entry_type="MARKET",
            stop_price=close * (1 - self.stop_pct), timeframe="1d", rationale="adversarial stress",
            signal_strength=1.0, timestamp=str(data.index[-1]),
        )

    def on_exit_signal(self, data, entry_price):
        return False


def reckless_router(symbol: str) -> StrategyRouter:
    router = StrategyRouter()
    strategy = RecklessLong(symbol)
    for regime in Regime:
        router.register(regime, strategy)
    return router


@dataclass
class Scenario:
    name: str
    n_days: int = 900
    shocks: dict[int, float] = field(default_factory=dict)
    drift_window: Optional[tuple[int, int, float]] = None


SCENARIOS = [
    Scenario("calm"),
    Scenario("single_crash_-30%", shocks={600: -0.30}),
    Scenario("double_crash_-25%x2", shocks={450: -0.25, 470: -0.25}),
    Scenario("bear_grind", drift_window=(300, 750, -0.004)),
    Scenario("crash_then_grind", shocks={400: -0.35}, drift_window=(400, 800, -0.003)),
]


@dataclass
class RunResult:
    scenario: str
    seed: int
    final_equity_ratio: float
    max_drawdown_pct: float
    worst_bar_loss_pct: float
    max_exposure_pct: float
    trades: int
    max_concurrent_positions: int
    halted: bool
    halt_bar: Optional[int]
    violations: list[str]


def run_scenario(
    scenario: Scenario,
    seed: int,
    *,
    symbols: list[str] = SYMBOLS,
    risk_overrides: Optional[dict] = None,
    router_factory: Callable[[str], StrategyRouter] = reckless_router,
    warmup: int = 60,
    trailing_stop_pct: Optional[float] = None,
) -> RunResult:
    frames = make_correlated_universe(
        symbols, scenario.n_days, seed=seed, shocks=scenario.shocks, drift_window=scenario.drift_window,
    )
    config = RiskConfig(**{**BENCH_RISK_DEFAULTS, **(risk_overrides or {})})
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        risk = RiskEngine(config, tmp_path / "risk.json", AuditLog(tmp_path / "audit"))
        paper = PaperAdapter(_DataOnly(), INITIAL_EQUITY, tmp_path / "paper.json")
        runner = PaperTradingRunner(router_factory, risk, paper, trailing_stop_pct=trailing_stop_pct)

        violations: list[str] = []
        exposures: list[float] = []
        bound_pct: list[float] = []
        equities: list[float] = []
        max_conc = 0
        halt_bar: Optional[int] = None
        entries_after_halt = 0
        n = scenario.n_days
        for i in range(warmup, n):
            steps = runner.process_bars({sym: f.iloc[: i + 1] for sym, f in frames.items()})
            equity = steps[0].equity
            assert equity is not None
            equities.append(float(equity))
            exposures.append(float((equity - paper.cash) / equity * 100) if equity > 0 else 0.0)
            bought = sum(
                (f.fill_price * f.filled_quantity for st in steps for f in st.fills
                 if f.side == "BUY" and f.status == "FILLED" and f.fill_price is not None),
                Decimal("0"),
            )
            prev_equity = equities[-2] if len(equities) >= 2 else float(INITIAL_EQUITY)
            prev_exposure = exposures[-2] if len(exposures) >= 2 else 0.0
            bound_pct.append(prev_exposure + float(bought) / prev_equity * 100 + FEE_TOLERANCE_PCT)
            max_conc = max(max_conc, len(paper.positions))
            if paper.cash < 0:
                violations.append(f"bar {i}: negative cash {paper.cash}")
            if equity <= 0:
                violations.append(f"bar {i}: non-positive equity {equity}")
            problems = runner.reconcile()
            if problems:
                violations.append(f"bar {i}: books disagree: {problems[0]}")
            if len(paper.positions) > config.max_open_positions:
                violations.append(f"bar {i}: {len(paper.positions)} open > max {config.max_open_positions}")
            if risk.state.kill_switch and halt_bar is None:
                halt_bar = i
            if halt_bar is not None and any(s.action == "ENTRY_SUBMITTED" for s in steps):
                entries_after_halt += 1
            if len(equities) >= 2 and equities[-2] > 0:
                loss_pct = (equities[-2] - equities[-1]) / equities[-2] * 100
                bound = bound_pct[-1]
                if loss_pct > bound:
                    violations.append(f"bar {i}: single-bar loss {loss_pct:.2f}% > held + newly bought exposure {bound:.2f}%")
        if entries_after_halt:
            violations.append(f"{entries_after_halt} entries submitted after the kill switch tripped")

        peak = equities[0]
        max_dd = 0.0
        worst = 0.0
        for k, e in enumerate(equities):
            peak = max(peak, e)
            max_dd = max(max_dd, (peak - e) / peak * 100)
            if k:
                worst = max(worst, (equities[k - 1] - e) / equities[k - 1] * 100)
        return RunResult(
            scenario=scenario.name, seed=seed,
            final_equity_ratio=equities[-1] / float(INITIAL_EQUITY),
            max_drawdown_pct=max_dd, worst_bar_loss_pct=worst, max_exposure_pct=max(exposures),
            trades=len(runner.closed_trades),
            max_concurrent_positions=max_conc, halted=risk.state.kill_switch, halt_bar=halt_bar,
            violations=violations,
        )


def main(seeds: list[int]) -> int:
    logging.disable(logging.CRITICAL)  # the alert sink logs every pause/halt; the table is the output
    print(f"{'scenario':<24}{'seed':>5}{'final':>8}{'maxDD%':>8}{'worst1bar%':>11}{'maxExp%':>9}"
          f"{'trades':>7}{'maxPos':>7}{'halted':>7}  violations", flush=True)
    bad = 0
    for scenario in SCENARIOS:
        for seed in seeds:
            r = run_scenario(scenario, seed)
            bad += len(r.violations)
            print(f"{r.scenario:<24}{r.seed:>5}{r.final_equity_ratio:>8.3f}{r.max_drawdown_pct:>8.2f}"
                  f"{r.worst_bar_loss_pct:>11.2f}{r.max_exposure_pct:>9.1f}{r.trades:>7}{r.max_concurrent_positions:>7}"
                  f"{str(r.halted):>7}  {len(r.violations)}", flush=True)
            for v in r.violations[:3]:
                print(f"    VIOLATION: {v}", flush=True)
    print(f"\ntotal violations: {bad}", flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main([int(a) for a in sys.argv[1:]] or [1, 2, 3]))
