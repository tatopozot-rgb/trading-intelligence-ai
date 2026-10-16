"""Tests for research_opciones_xsp (synthetic prices, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_opciones_xsp as rx


def _px(start="2024-01-02", n=900, drift=0.0, vix=16.0, seed=0):
    days = pd.bdate_range(start, periods=n)
    rng = np.random.default_rng(seed)
    spx = 5000 * np.exp(np.cumsum(drift + rng.normal(0, 0.008, n)))
    px = pd.DataFrame({"spx": spx, "vix": vix}, index=days)
    px["sma200"] = px["spx"].rolling(200).mean()
    return px.dropna()


def test_black_scholes_put_call_parity_and_spread_bounds():
    s, k, t, v = 500.0, 500.0, 30 / 365, 0.16
    c = rx.bs_call(s, k, t, v)
    put = c - s * np.exp(-rx.DIV * t) + k * np.exp(-rx.RATE * t)
    assert put > 0
    val = rx.spread_value(s, k, t, v)
    assert 0 < val < rx.WIDTH * rx.MULT
    assert val == pytest.approx(52, abs=6)  # ~half the width at the money
    assert rx.spread_value(510, 500, 0, v) == 100 and rx.spread_value(490, 500, 0, v) == 0
    assert rx.spread_value(500.4, 500, 0, v) == pytest.approx(40)


def test_entry_cost_uses_ibkr_commission_per_contract():
    fees, slip = rx.entry_cost(1.0)
    assert fees == pytest.approx(2 * (0.65 + 0.025 + 0.30))
    assert slip == pytest.approx(6.0)
    assert rx.entry_cost(2.0)[0] == pytest.approx(2 * fees)


def test_one_spread_at_a_time_about_monthly_and_capital_never_negative():
    px = _px(drift=0.001)
    book = rx.run(px, "2024-10-14", "2025-10-10", trend=False)
    assert 10 <= len(book.trades) <= 13
    assert min(book.equity) >= 0
    for a, b in zip(book.trades, book.trades[1:]):
        assert a["salida"] <= b["entrada"]
    closed = [t for t in book.trades if not t["salida"].startswith("abierto")]
    assert all(t["pago"] in (0.0, 100.0) or 0 <= t["pago"] <= 100 for t in closed)


def test_no_entry_when_capital_cannot_pay_a_spread():
    px = _px(drift=-0.003)
    book = rx.run(px, "2024-10-14", "2025-10-10", trend=False)
    assert book.capital >= 0 and len(book.trades) < 10


def test_trend_filter_stays_in_cash_in_a_falling_market():
    px = _px(drift=-0.003)
    book = rx.run(px, "2024-10-14", "2025-10-10", trend=True)
    assert len(book.trades) == 0
    assert book.equity[-1] == rx.CAPITAL


def test_higher_costs_lower_the_result_and_report_renders():
    px = _px(seed=3)
    a = rx.summarize(rx.run(px, "2024-10-14", "2025-10-10", False, 1.0), 259)
    b = rx.summarize(rx.run(px, "2024-10-14", "2025-10-10", False, 2.0), 259)
    assert b["neto_pct"] < a["neto_pct"]
    assert len(a["capital_diario"]) > 200


def test_evaluate_and_render_list_the_four_rules():
    px = _px(start="2023-09-01", n=1000, seed=5)
    res = rx.evaluate(px, 259)
    assert list(res["reglas"]) == [r[0] for r in rx.RULES]
    assert res["reglas"]["siempre, costes ×2"]["pasa"] is None
    text = rx.render(res, 259)
    assert "Veredicto" in text and "2025-26" in text


def test_parse_close_reads_cboe_and_fred_formats():
    cboe = rx.parse_close("DATE,OPEN,HIGH,LOW,CLOSE\n01/03/2024,14.0,15,13,14.5\n01/02/2024,13.0,14,12,13.5\n")
    assert list(cboe.values) == [13.5, 14.5] and cboe.index[0] == pd.Timestamp("2024-01-02")
    fred = rx.parse_close("observation_date,SP500\n2024-01-01,.\n2024-01-02,4742.83\n")
    assert len(fred) == 1 and fred.iloc[0] == pytest.approx(4742.83)


def test_parse_yahoo_chart_json():
    text = '{"chart": {"result": [{"timestamp": [1704205800, 1704292200], "indicators": {"quote": [{"close": [4742.8, null]}]}}]}}'
    out = rx.parse_yahoo(text)
    assert len(out) == 1 and out.index[0] == pd.Timestamp("2024-01-02")
