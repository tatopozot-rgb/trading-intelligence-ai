"""
Funding carry, market-neutral (leader, 2026-10-13), research only (docs/research/PROTOCOLO.md).

Hold spot long + perpetual short of the same coin, the same quantity, while its funding is persistently
positive: the short receives the funding and the price moves of the two legs cancel (up to the basis).
This is a different entry from the desk: no bet on direction.

Each position takes 1/K of equity: half buys spot, half is the perp margin for a short of the same quantity
(1x, no leverage overall; capital efficiency 50%). Decisions every 8 h (00, 08, 16 UTC) on the trailing
mean of the last L funding payments, normalised to 8 h: enter above `enter`, leave below `exit`; the K
highest carry when there are more. Costs per leg and side: spot 0.10% (taker, no BNB discount), perp 0.05%,
plus 0.02% slippage each. When the short's loss eats half of its margin both legs are closed and reopened
at the current price ("rebalanceo", paying the round trip). Funding is paid on the position held at the
funding time; prices are hourly closes (spot from data-api.binance.vision, perp and funding from the
public futures archive data.binance.vision). Walk-forward: choose (L, enter) on 90 days, test 30, roll 30.
Public data only: no account, no key, no orders. Nothing here touches config/ or live/.
"""
from __future__ import annotations

import argparse
import csv
import io
import itertools
import json
import math
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import real_data_validation as rdv
from trading_intelligence.backtesting import two_way_backtest as tw

CAPITAL = 1000.0
SPOT_COST = 0.0010 + 0.0002  # fee + slippage, per side
PERP_COST = tw.FEE + 0.0002
REBALANCE_AT = 0.5  # short leg loss / its margin
HOUR = 3_600_000_000_000
FIT_HOURS, TEST_HOURS = 90 * 24, 30 * 24
OUT_DIR = Path("docs/research/carry")
DEFAULT_START = "2020-01-01"


@dataclass(frozen=True)
class Rule:
    lookback: int  # funding payments in the trailing mean
    enter: float  # % per 8 h
    exit: float = 0.0
    k: int = 4
    only: Optional[str] = None  # restrict to one coin

    def label(self) -> str:
        if self.enter == -math.inf:
            return f"siempre dentro ({self.only or 'todas las monedas'})"
        return f"media de {self.lookback} pagos > {self.enter:g}%/8h, salir < {self.exit:g}%, {self.k} monedas"


GRID = [Rule(lb, e) for lb, e in itertools.product((3, 9, 21), (0.005, 0.01, 0.02))]
DEFAULT = Rule(21, 0.01)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def _zip_csv(url: str) -> list[list[str]]:
    with urllib.request.urlopen(url, timeout=30) as resp:  # public archive: no key, no account
        blob = resp.read(50_000_001)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        return list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode("utf-8"))))


def parse_klines(rows: list[list[str]]) -> pd.Series:
    """Close per hour, indexed by the bar's CLOSE time (open + 1 h). Header rows skipped; ms or µs times."""
    out: dict[pd.Timestamp, float] = {}
    for r in rows:
        if not r or not r[0].strip().isdigit():
            continue
        t = int(r[0])
        t = t // 1000 if t > 10**14 else t  # microseconds in newer archives
        out[pd.Timestamp(t, unit="ms", tz="UTC") + pd.Timedelta(hours=1)] = float(r[4])
    return pd.Series(out, dtype=float).sort_index()


def fetch_perp_1h(symbol: str, start: datetime, end: datetime) -> pd.Series:
    """Perp hourly closes from the futures archive: monthly files, then daily files for the current month."""
    parts = []
    month = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while month <= end:
        url = f"{tw.VISION}/monthly/klines/{symbol}/1h/{symbol}-1h-{month:%Y-%m}.zip"
        try:
            parts.append(parse_klines(_zip_csv(url)))
        except Exception:  # noqa: BLE001 - not listed yet, or the month is not published: try days
            day = month
            while day < min(end, (month + timedelta(days=32)).replace(day=1)):
                try:
                    parts.append(parse_klines(_zip_csv(
                        f"{tw.VISION}/daily/klines/{symbol}/1h/{symbol}-1h-{day:%Y-%m-%d}.zip")))
                except Exception:  # noqa: BLE001
                    pass
                day += timedelta(days=1)
        month = (month + timedelta(days=32)).replace(day=1)
    if not parts:
        return pd.Series(dtype=float)
    s = pd.concat(parts)
    return s[~s.index.duplicated()].sort_index()


