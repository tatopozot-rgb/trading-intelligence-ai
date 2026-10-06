"""
Quant/Validation: synthetic-data validation of the 4h trend-following
candidate (trading_intelligence.strategy.router.candidate_router_trend_4h),
proposed to remediate the real NO-GO recorded in docs/CHECKPOINT.md section
12 -- DualMACrossover(1D, fast=20/slow=50), the ONLY strategy wired into
this project's live router, produced just 11 completed trades on real
BTCUSDT 2019-2026 data (below the 30-trade minimum) and 0 walk-forward
folds cleared IS Sharpe >= 0.5.

STAGE 0 -- ECONOMIC RATIONALE (written and committed before any of this
file's backtest numbers were looked at; see candidate_router_trend_4h()'s
own docstring for the full statement, restated briefly here):

  The crossover strategy's rationale -- ride an established trend until
  the fast/slow MA relationship reverses -- does not depend on calendar
  bar size. Sampling it once a day gives only ~365 independent crossover
  opportunities per year on a multi-year span; sampling it every 4 hours
  gives ~6x that. This is a change in SAMPLING FREQUENCY, not a retuning
  of the strategy: fast_period=20, slow_period=50 and their 20:50 ratio
  are exactly what default_router() already runs, unchanged. The project's
  own data layer (HistoricalDataDownloader / BinanceSpotAdapter) already
  treats "4h" as an ordinary Binance kline interval -- no new
  architecture is needed to run this candidate for real.

THIS CLOUD SESSION HAS NO REAL BINANCE NETWORK ACCESS (confirmed:
api.binance.com returns 403 via the egress proxy policy). Everything
below is validated on SYNTHETIC data only -- a controlled stand-in built
to carry two real-BTC characteristics (volatility clustering via a
GARCH(1,1) process, and regime-switching drift), not real market data.
No synthetic result here is a real-data GO/NO-GO claim. See
docs/STRATEGY_CANDIDATE_TREND_4H_VALIDATION.md for the full write-up and
docs/CHECKPOINT.md's Quant/Validation section for the honest final verdict.
"""
from __future__ import annotations

from decimal import Decimal

from tests.synthetic_market import make_btc_like_ohlcv_4h, resample_to_1d
from trading_intelligence.backtesting.backtest_engine import BacktestEngine
from trading_intelligence.backtesting.walk_forward import run_anchored_walk_forward
from trading_intelligence.strategy.router import candidate_router_trend_4h, default_router
from trading_intelligence.strategy.strategies.ma_crossover import DualMACrossover

# Fixed, predetermined battery of seeds -- chosen once, before looking at
# any result from this battery, and never changed after seeing outcomes.
# Running many seeds (not one hand-picked seed) is the Monte-Carlo-style
# robustness check STRATEGY_VALIDATION_FRAMEWORK.md's Stage 5 asks for;
# reporting the aggregate across all of them (not the best one) is what
# keeps this from being exactly the seed-level cherry-picking the
# framework's anti-curve-fitting rule exists to prevent.
SEED_BATTERY = list(range(1, 16))
YEARS = 7
N_BARS_4H = int(YEARS * 365 * 6)


def _candidate_strategy(timeframe: str) -> DualMACrossover:
    """The exact params default_router() already runs for TREND_UP /
    BREAKOUT_UP -- fast=20, slow=50, trend filter disabled. Only the
    timeframe argument differs between the real (1D) and candidate (4h)
    configurations; nothing else is retuned."""
    return DualMACrossover(
        "BTCUSDT", timeframe,
        params={"fast_period": 20, "slow_period": 50, "trend_filter_period": 0},
    )


class TestStage1DataQuality:
    """STRATEGY_VALIDATION_FRAMEWORK.md Stage 1's mandatory OHLCV
    consistency checks, against the synthetic fixture itself -- structural
    checks, not statistical ones."""

    def test_multi_year_span_and_no_gaps(self):
        data = make_btc_like_ohlcv_4h(N_BARS_4H, seed=SEED_BATTERY[0])
        assert len(data) == N_BARS_4H
        span_years = (data.index[-1] - data.index[0]).days / 365.25
        assert span_years >= 4.0, "Stage 1 requires >= 4 years preferred for crypto"
        deltas = data.index.to_series().diff().dropna()
        assert (deltas == deltas.iloc[0]).all(), "4h bars must be evenly spaced, no gaps"

    def test_ohlc_internal_consistency_every_bar(self):
        """H >= O, H >= C, L <= O, L <= C, H >= L -- for every single bar,
        across several seeds, not just the first."""
        for seed in SEED_BATTERY[:3]:
            data = make_btc_like_ohlcv_4h(N_BARS_4H, seed=seed)
            assert (data["high"] >= data["open"]).all()
            assert (data["high"] >= data["close"]).all()
            assert (data["low"] <= data["open"]).all()
            assert (data["low"] <= data["close"]).all()
            assert (data["high"] >= data["low"]).all()
            assert (data["close"] > 0).all(), "no runaway negative/zero prices"

    def test_resample_to_1d_preserves_ohlc_consistency(self):
        """The 1D control series (same price path, aggregated) must remain
        internally consistent after resampling -- proves the comparison
        below isolates sampling frequency, not a data-construction bug."""
        data_4h = make_btc_like_ohlcv_4h(N_BARS_4H, seed=SEED_BATTERY[0])
        data_1d = resample_to_1d(data_4h)
        assert (data_1d["high"] >= data_1d[["open", "close"]].max(axis=1)).all()
        assert (data_1d["low"] <= data_1d[["open", "close"]].min(axis=1)).all()
        # Same underlying path -> same start/end close, just fewer, wider bars.
        assert data_1d["close"].iloc[-1] == data_4h["close"].iloc[-1]


