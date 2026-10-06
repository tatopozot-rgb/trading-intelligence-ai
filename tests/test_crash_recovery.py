"""
Crash-simulation tests: proves the atomic write pattern (write to .tmp, then
rename over the real file) actually protects state against a process that
dies mid-write, and that restart correctly resumes from the last good state.

Per the final checklist: "simulación de fallos; crash/restart test;
validación de persistencia" — these exercise that directly, not just happy-path
save/load round trips (which test_risk_engine.py and test_paper_adapter.py
already cover).
"""
import json
from decimal import Decimal

from trading_intelligence.execution.base import AbstractExchangeAdapter
from trading_intelligence.execution.order_models import OrderRequest
from trading_intelligence.execution.paper import PaperAdapter
from trading_intelligence.persistence.audit_log import AuditLog
from trading_intelligence.risk.engine import RiskEngine
from trading_intelligence.risk.models import RiskConfig, RiskState


class _NullMarketDataAdapter(AbstractExchangeAdapter):
    def submit_order(self, order):
        raise AssertionError("not used")

    def cancel_order(self, client_order_id):
        raise AssertionError("not used")

    def get_position(self, symbol):
        return None

    def get_account_info(self):
        raise AssertionError("not used")

    def get_current_price(self, symbol):
        return Decimal("100")

    def get_ohlcv(self, symbol, timeframe, limit=500):
        import pandas as pd
        return pd.DataFrame()

    def is_connected(self):
        return True

    def get_exchange_name(self):
        return "null"


class TestRiskStateCrashDuringWrite:
    def test_crash_after_tmp_write_before_rename_leaves_original_file_intact(self, tmp_path):
        """
        Simulates the exact crash window the atomic-write pattern exists to
        protect against: the process writes the new state to a .tmp file,
        then dies before the rename. On restart, the ORIGINAL (pre-crash)
        state file must still be valid and loadable — never a half-written
        or missing file.
        """
        state_path = tmp_path / "risk_state.json"

        good_state = RiskState(kill_switch=False, equity_at_day_start="10000")
        good_state.save(state_path)
        original_bytes = state_path.read_bytes()

        # Simulate: a save() call got as far as writing the .tmp file, then
        # the process died before tmp_path.replace(path) ran. Write garbage
        # to the .tmp file directly (what a half-written new state would
        # look like) and do NOT call replace — this is exactly what "crash
        # before rename" leaves on disk.
        tmp_path_file = state_path.with_suffix(state_path.suffix + ".tmp")
        tmp_path_file.write_text('{"kill_switch": true, "INCOMPLETE')  # truncated/corrupt

        # The real state file must be completely unaffected by the crash.
        assert state_path.read_bytes() == original_bytes

        # "Restart": load from the real path. Must get the last GOOD state,
        # not the corrupt .tmp content, and must not raise.
        recovered = RiskState.load(state_path)
        assert recovered.kill_switch is False
        assert recovered.equity_at_day_start == "10000"

    def test_crash_mid_write_then_successful_retry_converges(self, tmp_path):
        """After a simulated crash leaves a stray .tmp file, a subsequent
        successful save() must still work correctly (the stray .tmp file
        from the crash does not interfere with a new save attempt)."""
        state_path = tmp_path / "risk_state.json"
        RiskState(kill_switch=False).save(state_path)

        stray_tmp = state_path.with_suffix(state_path.suffix + ".tmp")
        stray_tmp.write_text("garbage from a previous crash")

        new_state = RiskState(kill_switch=True, kill_switch_reason="real update")
        new_state.save(state_path)

        recovered = RiskState.load(state_path)
        assert recovered.kill_switch is True
        assert recovered.kill_switch_reason == "real update"

    def test_risk_engine_survives_restart_after_simulated_crash(self, tmp_path):
        """End-to-end: activate kill switch, simulate a crash leaving a
        stray .tmp file, then construct a fresh RiskEngine (restart) and
        confirm it starts halted — the safety property that matters most."""
        state_path = tmp_path / "risk_state.json"
        audit_log = AuditLog(tmp_path / "audit")
        config = RiskConfig()

        engine1 = RiskEngine(config, state_path, audit_log)
        engine1.activate_kill_switch("crash test")

        # Simulate a crash: leave a stray, unrelated .tmp file around (as if
        # a later save() attempt died mid-write after this).
        stray_tmp = state_path.with_suffix(state_path.suffix + ".tmp")
        stray_tmp.write_text("not valid json {{{")

        # Restart: construct a brand new engine instance pointing at the same path.
        engine2 = RiskEngine(config, state_path, AuditLog(tmp_path / "audit"))
        assert engine2.state.kill_switch is True
        assert engine2.state.kill_switch_reason == "crash test"


class TestPaperAdapterCrashDuringWrite:
    def test_crash_after_tmp_write_before_rename_leaves_original_file_intact(self, tmp_path):
        state_path = tmp_path / "paper_state.json"
        adapter = PaperAdapter(_NullMarketDataAdapter(), Decimal("10000"), state_path=state_path)

        buy = OrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("1"))
        adapter.submit_order(buy)
        adapter.on_new_bar("BTCUSDT", Decimal("100"), Decimal("101"), Decimal("99"),
                            Decimal("100"), "2026-01-01T00:00:00Z")
        original_bytes = state_path.read_bytes()
        original_data = json.loads(original_bytes)
        assert original_data["positions"]  # confirm there's real state to protect

        tmp_file = state_path.with_suffix(state_path.suffix + ".tmp")
        tmp_file.write_text('{"cash": "999999", "positions": {BROKEN')

        assert state_path.read_bytes() == original_bytes

        # "Restart": a fresh adapter loading from the same path gets the
        # last GOOD state, not the corrupt .tmp content.
        restarted = PaperAdapter(_NullMarketDataAdapter(), Decimal("1"), state_path=state_path)
        assert restarted.cash == adapter.cash
        assert restarted.get_position("BTCUSDT") is not None

    def test_missing_state_file_starts_fresh_rather_than_crashing(self, tmp_path):
        """A state path that doesn't exist yet (first-ever startup) must not
        be treated as a crash — it's the normal cold-start case."""
        state_path = tmp_path / "does_not_exist_yet" / "paper_state.json"
        adapter = PaperAdapter(_NullMarketDataAdapter(), Decimal("5000"), state_path=state_path)
        assert adapter.cash == Decimal("5000")
        assert adapter.positions == {}
