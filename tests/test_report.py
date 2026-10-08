"""Tests for backtest report generation (CSV + HTML)."""
from decimal import Decimal

import numpy as np
import pandas as pd

from trading_intelligence.backtesting.backtest_engine import BacktestEngine
from trading_intelligence.backtesting.report import (
    generate_html_report,
    write_csv_report,
    write_html_report,
)
from trading_intelligence.strategy.strategies.ma_crossover import DualMACrossover


def _trending_ohlcv(n: int = 300, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.001, 0.015, n)
    close = 100.0 * np.cumprod(1 + returns)
    idx = pd.date_range("2020-01-01", periods=n, freq="1D")
    return pd.DataFrame(
        {
            "open": close * (1 + rng.uniform(-0.003, 0.003, n)),
            "high": close * (1 + rng.uniform(0.001, 0.008, n)),
            "low": close * (1 - rng.uniform(0.001, 0.008, n)),
            "close": close,
            "volume": rng.uniform(1000, 5000, n),
        },
        index=idx,
    )


def _result():
    data = _trending_ohlcv()
    strategy = DualMACrossover("BTCUSDT", "1d", params={"fast_period": 10, "slow_period": 30,
                                                          "trend_filter_period": 0})
    engine = BacktestEngine(strategy, initial_equity=Decimal("10000"))
    result = engine.run(data)
    result.compute_metrics()
    return result


class TestCsvReport:
    def test_writes_both_files(self, tmp_path):
        result = _result()
        paths = write_csv_report(result, tmp_path)
        assert paths["trades"].exists()
        assert paths["equity_curve"].exists()

    def test_trades_csv_has_expected_columns(self, tmp_path):
        result = _result()
        paths = write_csv_report(result, tmp_path)
        df = pd.read_csv(paths["trades"])
        assert "pnl" in df.columns
        assert "entry_price" in df.columns
        assert "exit_reason" in df.columns

    def test_trades_csv_row_count_matches_trades(self, tmp_path):
        result = _result()
        paths = write_csv_report(result, tmp_path)
        df = pd.read_csv(paths["trades"])
        assert len(df) == len(result.trades)

    def test_equity_curve_csv_matches_length(self, tmp_path):
        result = _result()
        paths = write_csv_report(result, tmp_path)
        df = pd.read_csv(paths["equity_curve"])
        assert len(df) == len(result.equity_curve)

    def test_empty_trades_does_not_crash(self, tmp_path):
        """A strategy that never trades should still produce a valid (empty) report."""
        from trading_intelligence.backtesting.backtest_engine import BacktestResult
        empty_result = BacktestResult(
            trades=[], equity_curve=pd.Series([10000.0, 10000.0], name="equity"),
            initial_equity=Decimal("10000"), final_equity=Decimal("10000"),
        )
        paths = write_csv_report(empty_result, tmp_path)
        df = pd.read_csv(paths["trades"])
        assert len(df) == 0


class TestHtmlReport:
    def test_generates_valid_html_string(self):
        result = _result()
        html_str = generate_html_report(result, title="Test Report")
        assert "<html>" in html_str
        assert "Test Report" in html_str
        assert "<svg" in html_str

    def test_includes_disclaimer(self):
        """Must never read as a profitability claim — see STRATEGY_VALIDATION_FRAMEWORK.md."""
        result = _result()
        html_str = generate_html_report(result)
        normalized = " ".join(html_str.split())  # collapse newlines/indentation from the template
        assert "not a profitability claim" in normalized
        assert "STRATEGY_VALIDATION_FRAMEWORK.md" in normalized

    def test_escapes_html_in_title(self):
        result = _result()
        html_str = generate_html_report(result, title="<script>alert(1)</script>")
        assert "<script>alert(1)</script>" not in html_str
        assert "&lt;script&gt;" in html_str

    def test_write_html_report_creates_file(self, tmp_path):
        result = _result()
        path = write_html_report(result, tmp_path / "report.html")
        assert path.exists()
        assert "<html>" in path.read_text()

    def test_handles_empty_equity_curve_gracefully(self):
        from trading_intelligence.backtesting.backtest_engine import BacktestResult
        empty_result = BacktestResult(
            trades=[], equity_curve=pd.Series([10000.0], name="equity"),
            initial_equity=Decimal("10000"), final_equity=Decimal("10000"),
        )
        html_str = generate_html_report(empty_result)  # should not raise
        assert "<svg" in html_str

    def test_trade_table_row_count(self):
        result = _result()
        html_str = generate_html_report(result)
        assert f"Trades ({len(result.trades)})" in html_str