class TestFrequencyFixConfirmed:
    """The actual hypothesis under test: does sampling the IDENTICAL price
    path at 4h instead of 1D produce enough completed trades to clear
    Stage 1's 30-trade minimum, with nothing else about the strategy
    changed? Checked across the full predetermined battery, not one seed."""

    def test_4h_clears_30_trade_minimum_in_most_seeds_1d_does_not(self):
        below_min_1d = 0
        below_min_4h = 0
        for seed in SEED_BATTERY:
            data_4h = make_btc_like_ohlcv_4h(N_BARS_4H, seed=seed)
            data_1d = resample_to_1d(data_4h)

            result_4h = BacktestEngine(
                _candidate_strategy("4h"), initial_equity=Decimal("10000")
            ).run(data_4h)
            result_4h.compute_metrics()

            result_1d = BacktestEngine(
                _candidate_strategy("1d"), initial_equity=Decimal("10000")
            ).run(data_1d)
            result_1d.compute_metrics()

            if result_4h.total_trades < 30:
                below_min_4h += 1
            if result_1d.total_trades < 30:
                below_min_1d += 1

        # The real finding this candidate responds to: 1D produced too few
        # trades (11, real data) for the SAME strategy logic. The identical
        # price path, sampled at 4h, must clear the 30-trade minimum in a
        # clear majority of seeds; 1D, sampled on the exact same path,
        # should struggle the same way the real 1D run did.
        assert below_min_4h <= 2, (
            f"4h fell below the 30-trade minimum in {below_min_4h}/{len(SEED_BATTERY)} "
            "seeds -- the frequency fix should clear this bar in nearly all of them"
        )
        assert below_min_1d >= len(SEED_BATTERY) - 3, (
            f"1D fell below the 30-trade minimum in only {below_min_1d}/{len(SEED_BATTERY)} "
            "seeds -- expected most, matching the real 11-trade finding"
        )


class TestWalkForwardHarnessRunsForCandidateConfiguration:
    """Proves the full Stage 2-3 pipeline (BacktestEngine fees/slippage ->
    anchored walk-forward -> go/no-go) runs end to end for the 4h
    candidate, through the real StrategyRouter via router_factory= (the
    actual way this would be wired if promoted) -- same discipline as
    test_walk_forward.py's own existing end-to-end tests. Does NOT assert
    GO: a synthetic Monte-Carlo-style battery result (mixed outcomes
    across seeds) is reported honestly in
    docs/STRATEGY_CANDIDATE_TREND_4H_VALIDATION.md, not hardcoded here as
    a pass/fail on one seed, which would itself be seed-level
    cherry-picking."""

    def test_candidate_router_runs_through_walk_forward_without_error(self):
        data = make_btc_like_ohlcv_4h(N_BARS_4H, seed=SEED_BATTERY[0])
        report = run_anchored_walk_forward(
            router_factory=lambda params: candidate_router_trend_4h(),
            params={"strategy_id": "candidate_trend_4h"},
            data=data, is_pct=0.5, oos_pct=0.15, step_pct=0.1, max_folds=5,
        )
        go, reason = report.go_no_go()
        assert isinstance(go, bool)
        assert isinstance(reason, str) and reason
        for fold in report.folds:
            assert fold.oos_start > fold.is_end
            assert fold.is_start == data.index[0], "anchored: IS always starts at bar 0"

    def test_candidate_router_registers_only_trend_up_and_breakout_up(self):
        """Confirms the candidate router makes the same honest coverage
        claim as default_router() -- TREND_UP/BREAKOUT_UP only, nothing
        invented for RANGE/TREND_DOWN/NO_EDGE."""
        from trading_intelligence.regime.detector import Regime

        router = candidate_router_trend_4h()
        assert router.registered_regimes() == {Regime.TREND_UP, Regime.BREAKOUT_UP}

    def test_candidate_is_not_wired_into_the_live_default_router(self):
        """The candidate must stay opt-in until a real-data walk-forward
        run confirms it -- promoting it into default_router() on synthetic
        evidence alone would be exactly the premature claim this project's
        validation gate exists to prevent."""
        live_router = default_router()
        # default_router()'s own registered strategy must still be the 1D
        # configuration, not silently swapped for the 4h candidate.
        from trading_intelligence.regime.detector import Regime

        live_strategy, _ = live_router._registry[Regime.TREND_UP]
        assert live_strategy.timeframe == "1d"
