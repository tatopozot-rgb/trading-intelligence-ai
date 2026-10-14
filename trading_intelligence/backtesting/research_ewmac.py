"""
EWMAC trend following (Robert Carver, pysystemtrade) on the desk's 12 coins, research only.

Rules and judging are preregistered in docs/research/ewmac/PREREGISTRO.md (written before any run):
four EWMA pairs (8/32, 16/64, 32/128, 64/256 days) on daily closes, each divided by the price volatility
(exponential std of daily price changes, span 35), scaled so its mean |forecast| over the 90 days before each
30-day test block is 10, capped at +-20, averaged, capped again. Position = (forecast / 10) x 1% / daily return
volatility of equity, capped at +-50%, only the 3 strongest |forecast|, 1x overall. Orders at the next day's
open; an open position is changed only if its target moves more than 10%. No stops. Fees 0.05% and slippage
0.02% per side, real funding. Public data only: no account, no key, no orders. Nothing touches config/ or live/.
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
from trading_intelligence.backtesting import two_way_backtest as tw

PAIRS = ((8, 32), (16, 64), (32, 128), (64, 256))
VOL_SPAN = 35
TARGET_ABS, CAP = 10.0, 20.0
DAILY_RISK = 0.01  # equity volatility per position at forecast 10
MAX_POSITION, MAX_OPEN, BUFFER = tw.MAX_POSITION, 3, 0.10
COST = tw.FEE + 0.0002  # fee + slippage, per side
FIT_DAYS, BLOCK_DAYS = 90, 30
CAPITAL = 1000.0
WARM_FROM = "2021-01-01"
YEARS = (("2024-10-12", "2025-10-12"), ("2025-10-13", "2026-10-13"))
OUT_DIR = Path("docs/research/ewmac")
# docs/research/mesa/ (same windows): net %, max drawdown %, net/drawdown
DESK = {"2024-10-12": {"mesa_r3": (17.6, 58.18, 0.30), "mesa_r3 + freno b": (78.2, 46.89, 1.67)},
        "2025-10-13": {"mesa_r3": (-65.5, 75.5, -0.87), "mesa_r3 + freno b": (-7.4, 35.75, -0.21)}}
PRACTICE = "mesa_r3 + freno b"


@dataclass
class Data:
    days: pd.DatetimeIndex  # UTC midnights
    open: np.ndarray  # [n, T]
    close: np.ndarray
    funding: np.ndarray  # [n, T] % paid that day (sum of payments)
    names: list[str]


def raw_forecasts(close: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per pair [p, n, T] raw forecast, and the daily return volatility [n, T]. Causal (uses closes up to t)."""
    n, T = close.shape
    raw = np.full((len(PAIRS), n, T), np.nan)
    ret_vol = np.full((n, T), np.nan)
    for i in range(n):
        c = pd.Series(close[i])
        vol = c.diff().ewm(span=VOL_SPAN, adjust=False, min_periods=VOL_SPAN).std()
        ret_vol[i] = (vol / c).values
        for p, (f, s) in enumerate(PAIRS):
            fast = c.ewm(span=f, adjust=False, min_periods=s).mean()
            slow = c.ewm(span=s, adjust=False, min_periods=s).mean()
            raw[p, i] = ((fast - slow) / vol.replace(0, np.nan)).values
    return raw, ret_vol


def scalars(raw: np.ndarray, lo: int, hi: int) -> np.ndarray:
    """10 / mean |raw| per pair over days [lo, hi), all coins pooled (NaN if no data)."""
    out = np.full(raw.shape[0], np.nan)
    for p in range(raw.shape[0]):
        x = np.abs(raw[p, :, max(0, lo):hi])
        x = x[np.isfinite(x)]
        if len(x) and x.mean() > 0:
            out[p] = TARGET_ABS / x.mean()
    return out


