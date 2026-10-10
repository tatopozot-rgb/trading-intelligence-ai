"""Minimum stop distance (owner, 2026-10-10: a real AVAX stop at -0.28% was inside the noise)."""
from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from trading_intelligence.strategy.base import AbstractStrategy
from trading_intelligence.strategy.models import TradeProposal
from trading_intelligence.strategy.router import router_with_range_reversion
from trading_intelligence.strategy.stop_floor import StopFloor, with_stop_floor


class Fixed(AbstractStrategy):
    def __init__(self, stop):
        super().__init__("fixed_AVAXUSDT_1m", "AVAXUSDT", "1m", {})
        self.stop, self.exits = stop, 0

    def on_bar(self, data):
        return TradeProposal("fixed_AVAXUSDT_1m", "AVAXUSDT", "BUY", "MARKET", self.stop, "1m", "cross", 0.8, "t")

    def on_exit_signal(self, data, entry_price):
        self.exits += 1
        return True


DATA = pd.DataFrame({"open": [10.0], "high": [10.0], "low": [10.0], "close": [10.0], "volume": [1.0]})


def test_a_stop_inside_the_noise_is_moved_to_the_floor():
    p = StopFloor(Fixed(Decimal("9.972")), Decimal("2")).on_bar(DATA)  # the real AVAX case: -0.28%
    assert p.stop_price == Decimal("9.8") and "widened" in p.rationale


def test_a_stop_already_wider_is_kept_and_exits_are_unchanged():
    inner = Fixed(Decimal("9.5"))
    wrapped = StopFloor(inner, Decimal("2"))
    assert wrapped.on_bar(DATA).stop_price == Decimal("9.5")
    assert wrapped.on_exit_signal(DATA, Decimal("10")) is True and inner.exits == 1
    assert (wrapped.strategy_id, wrapped.symbol) == (inner.strategy_id, inner.symbol)  # re-attach after restart


def test_every_routed_strategy_gets_the_floor_and_none_means_unchanged():
    router = with_stop_floor(router_with_range_reversion("BTCUSDT"), Decimal("2"))
    assert all(isinstance(s, StopFloor) for s, _ in router._registry.values())
    plain = router_with_range_reversion("BTCUSDT")
    assert with_stop_floor(plain, None) is plain and not any(isinstance(s, StopFloor) for s, _ in plain._registry.values())
    with pytest.raises(ValueError):
        StopFloor(Fixed(Decimal("9")), Decimal("0"))


@pytest.mark.parametrize("timeframe,extra,expected", [("1m", [], "2"), ("1m", ["--stop-minimo", "3"], "3"),
                                                      ("4h", [], None), ("1m", ["--stop-minimo", "0"], None)])
def test_intraday_sessions_get_a_2_percent_floor_by_default(tmp_path, monkeypatch, timeframe, extra, expected):
    from tests.test_live_operator import FakeTrader
    from trading_intelligence.live import operator as O

    launched = []
    monkeypatch.setattr(O, "_trader", lambda real, journal: FakeTrader({"BTCUSDT": Decimal("100")}))
    monkeypatch.setattr(O, "_launch", lambda d, limits, meta, eq, it: launched.append(meta))
    O.main(["--dir", str(tmp_path), "iniciar", "--capital", "32", "--temporalidad", timeframe, "--real",
            "--perfil", "tendencia_rango", *extra])
    assert launched[0].get("min_stop_pct") == expected


def test_a_nonsense_floor_is_refused(tmp_path, capsys):
    from trading_intelligence.live import operator as O

    with pytest.raises(SystemExit):
        O.main(["--dir", str(tmp_path), "iniciar", "--capital", "32", "--temporalidad", "1m", "--stop-minimo", "x"])
    assert "--stop-minimo" in capsys.readouterr().err
