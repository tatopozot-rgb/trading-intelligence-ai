"""
Larry Williams volatility breakout on the desk's 12 coins, research only.

Rules from docs/inteligencia/BOTS_PUBLICOS.md (2026-10-15), the rest preregistered in
docs/research/breakout/PREREGISTRO.md before any run: daily UTC candles; long when today's high reaches
open + k x yesterday's range, short when the low reaches open - k x range; fill at the trigger (or the open if it
gapped past) with slippage; exit at tomorrow's open; no stop; if both triggers hit, the worse trade counts. At most
3 positions, a third of the day's capital each, 1x; more than 3 triggers: the 3 with the most USDT volume
yesterday. Fees 0.05% and slippage 0.02% per side, real funding for the UTC day. Version A pure, version B with
the desk brakes (regime b on yesterday's BTC close; no entries on FOMC/CPI UTC days). Public data only.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import real_data_validation as rdv
from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.backtesting import two_way_backtest as tw

K, SENSITIVITY = 0.5, (0.25, 0.75)
SLIP, FEE = 0.0002, tw.FEE
MAX_OPEN, CAPITAL = 3, 1000.0
REGIME_SMA = 50
YEARS = (("2024-10-12", "2025-10-12"), ("2025-10-13", "2026-10-13"))
WARM_FROM = "2024-06-01"
# Practice desk net/drawdown: the leader's fixed reference, and re-measured on today's rules (docs/research/saturado/)
DESK = {"2024-10-12": {"líder": 1.67, "re-medida": 1.73}, "2025-10-13": {"líder": -0.21, "re-medida": 0.20}}
OUT_DIR = Path("docs/research/breakout")


@dataclass
class Data:
    days: pd.DatetimeIndex
    open: np.ndarray  # [n, T]
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    usdt_volume: np.ndarray
    funding: np.ndarray  # % paid that UTC day
    names: list[str]


def trade_return(side: int, entry_trigger: float, open_: float, next_open: float, fund_pct: float) -> float:
    """Return on the position's notional: entry at the trigger (or the open if gapped past), exit at next open,
    slippage and fees both sides, the day's funding."""
    entry = max(entry_trigger, open_) if side > 0 else min(entry_trigger, open_)
    fill_in = entry * (1 + SLIP * side)
    fill_out = next_open * (1 - SLIP * side)
    gross = side * (fill_out - fill_in) / fill_in
    return gross - FEE - FEE * fill_out / fill_in - side * fund_pct / 100


def regime_ok(d: Data, t: int) -> bool:
    """Regime b for day t: BTC's close of day t-1 above the mean of its last 50 closes (up to t-1)."""
    if "BTCUSDT" not in d.names or t < REGIME_SMA:
        return True
    c = d.close[d.names.index("BTCUSDT"), t - REGIME_SMA:t]
    return bool(np.isfinite(c).all() and c[-1] > c.mean())


def event_days(days: pd.DatetimeIndex) -> np.ndarray:
    ev = {e.floor("D") for e in rm.macro_events()}
    return np.array([d in ev for d in days])


@dataclass
class Result:
    equity: np.ndarray
    trades: list[dict] = field(default_factory=list)
    both_hit: int = 0
    fees_pct_sum: float = 0.0


def simulate(d: Data, start: int, end: int, k: float = K, brakes: bool = False, capital: float = CAPITAL) -> Result:
    events = event_days(d.days) if brakes else np.zeros(len(d.days), bool)
    equity, eq, trades, both = capital, [], [], 0
    for t in range(start, end):
        if t + 1 >= len(d.days):
            eq.append(equity)
            continue
        longs_only = brakes
        allowed = not (brakes and (events[t] or not regime_ok(d, t)))
        cands = []
        if allowed:
            for i in range(len(d.names)):
                o, h, lo, r = d.open[i, t], d.high[i, t], d.low[i, t], d.high[i, t - 1] - d.low[i, t - 1]
                nxt = d.open[i, t + 1]
                if not np.isfinite([o, h, lo, r, nxt]).all() or r <= 0:
                    continue
                up, dn = o + k * r, o - k * r
                hit_l, hit_s = h >= up, (lo <= dn) and not longs_only
                if not (hit_l or hit_s):
                    continue
                opts = []
                if hit_l:
                    opts.append((trade_return(1, up, o, nxt, d.funding[i, t]), 1))
                if hit_s:
                    opts.append((trade_return(-1, dn, o, nxt, d.funding[i, t]), -1))
                if len(opts) == 2:
                    both += 1
                ret, side = min(opts)
                cands.append((d.usdt_volume[i, t - 1], i, side, ret))
        cands.sort(key=lambda x: -x[0] if np.isfinite(x[0]) else 0)
        size = equity / MAX_OPEN
        pnl = 0.0
        for _, i, side, ret in cands[:MAX_OPEN]:
            pnl += size * ret
            trades.append({"day": str(d.days[t].date()), "symbol": d.names[i], "side": side, "ret_pct": ret * 100})
        equity += pnl
        eq.append(equity)
    return Result(np.array(eq), trades, both)


