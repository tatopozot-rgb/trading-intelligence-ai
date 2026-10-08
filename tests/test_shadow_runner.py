"""
Tests for ShadowRunner — proves it never constructs or sends an order, only
ever calls public read-only market data methods, and correctly wires a real
RiskEngine's decision through to the recorded ShadowDecision.
"""
from decimal import Decimal
from pathlib import Path
from typing import Optional

import pandas as pd

from trading_intelligence.execution.base import AbstractExchangeAdapter
from trading_intelligence.execution.shadow import ShadowRunner
from trading_intelligence.persistence.audit_log import AuditLog
from trading_intelligence.risk.engine import RiskEngine
from trading_intelligence.risk.models import RiskConfig
from trading_intelligence.strategy.base import AbstractStrategy
from trading_intelligence.strategy.models import TradeProposal


class _AlwaysSignalsStrategy(AbstractStrategy):
    """Fires a BUY proposal on every call — isolates ShadowRunner's wiring
    from any real indicator logic."""

    def __init__(self, stop_price: Decimal):
        super().__init__(strategy_id="shadow_test", symbol="BTCUSDT", timeframe="1h", params={})
        self.stop_price = stop_price

    def on_bar(self, data: pd.DataFrame) -> Optional[TradeProposal]:
        return TradeProposal(
            strategy_id=self.strategy_id, symbol=self.symbol, side="BUY",
            entry_type="MARKET", stop_price=self.stop_price, timeframe=self.timeframe,
            rationale="always signals", signal_strength=1.0, timestamp=str(data.index[-1]),
        )

    def on_exit_signal(self, data: pd.DataFrame, entry_price: Decimal) -> bool:
        return False


class _NeverSignalsStrategy(AbstractStrategy):
    def __init__(self):
        super().__init__(strategy_id="never", symbol="BTCUSDT", timeframe="1h", params={})

    def on_bar(self, data: pd.DataFrame) -> Optional[TradeProposal]:
        return None

    def on_exit_signal(self, data: pd.DataFrame, entry_price: Decimal) -> bool:
        return False


class FakeMarketDataAdapter(AbstractExchangeAdapter):
    """Records every call made to it — proves ShadowRunner only ever
    touches public, read-only methods."""

    def __init__(self, price: Decimal = Decimal("50000"), bars: int = 60):
        self.price = price
        self.bars = bars
        self.calls: list[str] = []

    def submit_order(self, order):
        self.calls.append("submit_order")
        raise AssertionError("ShadowRunner must never submit an order")

    def cancel_order(self, client_order_id):
        self.calls.append("cancel_order")
        raise AssertionError("ShadowRunner must never cancel an order")

    def get_position(self, symbol):
        self.calls.append("get_position")
        raise AssertionError("ShadowRunner must never query positions (no account access needed)")

    def get_account_info(self):
        self.calls.append("get_account_info")
        raise AssertionError("ShadowRunner must never query account info — equity comes from equity_fn")

    def get_current_price(self, symbol: str) -> Decimal:
        self.calls.append("get_current_price")
        return self.price

    def get_ohlcv(self, symbol, timeframe, limit=500):
        self.calls.append("get_ohlcv")
        idx = pd.date_range("2024-01-01", periods=self.bars, freq="1h")
        close = [float(self.price)] * self.bars
        return pd.DataFrame(
            {"open": close, "high": close, "low": close, "close": close, "volume": [100.0] * self.bars},
            index=idx,
        )

    def is_connected(self) -> bool:
        self.calls.append("is_connected")
        return True

    def get_exchange_name(self) -> str:
        return "fake_market_data"


def _risk_engine(tmp_path: Path, **config_overrides) -> RiskEngine:
    config = RiskConfig(**{
        "max_position_size_pct": 100.0, "max_total_exposure_pct": 100.0,
        "max_correlated_exposure_pct": 100.0,
        # Previously unenforced (real bug, now fixed in trading_intelligence/
        # risk/engine.py's Step 9b), so this fixture never needed to loosen
        # it before.
        "max_daily_turnover_pct": 1000.0,
        **config_overrides,
    })
    audit_log = AuditLog(tmp_path / "audit")
    return RiskEngine(config, tmp_path / "risk_state.json", audit_log)


