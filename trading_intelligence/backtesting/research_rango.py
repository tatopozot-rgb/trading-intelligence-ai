"""
Range mean reversion (Bollinger bands filtered by low ADX) on the desk's 12 coins, daily and 4h, research only.

Preregistered in docs/research/rango/PREREGISTRO.md before any run: a candle that closes outside its 20/2 Bollinger
band while ADX 14 < 20 opens a position against the move at the next open (below the lower band: long; above the
upper: short). Exit at the next open after a close back at or past the 20 mean, or at a 1.5 x ATR 14 stop checked on
every open candle (a gap past the stop fills at the open), or at the open after 10 candles. Stop and mean on the same
candle: the stop counts. At most 3 positions, one per coin, a third of realized capital each, 1x; more signals than
slots: the most USDT volume on the signal candle. Fees 0.05% and slippage 0.02% per side, real funding for every
candle held. Version A pure, version B with the desk brakes (regime b on the last complete daily BTC close; no new
entries on FOMC/CPI UTC days). ADX < 25 and 2.5 deviations are information only. Public data only.
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

from trading_intelligence.analysis import indicators as ind
from trading_intelligence.backtesting import real_data_validation as rdv
from trading_intelligence.backtesting import research_breakout as rb
from trading_intelligence.backtesting import two_way_backtest as tw

BB_PERIOD, ADX_PERIOD, ATR_PERIOD = 20, 14, 14
STOP_ATR, MAX_BARS = 1.5, 10
SLIP, FEE = rb.SLIP, rb.FEE
MAX_OPEN, CAPITAL = 3, 1000.0
REGIME_SMA = 50
# name -> (ADX threshold, band deviations); "base" decides, the others only show sensitivity
VARIANTS = {"base": (20.0, 2.0), "ADX<25": (25.0, 2.0), "2,5 desv.": (20.0, 2.5)}
FRAMES = {"1d": "diario", "4h": "4 h"}
YEARS, WARM_FROM, DESK = rb.YEARS, rb.WARM_FROM, rb.DESK
OUT_DIR = Path("docs/research/rango")


@dataclass
class Data:
    bars: pd.DatetimeIndex
    open: np.ndarray  # [n, T]
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    usdt_volume: np.ndarray
    funding: np.ndarray  # % whose funding time falls inside the candle
    names: list[str]


@dataclass
class Signals:
    mid: np.ndarray
    upper: np.ndarray
    lower: np.ndarray
    adx: np.ndarray
    atr: np.ndarray


def signals(d: Data, num_std: float) -> Signals:
    out = {k: np.full(d.close.shape, np.nan) for k in ("mid", "upper", "lower", "adx", "atr")}
    for i in range(len(d.names)):
        h, lo, c = (pd.Series(x[i]) for x in (d.high, d.low, d.close))
        out["mid"][i], out["upper"][i], out["lower"][i] = (s.values for s in ind.bollinger_bands(c, BB_PERIOD, num_std))
        out["adx"][i] = ind.adx(h, lo, c, ADX_PERIOD).values
        out["atr"][i] = ind.atr(h, lo, c, ATR_PERIOD).values
    return Signals(**out)


def trade_return(side: int, fill_in: float, fill_out: float, fund_pct: float) -> float:
    """Return on the notional from fills that already carry slippage: fees both sides, funding while held."""
    return side * (fill_out - fill_in) / fill_in - FEE - FEE * fill_out / fill_in - side * fund_pct / 100


def regime_by_bar(d: Data) -> np.ndarray:
    """Regime b for an entry at each bar's open: the last complete UTC day's BTC close above its 50-day mean."""
    if "BTCUSDT" not in d.names:
        return np.ones(len(d.bars), bool)
    btc = pd.Series(d.close[d.names.index("BTCUSDT")], index=d.bars).dropna()
    daily = btc.groupby(btc.index.floor("D")).last()
    ok = (daily > daily.rolling(REGIME_SMA, min_periods=REGIME_SMA).mean()).fillna(False)
    prev_day = d.bars.floor("D") - pd.Timedelta(days=1)
    return np.asarray(ok.reindex(prev_day).fillna(False).values, dtype=bool)


def event_bars(d: Data) -> np.ndarray:
    """True for bars whose UTC day has an FOMC decision or a CPI release."""
    return rb.event_days(d.bars.floor("D"))


@dataclass
class Result:
    equity: np.ndarray
    trades: list[dict] = field(default_factory=list)


def simulate(d: Data, s: Signals, start: int, end: int, adx_max: float, brakes: bool = False,
             capital: float = CAPITAL) -> Result:
    regime = regime_by_bar(d) if brakes else np.ones(len(d.bars), bool)
    events = event_bars(d) if brakes else np.zeros(len(d.bars), bool)
    cash, eq, trades = capital, [], []
    pos: dict[int, dict] = {}
    exits: set[int] = set()
    entries: list[tuple[float, int, int]] = []

    def close_pos(i: int, t: int, px: float, why: str) -> None:
        nonlocal cash
        p = pos.pop(i)
        ret = trade_return(p["side"], p["fill_in"], px * (1 - SLIP * p["side"]), p["fund"])
        cash += p["size"] * ret
        trades.append({"symbol": d.names[i], "side": p["side"], "entry": str(d.bars[p["t"]]), "exit": str(d.bars[t]),
                       "bars": t - p["t"], "why": why, "ret_pct": ret * 100})

    for t in range(start, end):
        for i in sorted(exits):
            if i in pos and np.isfinite(d.open[i, t]):
                close_pos(i, t, d.open[i, t], pos[i]["why"])
        exits = {i for i in exits if i in pos}
        size = cash / MAX_OPEN
        for _, i, side in entries:
            if len(pos) >= MAX_OPEN or i in pos or not np.isfinite(d.open[i, t]):
                continue
            o = d.open[i, t]
            pos[i] = {"side": side, "fill_in": o * (1 + SLIP * side), "size": size, "t": t, "fund": 0.0,
                      "stop": o - side * STOP_ATR * s.atr[i, t - 1], "why": ""}
        entries = []
        for i in list(pos):
            p = pos[i]
            o, h, lo = d.open[i, t], d.high[i, t], d.low[i, t]
            if not np.isfinite([o, h, lo]).all():
                continue
            p["fund"] += d.funding[i, t]
            side, stop = p["side"], p["stop"]
            if side * (o - stop) <= 0:
                close_pos(i, t, o, "stop")
            elif (side > 0 and lo <= stop) or (side < 0 and h >= stop):
                close_pos(i, t, stop, "stop")
        mark = cash
        for i, p in pos.items():
            c = d.close[i, t]
            if not np.isfinite(c):
                continue
            side = p["side"]
            mark += p["size"] * (side * (c - p["fill_in"]) / p["fill_in"] - FEE - side * p["fund"] / 100)
            if i not in exits:
                if side * (c - s.mid[i, t]) >= 0:
                    exits.add(i)
                    p["why"] = "media"
                elif t - p["t"] + 1 >= MAX_BARS:
                    exits.add(i)
                    p["why"] = "tiempo"
        eq.append(mark)
        if t + 1 >= min(end, len(d.bars)) or (brakes and events[t + 1]):
            continue
        longs_ok = not brakes or regime[t + 1]
        for i in range(len(d.names)):
            if i in pos:
                continue
            c, a = d.close[i, t], s.adx[i, t]
            if not np.isfinite([c, a, s.lower[i, t], s.upper[i, t], s.atr[i, t]]).all() or a >= adx_max:
                continue
            if c < s.lower[i, t] and longs_ok:
                entries.append((d.usdt_volume[i, t], i, 1))
            elif c > s.upper[i, t] and not brakes:
                entries.append((d.usdt_volume[i, t], i, -1))
        entries.sort(key=lambda x: -x[0] if np.isfinite(x[0]) else 0)
    last = end if end < len(d.bars) else end - 1
    for i in list(pos):
        px = d.open[i, last] if last == end and np.isfinite(d.open[i, last]) else d.close[i, end - 1]
        close_pos(i, last, px, "fin")
    if eq:
        eq[-1] = cash
    return Result(np.array(eq), trades)


def stats(r: Result, capital: float = CAPITAL) -> dict:
    e = np.r_[capital, r.equity]
    peak = np.maximum.accumulate(e)
    dd = float(((peak - e) / peak).max() * 100)
    net = (e[-1] / capital - 1) * 100
    rets = [x["ret_pct"] for x in r.trades]
    why = {w: sum(1 for x in r.trades if x["why"] == w) for w in ("media", "stop", "tiempo", "fin")}
    return {"net_pct": round(net, 2), "max_dd_pct": round(dd, 2), "net_dd": round(net / dd, 2) if dd > 0 else None,
            "trades": len(rets), "win_rate": round(float(np.mean([x > 0 for x in rets]) * 100), 1) if rets else 0.0,
            "avg_trade_pct": round(float(np.mean(rets)), 3) if rets else 0.0,
            "avg_bars": round(float(np.mean([x["bars"] for x in r.trades])), 1) if rets else 0.0,
            "longs": sum(1 for x in r.trades if x["side"] > 0), "shorts": sum(1 for x in r.trades if x["side"] < 0),
            "exits": why}


def quarter_nets(r: Result, capital: float = CAPITAL) -> list[float]:
    e = np.r_[capital, r.equity]
    T = len(r.equity)
    out, a = [], 0
    for q in range(4):
        b = min(T, a + (T - a) // (4 - q))
        out.append(round((e[b] / e[a] - 1) * 100, 2))
        a = b
    return out


def year(d: Data, sigs: dict[float, Signals], a: str, b: str) -> dict:
    start = int(d.bars.searchsorted(pd.Timestamp(a, tz="UTC")))
    end = int(d.bars.searchsorted(pd.Timestamp(b, tz="UTC")))
    rows: dict[str, Any] = {}
    for brakes, label in ((False, "A pura"), (True, "B con frenos")):
        for name, (adx_max, std) in VARIANTS.items():
            r = simulate(d, sigs[std], start, end, adx_max, brakes)
            rows[f"{label}, {name}"] = {**stats(r), "quarters": quarter_nets(r), "version": label}
    btc = d.names.index("BTCUSDT") if "BTCUSDT" in d.names else None
    bh = round((d.close[btc, end - 1] / d.close[btc, start - 1] - 1) * 100, 2) if btc is not None else None
    ref = DESK.get(a, {})
    judge = {v: {k: (rows[f"{v}, base"]["net_dd"] or -99) > val for k, val in ref.items()}
             for v in ("A pura", "B con frenos")}
    return {"from": a, "to": b, "rows": rows, "btc_pct": bh, "desk": ref, "judge": judge}


def verdict(frames: dict[str, list[dict]]) -> list[str]:
    lines = []
    for f, years in frames.items():
        for v in ("A pura", "B con frenos"):
            ok_leader = all(y["judge"][v].get("líder", False) for y in years)
            ok_now = all(y["judge"][v].get("re-medida", False) for y in years)
            detail = "; ".join(f"{y['from']} → {y['to']}: {y['rows'][f'{v}, base']['net_dd']} contra "
                               f"{y['desk'].get('líder')} (re-medida {y['desk'].get('re-medida')})" for y in years)
            word = "pasa" if ok_leader else "no pasa"
            extra = "" if ok_leader == ok_now else (" (contra la mesa re-medida: " + ("pasa" if ok_now else "no pasa") + ")")
            lines.append(f"- **{FRAMES[f]}, {v}: {word}**{extra} — neto/caída {detail}.")
            for y in years:
                n = y["rows"][f"{v}, base"]["trades"]
                if n < 100:
                    lines.append(f"  - {y['from']} → {y['to']}: {n} operaciones, muestra corta.")
    return lines


def render(frames: dict[str, list[dict]], meta: dict) -> str:
    L = ["# Rebote a la media en mercado lateral (Bollinger + ADX), diario y 4 h", "",
         "Preregistrado en `docs/research/rango/PREREGISTRO.md` antes de correr. Cierre fuera de la banda de Bollinger "
         "20/2 con ADX 14 < 20: entrada en contra en la apertura siguiente; salida al volver a la media, stop a 1,5 ATR "
         "o a las 10 velas. 3 posiciones de un tercio del capital, 1x. Comisión 0,05% y deslizamiento 0,02% por lado, "
         "financiación real. La regla base decide; ADX < 25 y 2,5 desviaciones solo muestran la sensibilidad. "
         "Monedas: " + ", ".join(meta["simbolos"]) + ".", "", "## Veredicto", "", *verdict(frames)]
    for f, years in frames.items():
        for y in years:
            L += ["", f"## {FRAMES[f]} · {y['from']} → {y['to']} (BTC comprar y mantener {y['btc_pct']}%; mesa de "
                  f"práctica neto/caída {y['desk'].get('líder')}, re-medida {y['desk'].get('re-medida')})", "",
                  "| Versión | Neto % | Máx. caída | Neto/caída | Ops | Largos | Cortos | Acierto | Media por op. | "
                  "Velas | Salidas media/stop/tiempo/fin | Trimestres (neto %) |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|"]
            for name, r in y["rows"].items():
                ex = r["exits"]
                L.append(f"| {name} | {r['net_pct']:+.1f}% | {r['max_dd_pct']}% | {r['net_dd']} | {r['trades']} | "
                         f"{r['longs']} | {r['shorts']} | {r['win_rate']}% | {r['avg_trade_pct']:+.3f}% | {r['avg_bars']} | "
                         f"{ex['media']}/{ex['stop']}/{ex['tiempo']}/{ex['fin']} | "
                         + " / ".join(f"{q:+.1f}" for q in r["quarters"]) + " |")
    L += ["", "Advertencias: Spot como aproximación del perpetuo; la vela no dice qué se tocó primero (por eso stop y "
          "media en la misma vela cuentan como stop); el volumen en USDT es volumen × cierre; la caída se mide sobre el "
          "capital marcado a mercado al cierre de cada vela; la mesa de práctica se cita de `docs/research/mesa/` y "
          "`docs/research/saturado/`. Un resultado pasado no promete uno futuro."]
    return "\n".join(L) + "\n"


def _load(args: tuple) -> tuple[str, dict[str, Optional[pd.DataFrame]], pd.Series, str]:
    sym, frames, start_iso, end_iso = args
    start, end = datetime.fromisoformat(start_iso), datetime.fromisoformat(end_iso)
    rdv.INTERVAL_MS.setdefault("1d", 86_400_000)
    out: dict[str, Optional[pd.DataFrame]] = {}
    notes = []
    for f in frames:
        try:
            k = rdv.fetch_klines(sym, f, start, end)
            out[f] = k
            notes.append(f"{f} {len(k)} velas")
        except Exception as error:  # noqa: BLE001
            out[f] = None
            notes.append(f"{f} sin datos ({type(error).__name__})")
    fund = tw.fetch_funding(sym, start, end)
    return sym, out, fund, ", ".join(notes) + f", financiación {len(fund)}"


def build(loaded: list[tuple[str, Optional[pd.DataFrame], pd.Series]], interval: str) -> Data:
    frames = {s: k for s, k, _ in loaded if k is not None}
    bars = pd.DatetimeIndex(sorted(set().union(*[set(pd.DatetimeIndex(k.index)) for k in frames.values()])))
    names = sorted(frames)
    shape = (len(names), len(bars))
    arr = {c: np.full(shape, np.nan) for c in ("open", "high", "low", "close", "volume")}
    per_bar = tw.FUNDING_PER_8H * 100 * (pd.Timedelta(interval) / pd.Timedelta(hours=8))
    fu = np.full(shape, per_bar)
    fund = {s: f for s, _, f in loaded}
    step = pd.Timedelta(interval)
    for i, s in enumerate(names):
        k = frames[s].reindex(bars)
        for c in arr:
            arr[c][i] = k[c].values
        f = fund.get(s)
        if f is not None and not f.empty:
            idx = pd.DatetimeIndex(f.index)
            bucket = f.groupby(idx.floor(step)).sum().reindex(bars).fillna(0.0)
            covered = (bars >= idx.min().floor(step)) & (bars < idx.max() + pd.Timedelta(hours=8))
            fu[i] = np.where(covered, bucket.values, per_bar)
    return Data(bars, arr["open"], arr["high"], arr["low"], arr["close"], arr["volume"] * arr["close"], fu, names)


def run_frame(d: Data) -> list[dict]:
    sigs = {std: signals(d, std) for std in {v[1] for v in VARIANTS.values()}}
    return [year(d, sigs, a, b) for a, b in YEARS]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Rebote a la media en mercado lateral (investigación)")
    parser.add_argument("--simbolos", nargs="+", default=list(tw.SYMBOLS))
    parser.add_argument("--marcos", nargs="+", default=list(FRAMES), choices=list(FRAMES))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    start = datetime.fromisoformat(WARM_FROM).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(YEARS[-1][1]).replace(tzinfo=timezone.utc) + timedelta(days=2)
    with Pool(max(1, args.workers)) as pool:
        loaded = pool.map(_load, [(s, args.marcos, start.isoformat(), end.isoformat()) for s in args.simbolos])
    for s, _, _, note in loaded:
        print(f"{s}: {note}")
    results = {f: run_frame(build([(s, k[f], fund) for s, k, fund, _ in loaded], f)) for f in args.marcos}
    meta = {"simbolos": sorted(s for s, k, _, _ in loaded if any(v is not None for v in k.values()))}
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"rango_{stamp}.json").write_text(json.dumps({"meta": meta, "frames": results}, indent=1, default=str),
                                                     encoding="utf-8")
    report = render(results, meta)
    (args.salida / f"rango_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