def fetch_spot_1h(symbol: str, start: datetime, end: datetime) -> pd.Series:
    rdv.INTERVAL_MS.setdefault("1h", 3_600_000)
    k = rdv.fetch_klines(symbol, "1h", start, end)
    return pd.Series(k["close"].values, index=pd.DatetimeIndex(k.index) + pd.Timedelta(hours=1), dtype=float)


@dataclass
class Panel:
    names: list[str]
    times: np.ndarray  # int64 ns, hourly close times
    spot: np.ndarray  # [n, T], forward-filled after listing, NaN before
    perp: np.ndarray
    rate: np.ndarray  # [n, T] funding % paid at this hour (0 if none)
    norm: dict[int, np.ndarray] = field(default_factory=dict)  # lookback -> [n, T] trailing mean, %/8h
    btc: Optional[np.ndarray] = None  # BTC spot, for buy-and-hold


def build_panel(raw: dict[str, tuple[pd.Series, pd.Series, pd.Series]], start: datetime, end: datetime,
                lookbacks: tuple[int, ...]) -> Panel:
    grid = pd.date_range(pd.Timestamp(start).ceil("h"), pd.Timestamp(end).floor("h"), freq="h")
    times = pd.DatetimeIndex(grid).as_unit("ns").asi8
    names = sorted(raw)
    n, T = len(names), len(times)
    spot, perp, rate = np.full((n, T), np.nan), np.full((n, T), np.nan), np.zeros((n, T))
    norm = {lb: np.full((n, T), np.nan) for lb in lookbacks}
    for i, name in enumerate(names):
        s, p, f = raw[name]
        if not s.empty:
            spot[i] = s.reindex(grid).ffill().values
            spot[i, grid < s.index[0]] = np.nan
        if not p.empty:
            perp[i] = p.reindex(grid).ffill().values
            perp[i, grid < p.index[0]] = np.nan
        if f.empty:
            continue
        et = pd.DatetimeIndex(f.index).round("h")
        hours = np.r_[8.0, np.diff(et.as_unit("ns").asi8) / HOUR]
        per8 = f.values * 8 / np.clip(hours, 1, 8)
        idx = np.searchsorted(times, et.as_unit("ns").asi8)
        ok = idx < T
        np.add.at(rate[i], idx[ok], f.values[ok])
        for lb in lookbacks:
            mean = pd.Series(per8).rolling(lb).mean().values
            j = np.searchsorted(et.as_unit("ns").asi8, times, side="right") - 1
            norm[lb][i] = np.where(j >= 0, mean[np.clip(j, 0, None)], np.nan)
            last = et.as_unit("ns").asi8[-1]
            norm[lb][i, times > last + 24 * HOUR] = np.nan  # no funding data: no signal
    btc = spot[names.index("BTCUSDT")] if "BTCUSDT" in names else None
    return Panel(names, times, spot, perp, rate, norm, btc)


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

@dataclass
class Run:
    curve: np.ndarray
    funding: np.ndarray  # per hour, USDT
    costs: np.ndarray
    basis: np.ndarray  # price legs together
    invested: np.ndarray  # positions held
    trades: list[dict] = field(default_factory=list)
    rebalances: int = 0