def combine(raw_t: np.ndarray, scale: np.ndarray) -> np.ndarray:
    """raw_t [p, n] -> forecast [n]: scale, cap each pair, average the pairs available, cap."""
    scaled = np.clip(raw_t * scale[:, None], -CAP, CAP)
    with np.errstate(invalid="ignore"):
        f = np.nanmean(np.where(np.isfinite(scaled), scaled, np.nan), axis=0)
    return np.clip(f, -CAP, CAP)


def targets(forecast: np.ndarray, ret_vol: np.ndarray) -> np.ndarray:
    """Fraction of equity per coin: (F/10) x 1% / vol, capped at 50%, top 3 |F|, scaled into 1x."""
    frac = np.zeros(len(forecast))
    ok = np.isfinite(forecast) & np.isfinite(ret_vol) & (ret_vol > 0) & (forecast != 0)
    if not ok.any():
        return frac
    order = [i for i in np.argsort(-np.abs(np.where(ok, forecast, 0))) if ok[i]][:MAX_OPEN]
    for i in order:
        frac[i] = np.clip(forecast[i] / TARGET_ABS * DAILY_RISK / ret_vol[i], -MAX_POSITION, MAX_POSITION)
    total = np.abs(frac).sum()
    return frac / total if total > 1 else frac


@dataclass
class Result:
    equity: np.ndarray  # daily close equity over the test days
    days: pd.DatetimeIndex
    trades: list[dict] = field(default_factory=list)  # every order
    entries: int = 0
    fees: float = 0.0
    funding: float = 0.0
    mean_abs_forecast: float = 0.0
    scalars: list[dict] = field(default_factory=list)


def simulate(d: Data, start: int, end: int, capital: float = CAPITAL) -> Result:
    """Walk-forward EWMAC over days [start, end): scalars refitted every BLOCK_DAYS on the FIT_DAYS before."""
    raw, ret_vol = raw_forecasts(d.close)
    n = len(d.names)
    cash, q = capital, np.zeros(n)
    eq, trades, entries, fees, fund, absf, scal_log = [], [], 0, 0.0, 0.0, [], []
    scale = np.full(len(PAIRS), np.nan)
    pending: Optional[np.ndarray] = None  # target fractions decided at the previous close
    for t in range(start, end):
        if (t - start) % BLOCK_DAYS == 0:
            scale = scalars(raw, t - FIT_DAYS, t)
            scal_log.append({"from": str(d.days[t].date()), **{f"{f}/{s}": round(float(x), 3)
                                                                for (f, s), x in zip(PAIRS, scale)}})
        if pending is not None:  # orders at today's open
            px = d.open[:, t]
            equity_open = cash + float(np.nansum(q * px))
            for i in range(n):
                if not np.isfinite(px[i]):
                    continue
                want = pending[i] * equity_open / px[i]
                cur = q[i]
                change = (cur == 0 and want != 0) or (want == 0 and cur != 0) or \
                    (cur != 0 and abs(want - cur) > BUFFER * abs(cur)) or (np.sign(want) != np.sign(cur) and cur != 0)
                if not change:
                    continue
                dq = want - cur
                price = px[i] * (1 + 0.0002 * np.sign(dq))
                fee = abs(dq) * px[i] * tw.FEE
                cash -= dq * price + fee
                fees += fee + abs(dq) * px[i] * 0.0002
                if cur == 0 or np.sign(want) != np.sign(cur):
                    entries += 1 if want != 0 else 0
                trades.append({"day": str(d.days[t].date()), "symbol": d.names[i], "from": cur, "to": want})
                q[i] = want
        c = d.close[:, t]
        paid = float(np.nansum(q * c * d.funding[:, t] / 100))
        cash -= paid
        fund += paid
        eq.append(cash + float(np.nansum(np.where(np.isfinite(c), q * c, 0))))
        f = combine(raw[:, :, t], scale)
        absf.extend(np.abs(f[np.isfinite(f)]).tolist())
        pending = targets(f, ret_vol[:, t])
    return Result(np.array(eq), d.days[start:end], trades, entries, fees, fund,
                  float(np.mean(absf)) if absf else 0.0, scal_log)