def stats(r: Result, capital: float = CAPITAL) -> dict:
    e = np.r_[capital, r.equity]
    peak = np.maximum.accumulate(e)
    dd = float(((peak - e) / peak).max() * 100)
    net = (e[-1] / capital - 1) * 100
    rets = [x["ret_pct"] for x in r.trades]
    return {"net_pct": round(net, 2), "max_dd_pct": round(dd, 2), "net_dd": round(net / dd, 2) if dd > 0 else None,
            "trades": len(rets), "win_rate": round(float(np.mean([x > 0 for x in rets]) * 100), 1) if rets else 0.0,
            "avg_trade_pct": round(float(np.mean(rets)), 3) if rets else 0.0,
            "longs": sum(1 for x in r.trades if x["side"] > 0), "shorts": sum(1 for x in r.trades if x["side"] < 0),
            "both_hit": r.both_hit}


def quarter_nets(r: Result, capital: float = CAPITAL) -> list[float]:
    e = np.r_[capital, r.equity]
    T = len(r.equity)
    out, a = [], 0
    for q in range(4):
        b = min(T, a + (T - a) // (4 - q))
        out.append(round((e[b] / e[a] - 1) * 100, 2))
        a = b
    return out


def year(d: Data, a: str, b: str) -> dict:
    start = int(d.days.searchsorted(pd.Timestamp(a, tz="UTC")))
    end = int(d.days.searchsorted(pd.Timestamp(b, tz="UTC")))
    rows: dict[str, Any] = {}
    for brakes, label in ((False, "A pura"), (True, "B con frenos")):
        for k in (K, *SENSITIVITY):
            r = simulate(d, start, end, k, brakes)
            rows[f"{label}, k={k:g}"] = {**stats(r), "quarters": quarter_nets(r), "k": k, "version": label}
    btc = d.names.index("BTCUSDT") if "BTCUSDT" in d.names else None
    bh = round((d.close[btc, end - 1] / d.close[btc, start - 1] - 1) * 100, 2) if btc is not None else None
    ref = DESK.get(a, {})
    judge = {v: {name: (rows[f"{v}, k={K:g}"]["net_dd"] or -99) > val for name, val in ref.items()}
             for v in ("A pura", "B con frenos")}
    return {"from": a, "to": b, "rows": rows, "btc_pct": bh, "desk": ref, "judge": judge}


def verdict(years: list[dict]) -> list[str]:
    lines = []
    for v in ("A pura", "B con frenos"):
        ok_leader = all(y["judge"][v].get("líder", False) for y in years)
        ok_now = all(y["judge"][v].get("re-medida", False) for y in years)
        detail = "; ".join(f"{y['from']} → {y['to']}: {y['rows'][f'{v}, k={K:g}']['net_dd']} contra "
                           f"{y['desk'].get('líder')} (re-medida {y['desk'].get('re-medida')})" for y in years)
        word = "pasa" if ok_leader else "no pasa"
        extra = "" if ok_leader == ok_now else (" (contra la mesa re-medida: " + ("pasa" if ok_now else "no pasa") + ")")
        lines.append(f"- **{v}, k = 0,5: {word}**{extra} — neto/caída {detail}.")
    for y in years:
        for v in ("A pura", "B con frenos"):
            n = y["rows"][f"{v}, k={K:g}"]["trades"]
            if n < 100:
                lines.append(f"- {v}, {y['from']} → {y['to']}: {n} operaciones, muestra corta.")
    return lines


def render(years: list[dict], meta: dict) -> str:
    L = ["# Ruptura de volatilidad de Larry Williams en las 12 monedas de la mesa", "",
         "Reglas del líder (`docs/inteligencia/BOTS_PUBLICOS.md`) y preregistro (`docs/research/breakout/PREREGISTRO.md`), "
         "escritos antes de correr. Velas diarias de Spot, salida en la apertura siguiente, sin stop, 3 posiciones de un "
         "tercio del capital, 1x. Comisión 0,05% y deslizamiento 0,02% por lado, financiación real del día. k = 0,5 decide; "
         "0,25 y 0,75 solo muestran la sensibilidad. Monedas: " + ", ".join(meta["simbolos"]) + ".", "",
         "## Veredicto", "", *verdict(years)]
    for y in years:
        L += ["", f"## {y['from']} → {y['to']} (BTC comprar y mantener {y['btc_pct']}%; mesa de práctica neto/caída "
              f"{y['desk'].get('líder')}, re-medida {y['desk'].get('re-medida')})", "",
              "| Versión | Neto % | Máx. caída | Neto/caída | Ops | Largos | Cortos | Acierto | Media por op. | "
              "Ambos disparos | Trimestres (neto %) |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for name, r in y["rows"].items():
            L.append(f"| {name} | {r['net_pct']:+.1f}% | {r['max_dd_pct']}% | {r['net_dd']} | {r['trades']} | {r['longs']} | "
                     f"{r['shorts']} | {r['win_rate']}% | {r['avg_trade_pct']:+.3f}% | {r['both_hit']} | "
                     + " / ".join(f"{q:+.1f}" for q in r["quarters"]) + " |")
    L += ["", "Advertencias: Spot como aproximación del perpetuo; la vela diaria no dice qué se tocó primero (por eso, si "
          "se tocan los dos disparos, cuenta la peor); el volumen en USDT es volumen × cierre; la mesa de práctica se cita "
          "de `docs/research/mesa/` y `docs/research/saturado/`. Un resultado pasado no promete uno futuro."]
    return "\n".join(L) + "\n"


def _load(args: tuple) -> tuple[str, Optional[pd.DataFrame], pd.Series, str]:
    sym, start_iso, end_iso = args
    start, end = datetime.fromisoformat(start_iso), datetime.fromisoformat(end_iso)
    rdv.INTERVAL_MS.setdefault("1d", 86_400_000)
    try:
        k = rdv.fetch_klines(sym, "1d", start, end)
    except Exception as error:  # noqa: BLE001
        return sym, None, pd.Series(dtype=float), f"sin datos ({type(error).__name__})"
    f = tw.fetch_funding(sym, start, end)
    daily = f.groupby(pd.DatetimeIndex(f.index).floor("D")).sum() if not f.empty else f
    return sym, k, daily, f"{len(k)} días, financiación {len(f)}"


def build(loaded: list[tuple[str, Optional[pd.DataFrame], pd.Series, str]]) -> Data:
    frames = {s: k for s, k, _, _ in loaded if k is not None}
    days = pd.DatetimeIndex(sorted(set().union(*[set(pd.DatetimeIndex(k.index)) for k in frames.values()])))
    names = sorted(frames)
    shape = (len(names), len(days))
    arr = {c: np.full(shape, np.nan) for c in ("open", "high", "low", "close", "volume")}
    fu = np.full(shape, tw.FUNDING_PER_8H * 100 * 3)
    fund = {s: f for s, _, f, _ in loaded}
    for i, s in enumerate(names):
        k = frames[s].reindex(days)
        for c in arr:
            arr[c][i] = k[c].values
        f = fund.get(s)
        if f is not None and not f.empty:
            fu[i] = f.reindex(days).fillna(tw.FUNDING_PER_8H * 100 * 3).values
    return Data(days, arr["open"], arr["high"], arr["low"], arr["close"], arr["volume"] * arr["close"], fu, names)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Ruptura de volatilidad de Larry Williams (investigación)")
    parser.add_argument("--simbolos", nargs="+", default=list(tw.SYMBOLS))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    start = datetime.fromisoformat(WARM_FROM).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(YEARS[-1][1]).replace(tzinfo=timezone.utc) + timedelta(days=2)
    with Pool(max(1, args.workers)) as pool:
        loaded = pool.map(_load, [(s, start.isoformat(), end.isoformat()) for s in args.simbolos])
    for s, _, _, note in loaded:
        print(f"{s}: {note}")
    d = build(loaded)
    years = [year(d, a, b) for a, b in YEARS]
    meta = {"simbolos": d.names}
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"breakout_{stamp}.json").write_text(json.dumps({"meta": meta, "years": years}, indent=1, default=str),
                                                        encoding="utf-8")
    report = render(years, meta)
    (args.salida / f"breakout_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