def simulate(p: Panel, rule: Rule, capital: float = CAPITAL) -> Run:
    n, T = p.spot.shape
    always = rule.enter == -math.inf
    allowed = [i for i in range(n) if rule.only is None or p.names[i] == rule.only]
    k = len(allowed) if always else rule.k
    sig = p.norm.get(rule.lookback) if not always else None
    has_rate = p.rate != 0
    first_rate = np.where(has_rate.any(axis=1), has_rate.argmax(axis=1), T)
    equity = capital
    curve, fund, cost, basis, inv = np.zeros(T), np.zeros(T), np.zeros(T), np.zeros(T), np.zeros(T, dtype=np.int16)
    pos: dict[int, dict] = {}
    run = Run(curve, fund, cost, basis, inv)

    def close(i: int, t: int, why: str) -> None:
        nonlocal equity
        q = pos[i]
        c = q["q"] * (p.spot[i, t] * SPOT_COST + p.perp[i, t] * PERP_COST)
        equity -= c
        cost[t] += c
        q["pnl"] -= c
        run.trades.append({"symbol": p.names[i], "t0": int(p.times[q["t0"]]), "t1": int(p.times[t]), "why": why,
                           "pnl": q["pnl"], "funding": q["fund"], "alloc": q["alloc"]})
        del pos[i]

    def open_(i: int, t: int, alloc: float) -> None:
        nonlocal equity
        q = alloc / 2 / p.spot[i, t]
        c = q * (p.spot[i, t] * SPOT_COST + p.perp[i, t] * PERP_COST)
        equity -= c
        cost[t] += c
        pos[i] = {"q": q, "f0": p.perp[i, t], "alloc": alloc, "t0": t, "pnl": -c, "fund": 0.0}

    for t in range(T):
        if t > 0:
            for i, q in list(pos.items()):
                ds = p.spot[i, t] - p.spot[i, t - 1]
                dp = p.perp[i, t] - p.perp[i, t - 1]
                pnl_b = q["q"] * (ds - dp)
                pnl_f = q["q"] * p.perp[i, t] * p.rate[i, t] / 100
                equity += pnl_b + pnl_f
                basis[t] += pnl_b
                fund[t] += pnl_f
                q["pnl"] += pnl_b + pnl_f
                q["fund"] += pnl_f
                if q["q"] * (p.perp[i, t] - q["f0"]) > REBALANCE_AT * q["alloc"] / 2:
                    alloc = q["alloc"]
                    close(i, t, "rebalanceo")
                    open_(i, t, alloc)
                    run.rebalances += 1
        hour = (p.times[t] // HOUR) % 24
        if hour % 8 == 0:
            live = [i for i in allowed if not (math.isnan(p.spot[i, t]) or math.isnan(p.perp[i, t]))]
            if always:
                for i in live:
                    if i not in pos and first_rate[i] <= t:
                        open_(i, t, equity / k)
            else:
                assert sig is not None
                for i in list(pos):
                    m = sig[i, t]
                    if math.isnan(m) or m < rule.exit or i not in live:
                        close(i, t, "financiación baja" if not math.isnan(m) else "sin dato")
                cands = sorted((i for i in live if i not in pos and not math.isnan(sig[i, t]) and sig[i, t] > rule.enter),
                               key=lambda i: -sig[i, t])
                for i in cands[: max(0, k - len(pos))]:
                    open_(i, t, equity / k)
        curve[t] = equity
        inv[t] = len(pos)
    for i in list(pos):
        close(i, T - 1, "fin")
    curve[T - 1] = equity
    return run


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def window(run: Run, a: int, b: int, capital: float = CAPITAL) -> dict:
    """Stats for hours [a, b): returns relative to the equity at a (or the capital at 0)."""
    start = run.curve[a - 1] if a > 0 else capital
    seg = np.r_[start, run.curve[a:b]]
    peak = np.maximum.accumulate(seg)
    dd = float(((peak - seg) / peak).max() * 100)
    net = (seg[-1] / start - 1) * 100
    hours = max(1, b - a)
    ann = ((seg[-1] / start) ** (8760 / hours) - 1) * 100 if seg[-1] > 0 else -100.0
    daily = seg[::24]
    rets = np.diff(daily) / daily[:-1] if len(daily) > 1 else np.array([0.0])
    weekly = seg[::168]
    wk = np.diff(weekly) / weekly[:-1] if len(weekly) > 1 else np.array([0.0])
    return {"net_pct": round(net, 2), "annual_pct": round(ann, 2), "max_dd_pct": round(dd, 2),
            "net_dd": round(net / dd, 2) if dd > 0 else None,
            "funding_pct": round(float(run.funding[a:b].sum()) / start * 100, 2),
            "costs_pct": round(float(run.costs[a:b].sum()) / start * 100, 2),
            "basis_pct": round(float(run.basis[a:b].sum()) / start * 100, 2),
            "invested_pct": round(float((run.invested[a:b] > 0).mean() * 100), 1),
            "worst_day_pct": round(float(rets.min() * 100), 2), "worst_week_pct": round(float(wk.min() * 100), 2)}


def quarters(times: np.ndarray) -> list[tuple[str, int, int]]:
    q = pd.DatetimeIndex(pd.to_datetime(times, utc=True)).tz_localize(None).to_period("Q")
    out, a = [], 0
    for b in range(1, len(times) + 1):
        if b == len(times) or q[b] != q[a]:
            out.append((str(q[a]), a, b))
            a = b
    return out


def walk_forward(p: Panel, runs: dict[Rule, Run]) -> dict:
    T = len(p.times)
    chosen, level, curve, stats = [], 1.0, [1.0], []
    for a in range(FIT_HOURS, T, TEST_HOURS):
        b = min(T, a + TEST_HOURS)

        def score(r: Rule, _a: int = a) -> float:
            w = window(runs[r], _a - FIT_HOURS, _a)
            return w["net_pct"] / max(w["max_dd_pct"], 0.5)
        best = max(GRID, key=score)
        seg = runs[best].curve[a - 1: b]
        part = seg[1:] / seg[0] * level
        curve.extend(part.tolist())
        stats.append({"from": str(pd.Timestamp(p.times[a], tz="UTC").date()), "rule": best.label(),
                      "net_pct": round((seg[-1] / seg[0] - 1) * 100, 2)})
        level = part[-1]
        chosen.append(best)
    arr = np.array(curve)
    peak = np.maximum.accumulate(arr)
    dd = float(((peak - arr) / peak).max() * 100)
    net = (level - 1) * 100
    return {"net_pct": round(net, 2), "max_dd_pct": round(dd, 2), "net_dd": round(net / dd, 2) if dd > 0 else None,
            "blocks": stats, "blocks_positive": sum(1 for s in stats if s["net_pct"] > 0),
            "start": str(pd.Timestamp(p.times[min(FIT_HOURS, T - 1)], tz="UTC").date()),
            "annual_pct": round(((level) ** (8760 / max(1, len(arr) - 1)) - 1) * 100, 2) if level > 0 else -100.0}


def _sim(args: tuple) -> tuple:
    return args[0], simulate(PANEL, args[0])


PANEL: Panel


def experiments(p: Panel, workers: int) -> dict:
    global PANEL
    PANEL = p
    rules = [*GRID, Rule(0, -math.inf, -math.inf)]
    if "BTCUSDT" in p.names:
        rules.append(Rule(0, -math.inf, -math.inf, only="BTCUSDT"))
    with Pool(max(1, workers)) as pool:
        runs = dict(pool.map(_sim, [(r,) for r in rules]))
    T = len(p.times)
    full = {r.label(): {**window(runs[r], 0, T), "trades": len(runs[r].trades), "rebalances": runs[r].rebalances,
                        "quarters_positive": sum(1 for _, a, b in quarters(p.times) if window(runs[r], a, b)["net_pct"] > 0),
                        "quarters": len(quarters(p.times))} for r in rules}
    per_q = []
    for name, a, b in quarters(p.times):
        row: dict[str, Any] = {"quarter": name, "default": window(runs[DEFAULT], a, b), "always": window(runs[rules[len(GRID)]], a, b)}
        if p.btc is not None:
            s0, s1 = p.btc[a - 1] if a > 0 else p.btc[a], p.btc[b - 1]
            row["btc_pct"] = round((s1 / s0 - 1) * 100, 2) if not (math.isnan(s0) or math.isnan(s1)) else None
        per_q.append(row)
    wf = walk_forward(p, runs)
    trades = runs[DEFAULT].trades
    worst = sorted(trades, key=lambda x: x["pnl"] / x["alloc"])[:5]
    flips = sum(1 for x in trades if x["why"] == "financiación baja")
    neg = sum(1 for x in trades if x["funding"] < 0)
    by_symbol: dict[str, dict] = {}
    for x in trades:
        d = by_symbol.setdefault(x["symbol"], {"trades": 0, "pnl": 0.0, "funding": 0.0})
        d["trades"] += 1
        d["pnl"] += x["pnl"]
        d["funding"] += x["funding"]
    return {"full": full, "quarters": per_q, "walk_forward": wf,
            "default": {"rule": DEFAULT.label(), "trades": len(trades), "exits_low_funding": flips,
                        "trades_negative_funding": neg, "rebalances": runs[DEFAULT].rebalances,
                        "worst_trades": [{**w, "t0": str(pd.Timestamp(w["t0"], tz="UTC").date()),
                                          "t1": str(pd.Timestamp(w["t1"], tz="UTC").date()),
                                          "ret_pct": round(w["pnl"] / w["alloc"] * 100, 2)} for w in worst],
                        "by_symbol": {s: {k: round(v, 2) if isinstance(v, float) else v for k, v in d.items()}
                                      for s, d in sorted(by_symbol.items())}}}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def verdict(res: dict) -> list[str]:
    wf = res["walk_forward"]
    qs = res["quarters"]
    pos_q = sum(1 for q in qs if q["default"]["net_pct"] > 0)
    lines = []
    ok = (wf["net_dd"] or 0) > 1 and wf["blocks_positive"] >= 0.75 * max(1, len(wf["blocks"]))
    lines.append(("**Pasa:** " if ok else "**No pasa:** ")
                 + f"walk-forward {wf['net_pct']:+.1f}% neto ({wf['annual_pct']:+.1f}% anual), caída {wf['max_dd_pct']}%, "
                 f"neto/caída {wf['net_dd']}, {wf['blocks_positive']}/{len(wf['blocks'])} bloques de 30 días positivos "
                 "(listón: neto/caída > 1 y al menos 75% de bloques positivos).")
    lines.append(f"Regla por defecto ({res['default']['rule']}): positiva en {pos_q} de {len(qs)} trimestres.")
    return lines


def render(res: dict, meta: dict) -> str:
    L = [f"# Carry de financiación, neutral al mercado ({meta['desde']} a {meta['hasta']})", "",
         "Investigación con datos públicos (sin cuenta, sin órdenes). Spot comprado + perpetuo vendido de la misma "
         "moneda y la misma cantidad mientras la financiación sea positiva: el corto cobra la financiación y los "
         "movimientos de precio se compensan (salvo la base). Cada posición usa 1/K del capital: la mitad compra "
         "spot, la otra mitad es el margen del corto (1x, eficiencia de capital 50%). Costes por pata y lado: spot "
         "0,10%, perpetuo 0,05%, más 0,02% de deslizamiento en cada una. Decisión cada 8 h. Monedas: "
         + ", ".join(meta["simbolos"]) + ".", "", "## Veredicto", "", *verdict(res), "",
         "## 1. Todo el periodo, por regla", "",
         "| Regla | Neto % | Anual % | Máx. caída | Neto/caída | Financiación % | Costes % | Base % | Tiempo dentro | "
         "Peor día | Peor semana | Ops | Rebalanceos | Trimestres + |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, s in res["full"].items():
        L.append(f"| {name} | {s['net_pct']:+.1f}% | {s['annual_pct']:+.1f}% | {s['max_dd_pct']}% | {s['net_dd']} | "
                 f"{s['funding_pct']:+.1f}% | {s['costs_pct']:.1f}% | {s['basis_pct']:+.1f}% | {s['invested_pct']}% | "
                 f"{s['worst_day_pct']}% | {s['worst_week_pct']}% | {s['trades']} | {s['rebalances']} | "
                 f"{s['quarters_positive']}/{s['quarters']} |")
    wf = res["walk_forward"]
    L += ["", f"## 2. Walk-forward (ajuste 90 días, prueba 30, desde {wf['start']})", "",
          f"{wf['net_pct']:+.1f}% neto, {wf['annual_pct']:+.1f}% anual, caída {wf['max_dd_pct']}%, neto/caída {wf['net_dd']}, "
          f"{wf['blocks_positive']}/{len(wf['blocks'])} bloques positivos. El cambio de regla entre bloques no paga "
          "costes extra aquí (cada regla corre continua).", "",
          "| Bloque | Regla elegida | Neto % |", "|---|---|---|"]
    for b in wf["blocks"]:
        L.append(f"| {b['from']} | {b['rule']} | {b['net_pct']:+.2f}% |")
    L += ["", f"## 3. Por trimestre: regla por defecto ({res['default']['rule']}) y siempre dentro", "",
          "| Trimestre | Neto % | Financiación % | Costes % | Base % | Máx. caída | Tiempo dentro | Siempre dentro: neto % / caída | BTC % |",
          "|---|---|---|---|---|---|---|---|---|"]
    for q in res["quarters"]:
        d, a = q["default"], q["always"]
        L.append(f"| {q['quarter']} | {d['net_pct']:+.2f}% | {d['funding_pct']:+.2f}% | {d['costs_pct']:.2f}% | "
                 f"{d['basis_pct']:+.2f}% | {d['max_dd_pct']}% | {d['invested_pct']}% | {a['net_pct']:+.2f}% / "
                 f"{a['max_dd_pct']}% | {q.get('btc_pct')}% |")
    d = res["default"]
    L += ["", "## 4. Riesgos: financiación que se da vuelta y base que se dispara", "",
          f"- Operaciones: {d['trades']}; salidas porque la financiación bajó: {d['exits_low_funding']}; operaciones que "
          f"terminaron pagando financiación neta: {d['trades_negative_funding']}; rebalanceos por pérdida del corto: "
          f"{d['rebalances']}.", "", "| Peor operación | Desde | Hasta | Resultado sobre lo asignado | Financiación (USDT) |",
          "|---|---|---|---|---|"]
    for w in d["worst_trades"]:
        L.append(f"| {w['symbol']} | {w['t0']} | {w['t1']} | {w['ret_pct']:+.2f}% | {w['funding']:.2f} |")
    L += ["", "| Moneda | Ops | Resultado (USDT) | Financiación (USDT) |", "|---|---|---|---|"]
    for s, v in d["by_symbol"].items():
        L.append(f"| {s} | {v['trades']} | {v['pnl']:+.2f} | {v['funding']:+.2f} |")
    L += ["", "Advertencias: precios horarios (el desfase spot/perpetuo dentro de la hora no se ve); sin costes de "
          "transferir margen entre spot y futuros; sin riesgo de contraparte ni de bloqueo de retiros; la financiación "
          "del mes en curso puede faltar en el archivo público (sin dato, sin señal). Operaciones pocas por "
          "naturaleza: la evidencia es la serie de trimestres, no el número de operaciones. Un resultado pasado no "
          "promete uno futuro."]
    return "\n".join(L) + "\n"


def _load(args: tuple) -> tuple[str, tuple, str]:
    sym, start_iso, end_iso = args
    start, end = datetime.fromisoformat(start_iso), datetime.fromisoformat(end_iso)
    try:
        spot = fetch_spot_1h(sym, start, end)
    except Exception as error:  # noqa: BLE001 - one symbol must not stop the others
        spot = pd.Series(dtype=float)
        note = f"spot sin datos ({type(error).__name__})"
    else:
        note = f"spot {len(spot)}"
    perp = fetch_perp_1h(sym, start, end)
    fund = tw.fetch_funding(sym, start - timedelta(days=10), end)
    return sym, (spot, perp, fund), f"{note}, perpetuo {len(perp)}, financiación {len(fund)}"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Carry de financiación neutral al mercado (investigación)")
    parser.add_argument("--desde", default=DEFAULT_START)
    parser.add_argument("--hasta", default=None)
    parser.add_argument("--simbolos", nargs="+", default=list(tw.SYMBOLS))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    start = datetime.fromisoformat(args.desde).replace(tzinfo=timezone.utc)
    end = (datetime.fromisoformat(args.hasta).replace(tzinfo=timezone.utc) if args.hasta
           else datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0))
    with Pool(max(1, args.workers)) as pool:
        loaded = pool.map(_load, [(s, start.isoformat(), end.isoformat()) for s in args.simbolos])
    raw = {}
    last_funding = []
    for sym, data, note in loaded:
        print(f"{sym}: {note}")
        if not data[0].empty and not data[1].empty and not data[2].empty:
            raw[sym] = data
            last_funding.append(data[2].index[-1])
    end = min(end, max(last_funding).to_pydatetime()) if last_funding else end
    p = build_panel(raw, start, end, tuple(sorted({r.lookback for r in GRID})))
    res = experiments(p, args.workers)
    meta = {"desde": start.date().isoformat(), "hasta": end.date().isoformat(), "simbolos": p.names}
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = end.date().isoformat()
    (args.salida / f"carry_{stamp}.json").write_text(json.dumps({"meta": meta, **res}, indent=1, default=str),
                                                     encoding="utf-8")
    report = render(res, meta)
    (args.salida / f"carry_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