def stats(r: Result, capital: float = CAPITAL) -> dict:
    e = np.r_[capital, r.equity]
    peak = np.maximum.accumulate(e)
    dd = float(((peak - e) / peak).max() * 100)
    net = (e[-1] / capital - 1) * 100
    return {"net_pct": round(net, 2), "max_dd_pct": round(dd, 2), "net_dd": round(net / dd, 2) if dd > 0 else None,
            "orders": len(r.trades), "entries": r.entries, "fees_usdt": round(r.fees, 2),
            "funding_usdt": round(r.funding, 2), "mean_abs_forecast": round(r.mean_abs_forecast, 2)}


def quarter_rows(r: Result, d: Data, start: int, capital: float = CAPITAL) -> list[dict]:
    btc = d.names.index("BTCUSDT") if "BTCUSDT" in d.names else None
    rows, a = [], 0
    T = len(r.equity)
    for q in range(4):
        b = min(T, a + (T - a) // (4 - q))
        e0 = r.equity[a - 1] if a > 0 else capital
        seg = np.r_[e0, r.equity[a:b]]
        peak = np.maximum.accumulate(seg)
        bh = None
        if btc is not None:
            p0, p1 = d.close[btc, start + a - 1], d.close[btc, start + b - 1]
            bh = round((p1 / p0 - 1) * 100, 2)
        rows.append({"from": str(r.days[a].date()), "to": str(r.days[b - 1].date()),
                     "net_pct": round((seg[-1] / e0 - 1) * 100, 2),
                     "max_dd_pct": round(float(((peak - seg) / peak).max() * 100), 2), "btc_pct": bh})
        a = b
    return rows


def year(d: Data, a: str, b: str) -> dict:
    start = int(d.days.searchsorted(pd.Timestamp(a, tz="UTC")))
    end = int(d.days.searchsorted(pd.Timestamp(b, tz="UTC")))
    r = simulate(d, start, end)
    s = stats(r)
    btc = d.names.index("BTCUSDT") if "BTCUSDT" in d.names else None
    bh = round((d.close[btc, end - 1] / d.close[btc, start - 1] - 1) * 100, 2) if btc is not None else None
    desk = DESK.get(a, {})
    beats = {k: (s["net_dd"] or -99) > v[2] for k, v in desk.items()}
    by_symbol: dict[str, int] = {}
    for tr in r.trades:
        by_symbol[tr["symbol"]] = by_symbol.get(tr["symbol"], 0) + 1
    return {"from": a, "to": b, "stats": s, "quarters": quarter_rows(r, d, start), "btc_pct": bh, "desk": desk,
            "beats": beats, "scalars": r.scalars, "orders_by_symbol": by_symbol}


def verdict(years: list[dict]) -> list[str]:
    ok = all(y["beats"].get(PRACTICE, False) for y in years)
    lines = [("**Pasa a práctica:** " if ok else "**No pasa:** ")
             + "neto/caída de EWMAC frente a la mesa de práctica (mesa_r3 + freno b) — "
             + "; ".join(f"{y['from']} → {y['to']}: {y['stats']['net_dd']} contra {y['desk'][PRACTICE][2]}"
                         for y in years if PRACTICE in y["desk"]) + "."]
    for y in years:
        if y["stats"]["entries"] < 100:
            lines.append(f"{y['from']} → {y['to']}: {y['stats']['entries']} entradas, muestra corta.")
    return lines


def render(years: list[dict], meta: dict) -> str:
    L = ["# EWMAC de Carver en las 12 monedas de la mesa", "",
         "Reglas preregistradas en `docs/research/ewmac/PREREGISTRO.md` antes de correr. Velas diarias de Spot, largos y "
         "cortos, 3 posiciones como máximo, 1x, 50% por posición, sin stops, operación en la apertura siguiente con "
         "un margen de 10%. Comisión 0,05% y deslizamiento 0,02% por lado, financiación real. Monedas: "
         + ", ".join(meta["simbolos"]) + ".", "", "## Veredicto", "", *verdict(years), "",
         "| Año | EWMAC neto % | Caída | Neto/caída | Entradas | Órdenes | mesa_r3 neto/caída | Mesa de práctica (freno b) neto/caída | BTC % |",
         "|---|---|---|---|---|---|---|---|---|"]
    for y in years:
        s, dk = y["stats"], y["desk"]
        L.append(f"| {y['from']} → {y['to']} | {s['net_pct']:+.1f}% | {s['max_dd_pct']}% | {s['net_dd']} | {s['entries']} | "
                 f"{s['orders']} | {dk.get('mesa_r3', (None, None, None))[2]} | {dk.get(PRACTICE, (None, None, None))[2]} | "
                 f"{y['btc_pct']}% |")
    for y in years:
        s = y["stats"]
        L += ["", f"## {y['from']} → {y['to']}", "",
              f"Comisiones y deslizamiento {s['fees_usdt']} USDT, financiación pagada {s['funding_usdt']} USDT, "
              f"|pronóstico| medio en la prueba {s['mean_abs_forecast']} (objetivo 10).", "",
              "| Trimestre | EWMAC neto % | Máx. caída | BTC % |", "|---|---|---|---|"]
        for q in y["quarters"]:
            L.append(f"| {q['from']} → {q['to']} | {q['net_pct']:+.2f}% | {q['max_dd_pct']}% | {q['btc_pct']}% |")
        L += ["", "Escalas por bloque (10 / |pronóstico crudo| medio de los 90 días anteriores): "
              + "; ".join(f"{x['from']}: " + ", ".join(f"{k} {v}" for k, v in x.items() if k != "from")
                          for x in y["scalars"][:3]) + (" …" if len(y["scalars"]) > 3 else ""),
              "", "Órdenes por moneda: " + ", ".join(f"{k} {v}" for k, v in sorted(y["orders_by_symbol"].items()))]
    L += ["", "Advertencias: Spot como aproximación del perpetuo; sin stops (una brecha grande pega entera); la mesa "
          "se cita de `docs/research/mesa/` en las mismas fechas (velas de 5 minutos, bloques de 30 días con 1.000 "
          "USDT), EWMAC corre continuo con 1.000 USDT al inicio de cada año. Un resultado pasado no promete uno futuro."]
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
    T = len(days)
    op, cl, fu = np.full((len(names), T), np.nan), np.full((len(names), T), np.nan), np.zeros((len(names), T))
    fund = {s: f for s, _, f, _ in loaded}
    for i, s in enumerate(names):
        k = frames[s].reindex(days)
        op[i], cl[i] = k["open"].values, k["close"].values
        f = fund.get(s)
        if f is not None and not f.empty:
            fu[i] = f.reindex(days).fillna(tw.FUNDING_PER_8H * 100 * 3).values
        else:
            fu[i] = tw.FUNDING_PER_8H * 100 * 3
    return Data(days, op, cl, fu, names)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="EWMAC de Carver (investigación, preregistrada)")
    parser.add_argument("--simbolos", nargs="+", default=list(tw.SYMBOLS))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    start = datetime.fromisoformat(WARM_FROM).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(YEARS[-1][1]).replace(tzinfo=timezone.utc) + timedelta(days=1)
    with Pool(max(1, args.workers)) as pool:
        loaded = pool.map(_load, [(s, start.isoformat(), end.isoformat()) for s in args.simbolos])
    for s, _, _, note in loaded:
        print(f"{s}: {note}")
    d = build(loaded)
    years = [year(d, a, b) for a, b in YEARS]
    meta: dict[str, Any] = {"simbolos": d.names, "datos_desde": str(d.days[0].date()), "datos_hasta": str(d.days[-1].date())}
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"ewmac_{stamp}.json").write_text(json.dumps({"meta": meta, "years": years}, indent=1, default=str),
                                                     encoding="utf-8")
    report = render(years, meta)
    (args.salida / f"ewmac_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
