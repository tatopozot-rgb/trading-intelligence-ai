"""
The real futures bot through the two bars (leader, 2026-10-16), research only.

Preregistered in docs/research/real/PREREGISTRO.md before any run. The strategy that live/binance_futures.py runs with
real money (the practice desk with the BTC 50-day regime brake and the +-2 h event brake, config/futures_limits.json:
1x, risk 1-15% by quality, 50% per position, 3 positions, the 12 allowed symbols) is replayed with research_mesa over
the two judged years, in 30-day blocks chained so each block starts with the capital the previous one ended with.
Binance costs and per-order minimums come from two_way_backtest. Bar 1: net > 0 and net/drawdown >= 1 in both years.
Bar 2: deflated Sharpe >= 0.95 in 2025-26, N = 257 decisive tests, V = 1/T, daily returns over calendar days.
Public data only: no account, no key, no orders. Nothing here changes config/ or live/.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import research_deflactado as rd
from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.backtesting import two_way_backtest as tw

YEARS = (("2024-10-12", "2025-10-12"), ("2025-10-13", "2026-10-13"))
REAL_CAPITAL = 31.69
DECISIVE_N = 257
EVENT_HOURS = 2  # as config/eventos.json
ROWS = {"real": ("Real tal cual (31,69 USDT, riesgo 1-15%)", REAL_CAPITAL, None),
        "mil": ("Real con 1.000 USDT", 1000.0, None),
        "fijo2": ("Real con riesgo fijo 2% (31,69 USDT)", REAL_CAPITAL, 0.02)}
DESK = {"2024-10-12": 1.73, "2025-10-13": 0.20}  # re-measured practice desk, docs/research/saturado/
OUT_DIR = Path("docs/research/real")

SYMS: dict[str, Any] = {}
REGIME: dict[str, np.ndarray] = {}
EVENTS: dict[str, np.ndarray] = {}


def run_chained(syms: dict, bounds: list[tuple[int, int]], capital: float, risk: Optional[float],
                allow: Optional[dict] = None, entry_allow: Optional[dict] = None) -> dict:
    """Blocks one after another, each starting with the previous block's final capital. Returns the per-bar equity
    (bars after a session end stay flat), the trades and the capital at each block's start."""
    equity: list[float] = []
    trades: list[dict] = []
    starts: list[float] = []
    level = capital
    for lo, hi in bounds:
        starts.append(level)
        rep = rm.replay(syms, lo, hi, capital=level, risk_override=risk, allow=allow, entry_allow=entry_allow)
        end = level + sum(t["pnl"] for t in rep.trades)
        curve = list(rep.curve) or [level]
        curve += [curve[-1]] * (hi - lo - len(curve))
        curve[-1] = end
        equity.extend(curve)
        trades.extend({**t, "block_capital": level} for t in rep.trades)
        level = end
    return {"equity": equity, "trades": trades, "starts": starts}


def summarize(run: dict, times: np.ndarray, first: int, capital: float, n_decisive: int) -> dict:
    eq = np.array(run["equity"] or [capital], float)
    peak = np.maximum.accumulate(np.r_[capital, eq])
    dd = float(((peak - np.r_[capital, eq]) / peak).max() * 100)
    net = (eq[-1] / capital - 1) * 100
    idx = pd.to_datetime(times[first:first + len(eq)], utc=True)
    daily = pd.Series(eq, index=idx).groupby(idx.floor("D")).last()
    r = pd.concat([pd.Series([capital]), daily.reset_index(drop=True)]).pct_change().dropna()
    m = rd.moments(r)
    sr_year = m["sr_dia"] * np.sqrt(365)
    dsr = rd.deflated_sharpe(m["sr_dia"], m["T"], m["asimetria"], m["curtosis"], n_decisive, 1 / m["T"]) \
        if m["T"] > 2 else 0.0
    trades = run["trades"]
    pnl = [t["pnl"] / t["block_capital"] for t in trades]
    syms = sorted({t["symbol"] for t in trades})
    q = np.array_split(np.arange(len(eq)), 4)
    quarters = [round((eq[i[-1]] / (eq[i[0] - 1] if i[0] > 0 else capital) - 1) * 100, 1) for i in q if len(i)]
    return {"net_pct": round(net, 2), "max_dd_pct": round(dd, 2), "net_dd": round(net / dd, 2) if dd > 0 else None,
            "trades": len(trades), "win_rate": round(sum(p > 0 for p in pnl) / len(pnl) * 100, 1) if pnl else 0.0,
            "worst_trade_pct": round(min(pnl) * 100, 2) if pnl else 0.0,
            "fees": round(sum(t["fees"] for t in trades), 4), "funding": round(sum(t["funding"] for t in trades), 4),
            "symbols": syms, "quarters": quarters, "sharpe_anual": round(sr_year, 2), "dsr": round(dsr, 3),
            "final": round(float(eq[-1]), 2),
            "daily_equity": {str(d.date()): round(float(v), 4) for d, v in daily.items()}}


def passes_bar1(years: list[dict], key: str) -> bool:
    return all(y["rows"][key]["net_pct"] > 0 and (y["rows"][key]["net_dd"] or -99) >= 1 for y in years)