class TestNeverExecutesAnything:
    def test_no_signal_touches_only_ohlcv(self, tmp_path):
        adapter = FakeMarketDataAdapter()
        runner = ShadowRunner(
            strategy=_NeverSignalsStrategy(), risk_engine=_risk_engine(tmp_path),
            market_data_adapter=adapter, equity_fn=lambda: Decimal("10000"),
        )
        runner.check_once("BTCUSDT", "1h")
        assert adapter.calls == ["get_ohlcv"]

    def test_signal_touches_only_ohlcv_and_price(self, tmp_path):
        adapter = FakeMarketDataAdapter()
        strategy = _AlwaysSignalsStrategy(stop_price=Decimal("49000"))
        runner = ShadowRunner(
            strategy=strategy, risk_engine=_risk_engine(tmp_path),
            market_data_adapter=adapter, equity_fn=lambda: Decimal("10000"),
        )
        runner.check_once("BTCUSDT", "1h")
        assert set(adapter.calls) == {"get_ohlcv", "get_current_price"}
        assert "submit_order" not in adapter.calls
        assert "get_account_info" not in adapter.calls


class TestDecisionRecording:
    def test_no_data_recorded_as_no_data(self, tmp_path):
        adapter = FakeMarketDataAdapter(bars=0)
        runner = ShadowRunner(
            strategy=_AlwaysSignalsStrategy(Decimal("49000")), risk_engine=_risk_engine(tmp_path),
            market_data_adapter=adapter, equity_fn=lambda: Decimal("10000"),
        )
        decision = runner.check_once("BTCUSDT", "1h")
        assert "no market data" in decision.note
        assert decision.proposal is None

    def test_no_signal_recorded(self, tmp_path):
        adapter = FakeMarketDataAdapter()
        runner = ShadowRunner(
            strategy=_NeverSignalsStrategy(), risk_engine=_risk_engine(tmp_path),
            market_data_adapter=adapter, equity_fn=lambda: Decimal("10000"),
        )
        decision = runner.check_once("BTCUSDT", "1h")
        assert "no signal" in decision.note
        assert decision.risk_decision is None

    def test_approved_signal_recorded_with_quantity(self, tmp_path):
        adapter = FakeMarketDataAdapter(price=Decimal("50000"))
        strategy = _AlwaysSignalsStrategy(stop_price=Decimal("49000"))
        runner = ShadowRunner(
            strategy=strategy, risk_engine=_risk_engine(tmp_path),
            market_data_adapter=adapter, equity_fn=lambda: Decimal("10000"),
        )
        decision = runner.check_once("BTCUSDT", "1h")
        assert decision.risk_decision is not None
        assert decision.risk_decision.approved is True
        assert decision.risk_decision.quantity is not None
        assert "APPROVE" in decision.note

    def test_rejected_signal_recorded_with_reason(self, tmp_path):
        adapter = FakeMarketDataAdapter(price=Decimal("50000"))
        # Kill switch active -> risk engine rejects deterministically
        risk_engine = _risk_engine(tmp_path)
        risk_engine.activate_kill_switch("test")
        strategy = _AlwaysSignalsStrategy(stop_price=Decimal("49000"))
        runner = ShadowRunner(
            strategy=strategy, risk_engine=risk_engine,
            market_data_adapter=adapter, equity_fn=lambda: Decimal("10000"),
        )
        decision = runner.check_once("BTCUSDT", "1h")
        assert decision.risk_decision.approved is False
        assert decision.risk_decision.reason == "KILL_SWITCH_ACTIVE"
        assert "REJECT" in decision.note

    def test_decisions_accumulate_across_calls(self, tmp_path):
        adapter = FakeMarketDataAdapter()
        runner = ShadowRunner(
            strategy=_NeverSignalsStrategy(), risk_engine=_risk_engine(tmp_path),
            market_data_adapter=adapter, equity_fn=lambda: Decimal("10000"),
        )
        runner.check_once("BTCUSDT", "1h")
        runner.check_once("BTCUSDT", "1h")
        assert len(runner.decisions) == 2

    def test_equity_fn_is_used_for_sizing(self, tmp_path):
        """A larger equity_fn value should produce a larger approved quantity,
        proving ShadowRunner actually passes it through to the real RiskEngine."""
        adapter = FakeMarketDataAdapter(price=Decimal("50000"))
        strategy = _AlwaysSignalsStrategy(stop_price=Decimal("49000"))

        small_runner = ShadowRunner(
            strategy=strategy, risk_engine=_risk_engine(tmp_path / "small"),
            market_data_adapter=adapter, equity_fn=lambda: Decimal("1000"),
        )
        large_runner = ShadowRunner(
            strategy=strategy, risk_engine=_risk_engine(tmp_path / "large"),
            market_data_adapter=adapter, equity_fn=lambda: Decimal("100000"),
        )
        small_decision = small_runner.check_once("BTCUSDT", "1h")
        large_decision = large_runner.check_once("BTCUSDT", "1h")
        assert large_decision.risk_decision.quantity > small_decision.risk_decision.quantity
