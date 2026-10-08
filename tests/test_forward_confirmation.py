"""Tests for the pre-registered 4h forward confirmation (docs/PREREG_4H_FORWARD.md). No network."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import forward_confirmation as fc


def _sym(returns):
    return {"trade_returns": returns, "trade_pnls": [r * 1000 for r in returns]}


GOOD = [0.02, 0.025, 0.018, 0.03, -0.005] * 8
LOSING = [-0.01, 0.005, -0.008, 0.002] * 10


def test_registration_is_what_the_doc_says():
    assert fc.TIMEFRAME == "4h" and fc.FORWARD_START == "2026-10-01"
    assert len(set(fc.SYMBOLS)) == 12
    assert fc.LOOKS == {"2027-04-01": False, "2027-10-01": True, "2028-10-01": True}
    assert fc.FINAL_LOOK == max(fc.LOOKS) and fc.ALPHA == 0.025


def test_futility_look_can_refute_but_never_go():
    assert fc.verdict([_sym(GOOD)], "2027-04-01")["outcome"] == "INCONCLUSIVE"
    assert fc.verdict([_sym(LOSING)], "2027-04-01")["outcome"] == "REFUTED"


def test_go_looks():
    assert fc.verdict([_sym(GOOD)], "2027-10-01")["outcome"] == "GO"
    assert fc.verdict([_sym(LOSING)], "2027-10-01")["outcome"] == "REFUTED"


def test_too_few_trades_is_inconclusive_then_no_go_at_the_final_look():
    assert fc.verdict([_sym(GOOD[:10])], "2027-10-01")["outcome"] == "INCONCLUSIVE"
    assert fc.verdict([_sym(GOOD[:10])], "2028-10-01")["outcome"] == "NO-GO"
    assert fc.verdict([_sym([])], "2028-10-01")["outcome"] == "NO-GO"


def test_positive_but_not_significant_is_not_go():
    noisy = [0.30, -0.25, 0.28, -0.27, 0.01] * 8
    v = fc.verdict([_sym(noisy)], "2027-10-01")
    assert v["p_value"] >= fc.ALPHA and v["outcome"] == "INCONCLUSIVE"


def test_unregistered_look_is_rejected():
    with pytest.raises(ValueError, match="not a registered look"):
        fc.verdict([_sym(GOOD)], "2027-01-01")


def test_early_look_is_refused_before_any_data_is_fetched(tmp_path):
    with pytest.raises(SystemExit):
        fc.main(["--look", "2027-10-01", "--out", str(tmp_path)],
                now=datetime(2027, 9, 30, 23, 59, tzinfo=timezone.utc))
    assert not any(tmp_path.iterdir())


def test_forward_symbol_counts_only_closed_trades():
    rng = np.random.default_rng(7)
    close = 100 * np.cumprod(1 + rng.normal(0.001, 0.02, 800))
    idx = pd.date_range("2026-10-01", periods=800, freq="4h", tz="UTC")
    data = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                         "close": close, "volume": 1.0}, index=idx)
    out = fc.forward_symbol("BTCUSDT", data, fc.PRIMARY)
    assert out["bars"] == 800 and out["gaps"] == 0
    assert len(out["trade_returns"]) == len(out["trade_pnls"])
