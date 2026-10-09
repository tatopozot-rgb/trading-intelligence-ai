"""XM / MT5 phase 1: read-only connector, instrument sheet and the pre-entry check. No terminal:
a fake MetaTrader5 module returns MetaQuotes' documented shapes."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

from trading_intelligence.live import xm_mt5 as X

NOW = datetime(2026, 10, 9, 15, tzinfo=timezone.utc)

SYMBOLS = {
    # gold: 0.01 lot x 100 oz = 1 oz exposure
    "GOLD": dict(info=dict(trade_mode=4, volume_min=0.01, volume_step=0.01, volume_max=50.0, trade_contract_size=100.0,
                           trade_tick_value=1.0, trade_tick_size=0.01, swap_long=-55.0, swap_short=25.0, swap_mode=1,
                           trade_stops_level=0, point=0.01),
                 tick=dict(bid=2600.0, ask=2600.35), margin=26.0),
    # EURUSD: 0.01 lot x 100000 = 1000 EUR exposure
    "EURUSD": dict(info=dict(trade_mode=4, volume_min=0.01, volume_step=0.01, volume_max=100.0,
                             trade_contract_size=100000.0, trade_tick_value=1.0, trade_tick_size=0.00001,
                             swap_long=-7.0, swap_short=1.5, swap_mode=1, trade_stops_level=0, point=0.00001),
                   tick=dict(bid=1.08500, ask=1.08510), margin=1.09),
}


class FakeMt5:
    def __init__(self, equity=1000.0, mode=0, tick_age=5, trade_mode=None, now=NOW):
        self.equity, self.mode, self.tick_age, self.trade_mode, self.now = equity, mode, tick_age, trade_mode, now
        self.selected = []

    def initialize(self, *a, **k):
        assert not a and not k, "never pass login, password or server"
        return True

    def shutdown(self):
        return True

    def last_error(self):
        return (0, "ok")

    def account_info(self):
        return NS(trade_mode=self.mode, currency="USD", leverage=1000, balance=self.equity, equity=self.equity,
                  margin_free=self.equity, trade_allowed=True, login=12345678, name="owner")

    def symbol_select(self, symbol, enable):
        self.selected.append(symbol)
        return True

    def symbol_info(self, symbol):
        if symbol not in SYMBOLS:
            return None
        info = dict(SYMBOLS[symbol]["info"])
        if self.trade_mode is not None:
            info["trade_mode"] = self.trade_mode
        return NS(**info)

    def symbol_info_tick(self, symbol):
        return NS(**SYMBOLS[symbol]["tick"], time=int(self.now.timestamp()) - self.tick_age)

    def order_calc_margin(self, action, symbol, volume, price):
        return SYMBOLS[symbol]["margin"]

    def copy_rates_from_pos(self, symbol, timeframe, start, count):
        t0 = int(NOW.timestamp()) - count * 1200
        return [{"time": t0 + i * 1200, "open": 1.0 + i, "high": 2.0 + i, "low": 0.5 + i, "close": 1.5 + i,
                 "tick_volume": 10, "spread": 1, "real_volume": 0} for i in range(count)]

    def order_send(self, request):
        raise AssertionError("phase 1 must never reach order_send")


def _reader(**kw):
    r = X.XmReader(FakeMt5(**kw), clock=lambda: NOW)
    r.connect()
    return r


def test_the_sheet_reads_spread_lot_margin_and_swap():
    r = _reader()
    s = r.sheet("GOLD")
    assert s.spread == Decimal("0.35") and s.spread_pct.quantize(Decimal("0.0001")) == Decimal("0.0135")
    assert s.volume_min == Decimal("0.01") and s.contract_size == Decimal("100")
    assert s.min_lot_notional.quantize(Decimal("0.01")) == Decimal("2600.18")  # 1 oz, from the broker's tick value
    assert s.min_lot_margin == Decimal("26.0") and s.swap_long == Decimal("-55.0") and s.market_open
    assert r.account().leverage == 1000 and "GOLD" in r._mt5._m.selected  # added to Market Watch


def test_an_entry_is_refused_when_the_minimum_lot_is_too_big_for_the_equity():
    r = _reader(equity=100.0)
    no = X.check_entry(r.sheet("GOLD"), "BUY", r.account())
    assert any("apalancamiento efectivo 26.0x > máximo 2x" in n for n in no)


def test_an_entry_is_authorized_when_every_check_passes():
    r = _reader(equity=1000.0)
    assert X.check_entry(r.sheet("EURUSD"), "BUY", r.account()) == []
    assert X.check_entry(r.sheet("EURUSD"), "SELL", r.account()) == []


def test_a_closed_market_or_a_close_only_instrument_is_refused():
    r = _reader(tick_age=3600)
    assert any("mercado cerrado" in n for n in X.check_entry(r.sheet("EURUSD"), "BUY", r.account()))
    r = _reader(trade_mode=3)
    for side in ("BUY", "SELL"):
        assert any("SOLO_CIERRE" in n for n in X.check_entry(r.sheet("EURUSD"), side, r.account()))


def test_a_wide_spread_is_refused():
    r = _reader()
    caps = X.EntryCaps(max_spread_pct=Decimal("0.01"))
    assert any("spread" in n for n in X.check_entry(r.sheet("GOLD"), "BUY", r.account(), caps))


def test_phase_1_has_no_path_to_orders_and_no_credentials():
    r = _reader()
    with pytest.raises(X.OrdersDisabled):
        r._mt5.order_send({})
    with pytest.raises(X.OrdersDisabled):
        X.XmKlines(r).submit_order(None)
    assert "12345678" not in repr(r.account()) and "owner" not in repr(r.account())


def test_candles_feed_the_engine_with_utc_bars():
    feed = X.XmKlines(_reader())
    frame = feed.get_ohlcv("EURUSD", "20m", 3)
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"] and len(frame) == 3
    assert str(frame.index.tz) == "UTC" and frame.index[1] - frame.index[0] == __import__("pandas").Timedelta("20min")
    assert feed.get_current_price("EURUSD") == Decimal("1.08505")
    with pytest.raises(ValueError):
        feed.get_ohlcv("EURUSD", "7m", 3)


def test_an_unknown_symbol_says_so():
    with pytest.raises(X.XmError, match="no está disponible"):
        _reader().sheet("OIL123")


def test_the_cli_prints_the_sheet_and_the_verdict(capsys):
    live = datetime.now(timezone.utc)  # the CLI reads the real clock
    assert X.main(["fichas", "GOLD", "EURUSD"], mt5=FakeMt5(equity=100.0, now=live)) == 0
    out = capsys.readouterr().out
    assert "GOLD: abierto" in out and "COMPRA: NO" in out and "swap por noche" in out
    assert X.main(["cuenta"], mt5=FakeMt5()) == 0
    assert "1:1000" in capsys.readouterr().out


def test_the_operator_runs_xm_only_in_shadow(tmp_path, capsys):
    from trading_intelligence.live import operator as O

    with pytest.raises(SystemExit):
        O.main(["--dir", str(tmp_path), "iniciar", "--capital", "50", "--broker", "xm", "--simbolos", "GOLD",
                "--real"])
    assert "XM with real money does not exist yet" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        O.main(["--dir", str(tmp_path), "iniciar", "--capital", "50", "--broker", "xm"])
    assert "--simbolos" in capsys.readouterr().err
    assert not (tmp_path / "session.json").exists()


def test_a_shadow_session_runs_the_engine_on_xm_candles(tmp_path, monkeypatch):
    from trading_intelligence.live import operator as O

    monkeypatch.setattr(X, "load_mt5", lambda: FakeMt5(now=datetime.now(timezone.utc)))
    O.main(["--dir", str(tmp_path), "iniciar", "--capital", "100", "--broker", "xm", "--simbolos", "EURUSD",
            "--temporalidad", "20m", "--max-iteraciones", "1"])
    meta = __import__("json").loads((tmp_path / "meta.json").read_text())
    assert meta["broker"] == "xm" and meta["real"] is False and meta["symbols"] == ["EURUSD"]
    loop = __import__("json").loads((tmp_path / "engine" / "loop.json").read_text())
    assert loop["journal"] and loop["journal"][-1]["symbol"] == "EURUSD"
    assert list(tmp_path.glob("reporte_final_*.md"))
