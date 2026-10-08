"""The owner-facing report of a PaperLoop state file."""
import json

from trading_intelligence.execution.paper_report import explain, main, problems_in, render

STATE = {
    "symbols": ["BTCUSDT", "ETHUSDT"],
    "timeframe": "4h",
    "feed_origin": "https://data-api.binance.vision",
    "last_processed": "2026-10-07T16:00:00+00:00",
    "status": {"last_tick": "2026-10-07T22:08:16+00:00", "equity": "10050.5", "cash": "8000",
               "open_positions": ["ETHUSDT"], "kill_switch": False, "kill_switch_reason": "",
               "last_fetch_error": None, "stale_symbols": [], "last_gap_halt": None, "books_disagree": []},
    "journal": [
        {"bar": "2026-10-07T12:00:00+00:00", "symbol": "ETHUSDT", "action": "ENTRY_SUBMITTED",
         "regime": "BREAKOUT_UP", "close": "2400.5", "equity": "10000", "fills": [], "notes": []},
        {"bar": "2026-10-07T16:00:00+00:00", "symbol": "BTCUSDT", "action": "NO_TRADE:NO_STRATEGY_FOR_REGIME",
         "regime": "RANGE", "close": "62000", "equity": "10050.5", "fills": [], "notes": []},
        {"bar": "2026-10-07T16:00:00+00:00", "symbol": "ETHUSDT", "action": "HOLDING", "regime": "TREND_UP",
         "close": "2450", "equity": "10050.5",
         "fills": [{"side": "BUY", "status": "FILLED", "qty": "0.8", "price": "2401.7", "fee": "1.92"}], "notes": []},
    ],
    "trades": [{"symbol": "SOLUSDT", "quantity": "1", "entry_price": "150", "exit_price": "140",
                "pnl": "-10.3", "exit_reason": "STOP", "closed_at": "2026-10-06T08:00:00+00:00"}],
    "equity_history": [{"bar": "2026-10-07T12:00:00+00:00", "equity": "10000"},
                       {"bar": "2026-10-07T16:00:00+00:00", "equity": "10050.5"}],
}


def test_the_report_shows_the_latest_decision_per_symbol_with_its_reason():
    text = render(STATE)
    assert "**Estado: OK**" in text
    assert "| BTCUSDT | `2026-10-07T16:00:00+00:00` | 62,000.00 | RANGE | no opera: NO_STRATEGY_FOR_REGIME |" in text
    assert "| ETHUSDT |" in text and "posición abierta, se mantiene" in text
    assert "| ETHUSDT | BUY | 0.8 | 2,401.70 | 1.92 |" in text
    assert "1 trades · ganadores 0 · P&L total **-10.30**" in text
    assert "(+0.50%)" in text


def test_problems_turn_the_report_red():
    bad = json.loads(json.dumps(STATE))
    bad["status"].update(kill_switch=True, kill_switch_reason="daily loss", stale_symbols=["XRPUSDT"])
    assert len(problems_in(bad)) == 2
    assert "**Estado: ATENCIÓN**" in render(bad)


def test_unknown_actions_are_shown_verbatim():
    assert explain("SOMETHING_NEW") == "SOMETHING_NEW"
    assert explain("RISK_REJECTED:MAX_POSITIONS") == "rechazada por riesgo: MAX_POSITIONS"


def test_main_writes_the_summary_and_sets_the_exit_code(tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert main(["--state-dir", str(tmp_path / "missing")]) == 1
    (tmp_path / "live").mkdir()
    (tmp_path / "live" / "loop.json").write_text(json.dumps(STATE))
    assert main(["--state-dir", str(tmp_path / "live")]) == 0
    assert "Última decisión por símbolo" in summary.read_text(encoding="utf-8")


def test_a_state_without_history_renders():
    minimal = {k: v for k, v in STATE.items() if k not in ("journal", "trades", "equity_history")}
    text = render(minimal)
    assert "Ninguna todavía." in text and "Ninguno todavía." in text