def recommend(years: list[dict]) -> tuple[bool, str]:
    """The preregistered decision rule."""
    bar1 = passes_bar1(years, "real")
    bar2 = years[-1]["rows"]["real"]["dsr"] >= rd.PASS_DSR
    if bar1 and bar2:
        return True, "seguir igual"
    if bar1:
        if all(y["rows"]["fijo2"]["net_pct"] > 0 for y in years):
            return False, "bajar el tamaño a riesgo fijo 2%"
        return False, "pausar las entradas nuevas"
    return False, "pausar las entradas nuevas y dejar que las abiertas terminen con su stop o meta"


def _year(task: tuple) -> tuple:
    key, first, bounds = task
    _, capital, risk = ROWS[key]
    return key, run_chained(SYMS, bounds, capital, risk, allow=REGIME, entry_allow=EVENTS)


def evaluate(times: np.ndarray, workers: int, n_decisive: int) -> dict:
    bounds = rm.blocks(len(times), tw.WARMUP)
    first = bounds[0][0]
    with Pool(max(1, min(workers, len(ROWS)))) as pool:
        out = pool.map(_year, [(k, first, bounds) for k in ROWS])
    return {k: summarize(run, times, first, ROWS[k][1], n_decisive) for k, run in out}


def build_masks(times: np.ndarray, extras: dict[str, dict], btc_d1: Any) -> None:
    global REGIME, EVENTS
    REGIME = rm.gates(times, list(SYMS), btc_d1, {s: x["h4"] for s, x in extras.items()})["b"]
    events = np.where(rm.near_event(times, rm.macro_events(), EVENT_HOURS), 0, rm.BOTH).astype(np.int8)
    EVENTS = {name: events for name in SYMS}


def render(years: list[dict], n_decisive: int) -> str:
    ok, what = recommend(years)
    real = [y["rows"]["real"] for y in years]
    L = ["# El bot real de futuros por los dos listones", "",
         "Preregistro: `docs/research/real/PREREGISTRO.md`, escrito antes de correr. La mesa con freno de régimen y de "
         "eventos, con los límites de `config/futures_limits.json`, costes de Binance Futuros (0,05% por lado, 0,02% de "
         "deslizamiento, financiación real) y mínimos por orden (BTC 100, ETH 20, resto 5 USDT). Bloques de 30 días "
         f"encadenados. Sharpe deflactado con N = {n_decisive} decisorias y V = 1/T.", "", "## Veredicto", "",
         f"- **{'Pasa' if ok else 'No pasa'}.** Real tal cual: neto/caída "
         + " ; ".join(f"{r['net_dd']} ({r['net_pct']:+.1f}% / {r['max_dd_pct']}%)" for r in real)
         + f" (listón: neto positivo y ≥ 1 los dos años: {'sí' if passes_bar1(years, 'real') else 'no'}); Sharpe "
         f"deflactado 2025-26 {real[-1]['dsr']} (listón {rd.PASS_DSR}).",
         f"- **Recomendación preregistrada: {what}.**"]
    for y in years:
        L += ["", f"## {y['label']} (mesa de práctica re-medida con 1.000 USDT: neto/caída {y['desk']})", "",
              "| Fila | Neto % | Máx. caída | Neto/caída | Ops | Acierto | Peor op. | Comisiones | Financiación | "
              "Sharpe anual | Sharpe deflactado | Capital final | Trimestres (neto %) | Monedas operadas |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for key, r in y["rows"].items():
            L.append(f"| {ROWS[key][0]} | {r['net_pct']:+.1f}% | {r['max_dd_pct']}% | {r['net_dd']} | {r['trades']} | "
                     f"{r['win_rate']}% | {r['worst_trade_pct']:+.1f}% | {r['fees']} | {r['funding']} | "
                     f"{r['sharpe_anual']} | {r['dsr']} | {r['final']} | "
                     + " / ".join(f"{q:+.1f}" for q in r["quarters"]) + f" | {len(r['symbols'])} |")
    L += ["", "La peor operación es sobre el capital del bloque. Comisiones y financiación en USDT. Con 31,69 USDT y "
          "50% por posición, BTC (100 USDT) y ETH (20 USDT) no llegan al mínimo. El capital diario está en el JSON. "
          "Un resultado pasado no promete uno futuro."]
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    global SYMS
    parser = argparse.ArgumentParser(description="Bot real de futuros por los dos listones (investigación)")
    parser.add_argument("--simbolos", nargs="+", default=list(tw.SYMBOLS))
    parser.add_argument("--decisorias", type=int, default=DECISIVE_N)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    years = []
    for a, b in YEARS:
        end = datetime.fromisoformat(b).replace(tzinfo=timezone.utc)
        warm = datetime.fromisoformat(a).replace(tzinfo=timezone.utc) - timedelta(minutes=5 * tw.WARMUP)
        with Pool(max(1, args.workers)) as pool:
            loaded = pool.map(rm._load_symbol, [(s, warm.isoformat(), end.isoformat()) for s in args.simbolos])
        for sym, _, note, _ in loaded:
            print(f"{a}→{b} {sym}: {note}")
        extras = {s: x for s, a_, _, x in loaded if a_ is not None}
        times, SYMS = rm.align({s: x for s, x, _, _ in loaded if x is not None})
        build_masks(times, extras, extras["BTCUSDT"]["d1"])
        years.append({"label": f"{a} → {b}", "desk": DESK[a], "rows": evaluate(times, args.workers, args.decisorias)})
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"real_{stamp}.json").write_text(json.dumps(years, indent=1, default=str), encoding="utf-8")
    report = render(years, args.decisorias)
    (args.salida / f"real_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
