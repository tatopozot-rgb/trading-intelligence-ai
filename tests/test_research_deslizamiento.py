"""Tests for research_deslizamiento (synthetic files and candles, no network)."""
import json

import pandas as pd
import pytest

from trading_intelligence.backtesting import research_deslizamiento as rs


def test_bp_sign_is_against_us():
    assert rs.bp(100.0, 100.02, "BUY", True) == pytest.approx(2.0)
    assert rs.bp(100.0, 99.98, "SELL", True) == pytest.approx(2.0)
    assert rs.bp(100.0, 99.98, "BUY", False) == pytest.approx(2.0)  # a long's stop filled lower
    assert rs.bp(100.0, 100.02, "SELL", False) == pytest.approx(2.0)
    assert rs.bp(None, 1.0, "BUY", True) is None


def _bars(rows, start="2026-10-15 10:01"):
    idx = pd.date_range(start, periods=len(rows), freq="min", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def test_gap_model_fills_a_stop_at_the_open_beyond_it():
    bars = _bars([(100, 101, 99.5, 100), (98, 98.5, 97, 98)])  # gaps through a long stop at 99
    assert rs.gap_fill(bars, 99.0, "BUY", "stop") == 98.0
    assert rs.gap_fill(_bars([(100, 100, 98, 99)]), 99.0, "BUY", "stop") == 99.0
    assert rs.gap_fill(_bars([(100, 103, 100, 103)]), 102.0, "BUY", "meta") == 102.0
    assert rs.gap_fill(_bars([(100, 100.5, 99.5, 100)]), 95.0, "BUY", "stop") is None


def test_paper_trades_and_summary(tmp_path):
    book = {"closed": [{"symbol": "SOLUSDT", "side": "BUY", "entry": "100.05", "exit": "99", "qty": "1", "pnl": "-1",
                        "why": "stop", "opened": "2026-10-15T10:00:20+00:00", "at": "2026-10-15T10:05:00+00:00"}]}
    p = tmp_path / "paper.json"
    p.write_text(json.dumps(book))

    def candles(sym, a, b):
        full = _bars([(100, 100.1, 99.9, 100), (99.5, 99.6, 99.4, 99.5), (98.8, 98.9, 98.5, 98.6)],
                     start="2026-10-15 10:00")
        return full[(full.index >= a) & (full.index < b)]

    t = rs.paper_trades(p, "practica_1x", candles)[0]
    assert t.entry_ref == 100.0 and t.entry_bp() == pytest.approx(5.0)
    assert t.exit_fill == 98.8 and t.exit_bp() == pytest.approx((99 - 98.8) / 99 * 1e4)
    s = rs.summarize([t])
    assert s["practica_1x"]["salida_por_motivo"]["stop"]["n"] == 1
    assert "practica_1x" in rs.render(s, 1)


def test_real_entry_matches_the_filled_order(tmp_path):
    state = {"events": [{"at": "2026-10-14T12:00:00+00:00", "kind": "OPEN", "symbol": "ADAUSDT", "side": "BUY",
                         "text": "BUY 50 ADAUSDT @ 0.6000 SL 0.5800 TP 0.6400 riesgo 2% calidad 0.5"}]}
    orders = {"c1": {"state": "FILLED", "symbol": "ADAUSDT", "side": "BUY", "reduce_only": False, "avg": "0.6003",
                     "at": "2026-10-14T12:00:01+00:00"},
              "c2": {"state": "FILLED", "symbol": "ADAUSDT", "side": "SELL", "reduce_only": True, "avg": "0.59",
                     "at": "2026-10-14T13:00:00+00:00"}}
    (tmp_path / "state.json").write_text(json.dumps(state))
    (tmp_path / "orders.json").write_text(json.dumps(orders))
    exits = [{"symbol": "ADAUSDT", "closed": "2026-10-15T00:00:00+00:00", "why": "stop", "exit_ref": "0.58",
              "exit_fill": "0.5797"}]
    t = rs.real_trades(tmp_path / "state.json", tmp_path / "orders.json", exits)[0]
    assert t.entry_bp() == pytest.approx(5.0)
    assert t.exit_bp() == pytest.approx((0.58 - 0.5797) / 0.58 * 1e4)


def test_main_writes_no_quantity_or_result(tmp_path):
    book = {"closed": [{"symbol": "SOLUSDT", "side": "SELL", "entry": "100", "exit": "101", "qty": "3", "pnl": "-3.1",
                        "why": "stop", "opened": "2026-10-15T10:00:00+00:00", "at": "2026-10-15T10:05:00+00:00"}]}
    (tmp_path / "paper.json").write_text(json.dumps(book))
    out = tmp_path / "out"
    assert rs.main(["--practica", f"p1={tmp_path / 'paper.json'}", "--sin-velas", "--salida", str(out)]) == 0
    text = next(out.glob("*.csv")).read_text()
    assert "pnl" not in text and "qty" not in text and "-3.1" not in text
