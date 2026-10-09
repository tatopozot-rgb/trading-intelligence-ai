"""Tests for the Binance Spot universe scan. No network."""
import json

from trading_intelligence.backtesting import universe_scan as us


def _sym(symbol, base, quote="USDT", status="TRADING", min_notional="5"):
    return {"symbol": symbol, "baseAsset": base, "quoteAsset": quote, "status": status,
            "filters": [{"filterType": "NOTIONAL", "minNotional": min_notional}]}


def _get(symbols, volumes):
    def get(url, timeout):
        if "exchangeInfo" in url:
            return json.dumps({"symbols": symbols}).encode()
        return json.dumps([{"symbol": s, "quoteVolume": str(v)} for s, v in volumes.items()]).encode()
    return get


def test_scan_filters_and_ranks():
    symbols = [_sym("BTCUSDT", "BTC"), _sym("ETHUSDT", "ETH"), _sym("USDCUSDT", "USDC"), _sym("EURUSDT", "EUR"),
               _sym("BTCUPUSDT", "BTCUP"), _sym("JUPUSDT", "JUP"), _sym("OLDUSDT", "OLD", status="BREAK"),
               _sym("ETHBTC", "ETH", quote="BTC"), _sym("PAXGUSDT", "PAXG", min_notional="10")]
    vols = {"BTCUSDT": 9e9, "ETHUSDT": 5e9, "USDCUSDT": 8e9, "EURUSDT": 1e8, "BTCUPUSDT": 1e7, "JUPUSDT": 2e8,
            "OLDUSDT": 1e9, "ETHBTC": 1e9, "PAXGUSDT": 3e7}
    res = us.scan(get=_get(symbols, vols), base_url="https://x")
    assert [r["symbol"] for r in res["top"]] == ["BTCUSDT", "ETHUSDT", "JUPUSDT", "PAXGUSDT"]
    assert res["paxgusdt_rank"] == 4 and res["top"][3]["min_notional"] == 10.0
    assert res["xautusdt"] == "not listed"


def test_leveraged_detection_does_not_catch_real_coins():
    bases = {"BTC", "ETH", "J", "JUP"}
    assert us.is_leveraged("BTCUP", bases) and us.is_leveraged("ETHDOWN", bases)
    assert not us.is_leveraged("JUP", bases)


def test_compare_pools_groups():
    def s(name, rets):
        return {"symbol": name, "oos_trade_returns": rets, "oos_trade_pnls": [r * 100 for r in rets],
                "framework_go": False, "oos_fees": 1.0, "oos_max_dd_pct_by_fold": [-3.0], "buy_hold_oos_return": 0.0}
    results = {"symbols": [s("BTCUSDT", [0.02, -0.01]), s("NEWUSDT", [-0.02, -0.01, 0.005])]}
    table, out = us.compare(results, ["BTCUSDT", "ETHUSDT"])
    assert out["top-30 (all)"]["oos_trades"] == 5 and out["top-30 new (not in the 12)"]["oos_trades"] == 3
    assert "| 12 live (section 45" in table and "top-30 ∩ 12 live" in table
