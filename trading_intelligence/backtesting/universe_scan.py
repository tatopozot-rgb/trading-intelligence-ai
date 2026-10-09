"""
Binance Spot universe scan (research only: public endpoints, no key, no orders).

`scan`: top-30 USDT pairs by 24h quote volume among pairs that are TRADING, not
stablecoins/fiat, and not leveraged tokens; also whether XAUTUSDT exists and PAXGUSDT's
rank. `compare`: pools the section-45 walk-forward results of the live 4h
`tendencia_rango` rule on the top-30 set, against the 12 live symbols (a check of an
already-specified rule, not a new pre-registration).
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from multiprocessing import Pool
from pathlib import Path
from typing import Callable, Optional

from trading_intelligence.backtesting import real_data_validation as rdv
from trading_intelligence.data.binance_public_feed import DEFAULT_BASE_URL, _urllib_get

TOP_N = 30
STABLE_OR_FIAT = {"USDC", "FDUSD", "TUSD", "USDP", "DAI", "BUSD", "USDD", "PYUSD", "USDE", "USD1", "UST", "USTC", "RLUSD",
                  "EUR", "EURI", "AEUR", "GBP", "TRY", "BRL", "ARS", "JPY", "AUD", "RUB", "UAH", "ZAR", "PLN",
                  "MXN", "COP", "CZK", "RON", "NGN", "IDRT", "BIDR", "BVND", "XUSD", "USDS", "SUSD"}
LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")


def _min_notional(sym: dict) -> Optional[float]:
    for f in sym.get("filters", []):
        if f.get("filterType") in ("NOTIONAL", "MIN_NOTIONAL"):
            return float(f.get("minNotional", 0) or 0)
    return None


def is_leveraged(base: str, bases: set[str]) -> bool:
    for suffix in LEVERAGED_SUFFIXES:
        root = base[: -len(suffix)]
        if base.endswith(suffix) and len(root) >= 3 and root in bases:
            return True
    return False


def scan(get: Callable[[str, float], bytes] = _urllib_get, base_url: str = DEFAULT_BASE_URL) -> dict:
    info = json.loads(get(f"{base_url}/api/v3/exchangeInfo?permissions=SPOT", 60.0))
    tickers = {t["symbol"]: t for t in json.loads(get(f"{base_url}/api/v3/ticker/24hr", 60.0))}
    usdt = [s for s in info["symbols"] if s.get("quoteAsset") == "USDT"]
    bases = {s["baseAsset"] for s in usdt}
    eligible = []
    for s in usdt:
        if s.get("status") != "TRADING" or s["baseAsset"] in STABLE_OR_FIAT or is_leveraged(s["baseAsset"], bases):
            continue
        t = tickers.get(s["symbol"])
        if t is None:
            continue
        eligible.append({"symbol": s["symbol"], "base": s["baseAsset"], "quote_volume_24h": float(t["quoteVolume"]),
                         "min_notional": _min_notional(s)})
    eligible.sort(key=lambda r: r["quote_volume_24h"], reverse=True)
    for rank, r in enumerate(eligible, 1):
        r["rank"] = rank
    all_symbols = {s["symbol"]: s.get("status") for s in info["symbols"]}
    paxg = next((r["rank"] for r in eligible if r["symbol"] == "PAXGUSDT"), None)
    return {"generated": datetime.now(timezone.utc).isoformat(), "source": base_url, "eligible_pairs": len(eligible),
            "top": eligible[:TOP_N], "xautusdt": all_symbols.get("XAUTUSDT", "not listed"), "paxgusdt_rank": paxg}


WF_PROFILE, WF_TIMEFRAME, WF_START, WF_END = "tendencia_rango", "4h", "2022-10-01", "2026-10-01"  # section 45


def _walk_one(symbol: str) -> dict:
    start = datetime.fromisoformat(WF_START).replace(tzinfo=timezone.utc).isoformat()
    end = datetime.fromisoformat(WF_END).replace(tzinfo=timezone.utc).isoformat()
    try:
        return rdv._run_symbol((WF_PROFILE, symbol, WF_TIMEFRAME, start, end))
    except Exception as exc:  # noqa: BLE001 - a symbol without usable history is reported, not fatal
        return {"symbol": symbol, "excluded": f"{type(exc).__name__}: {exc}"[:200]}


def walk(symbols: list[str], workers: int) -> dict:
    with Pool(max(1, workers)) as pool:
        res = pool.map(_walk_one, symbols)
    return {"profile": WF_PROFILE, "timeframe": WF_TIMEFRAME, "start": WF_START, "end": WF_END,
            "symbols": [r for r in res if "excluded" not in r],
            "excluded": {r["symbol"]: r["excluded"] for r in res if "excluded" in r}}


def compare(results: dict, live_symbols: list[str]) -> tuple[str, dict]:
    syms = results["symbols"]
    groups = {"top-30 (all)": syms,
              "top-30 ∩ 12 live": [s for s in syms if s["symbol"] in live_symbols],
              "top-30 new (not in the 12)": [s for s in syms if s["symbol"] not in live_symbols]}
    out = {name: rdv.pool_verdict(g) if g else None for name, g in groups.items()}
    lines = ["| Set | Symbols | OOS trades | Mean net/trade | Median | PF | p | Worst fold DD | Verdict |",
             "|---|---|---|---|---|---|---|---|---|",
             "| 12 live (section 45, run 37787747047) | 12 | 235 | +3.06% | −2.33% | 1.90 | 0.090 | −5.6% | NO-GO |"]
    for name, g in groups.items():
        v = out[name]
        if v is None:
            continue
        lines.append(f"| {name} | {len(g)} | {v['oos_trades']} | {v['mean_net_return_per_trade']:+.2%} | "
                     f"{v['median_net_return_per_trade']:+.2%} | {v['profit_factor']:.2f} | {v['p_value']:.3f} | "
                     f"{v['worst_oos_fold_max_dd_pct']:.1f}% | {'GO' if v['go'] else 'NO-GO'} |")
    return "\n".join(lines), out


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Binance Spot universe scan (research only)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--out", type=Path, required=True)
    w = sub.add_parser("walk")
    w.add_argument("--symbols", nargs="+", required=True)
    w.add_argument("--workers", type=int, default=1)
    w.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("compare")
    c.add_argument("--results", type=Path, required=True)
    c.add_argument("--live-limits", type=Path, default=Path("config/live_limits.json"))
    c.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.cmd == "scan":
        res = scan()
        args.out.mkdir(parents=True, exist_ok=True)
        path = args.out / f"top30_{res['generated'][:10]}.json"
        path.write_text(json.dumps(res, indent=1) + "\n")
        print(" ".join(r["symbol"] for r in res["top"]))
        return 0
    if args.cmd == "walk":
        res = walk(args.symbols, args.workers)
        args.out.write_text(json.dumps(res, indent=1, default=str) + "\n")
        print(f"walk-forward done: {len(res['symbols'])} symbols, excluded {res['excluded']}")
        return 0
    live = json.loads(args.live_limits.read_text())["allowed_symbols"]
    results = json.loads(args.results.read_text())
    table, out = compare(results, live)
    args.out.write_text(json.dumps({"pooled": out, "excluded": results.get("excluded", {})},
                                   indent=1, default=str) + "\n")
    print(table)
    if results.get("excluded"):
        print("\nExcluded: " + "; ".join(f"{k} ({v})" for k, v in results["excluded"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
