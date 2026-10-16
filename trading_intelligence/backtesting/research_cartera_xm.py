"""
Multi-market trend portfolio on XM (leader, 2026-10-16), research only.

Preregistered in docs/research/cartera_xm/PREREGISTRO.md before any run. Carver's EWMAC (four pairs, his fixed
forecast scalars, no fitting) on every instrument at once, equal risk per market, sized for a small XM account and
rounded to XM's lot step and minimum lot. Costs are XM's own: half the spread per side on what is traded (the larger
of the candle's recorded spread and the spread read in the instrument sheet) and the overnight swap from the sheet,
triple on the instrument's rollover day. Daily candles and sheets were read from the XM DEMO terminal, read-only,
into docs/research/cartera_xm/datos/. No account, no key, no orders. Nothing here changes config/ or live/.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import research_deflactado as rd

PAIRS = ((8, 32), (16, 64), (32, 128), (64, 256))
SCALARS = (5.3, 3.75, 2.65, 1.87)  # Carver, Systematic Trading (2015), EWMAC forecast scalars
FDM = 1.1  # forecast diversification multiplier for the four pairs
VOL_SPAN = 35
TARGET_ABS, CAP = 10.0, 20.0
RISK_PER_MARKET = 0.0025  # daily equity volatility per market at forecast 10
MAX_LEVER_POSITION, MAX_LEVER_TOTAL = 2.0, 6.0  # notional / equity
BUFFER = 0.10
CAPITAL = 200.0
YEARS = (("2024-10-12", "2025-10-12"), ("2025-10-13", "2026-10-13"))
DECISIVE_N = 258
DESK = {"2024-10-12": 1.67, "2025-10-13": -0.21}  # practice desk net/drawdown (docs/research/mesa/)
DATA_DIR = Path("docs/research/cartera_xm/datos")
OUT_DIR = Path("docs/research/cartera_xm")
ROWS = {"base": ("Cartera EWMAC, 200 USD, lotes de XM", CAPITAL, 1.0, True),
        "grande": ("Misma regla con 100.000 USD (sin efecto del lote mínimo)", 100_000.0, 1.0, True),
        "costes2": ("200 USD, spread y swap ×2", CAPITAL, 2.0, True)}


@dataclass(frozen=True)
class Spec:
    """What the XM sheet says about one instrument."""
    name: str
    contract: float  # units per lot
    vmin: float
    step: float
    point: float
    spread_pts: float  # spread read in the sheet, in points
    swap_long: float
    swap_short: float
    swap_mode: int  # MT5 SYMBOL_SWAP_MODE
    triple_day: int  # 0 Sunday ... 6 Saturday (MT5 swap_rollover3days)
    profit_ccy: str


@dataclass
class Market:
    days: pd.DatetimeIndex
    names: list[str]
    open: np.ndarray  # [n, T], NaN when the market did not trade that day
    close: np.ndarray  # [n, T], forward-filled for marking
    spread: np.ndarray  # [n, T] in price units (NaN when unknown)
    traded: np.ndarray  # [n, T] bool: a real candle that day
    usd: np.ndarray  # [n, T] value of 1 unit of the profit currency in USD


# ---------------------------------------------------------------------------
# Rule
# ---------------------------------------------------------------------------

def forecasts(close: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Combined forecast [n, T] and daily return volatility [n, T], causal, on each market's own trading days."""
    n, T = close.shape
    fc = np.full((n, T), np.nan)
    vol_r = np.full((n, T), np.nan)
    for i in range(n):
        c = pd.Series(close[i])
        vol = c.diff().ewm(span=VOL_SPAN, adjust=False, min_periods=VOL_SPAN).std()
        vol_r[i] = (vol / c).values
        parts = []
        for (f, s), k in zip(PAIRS, SCALARS):
            raw = (c.ewm(span=f, adjust=False, min_periods=s).mean() - c.ewm(span=s, adjust=False, min_periods=s).mean())
            parts.append(np.clip((raw / vol.replace(0, np.nan)).values * k, -CAP, CAP))
        stack = np.vstack(parts)
        have = np.isfinite(stack).sum(axis=0)
        avg = np.where(have > 0, np.nansum(stack, axis=0) / np.maximum(have, 1), np.nan)
        fc[i] = np.clip(avg * FDM, -CAP, CAP)
    return fc, vol_r


def round_lots(units: float, spec: Spec) -> float:
    """Units rounded to XM's lot step; below half the minimum lot is no position, between half and one is one
    minimum lot."""
    lots = abs(units) / spec.contract
    if lots < spec.vmin / 2:
        return 0.0
    lots = max(spec.vmin, round(lots / spec.step) * spec.step)
    return float(np.sign(units) * lots * spec.contract)


def target_units(forecast: np.ndarray, vol_r: np.ndarray, price: np.ndarray, usd: np.ndarray, equity: float,
                 specs: list[Spec]) -> np.ndarray:
    """Units per market: (F/10) x 0.25% of equity / daily vol, capped at 2x equity per position and 6x in total,
    then rounded to lots."""
    n = len(specs)
    notional = np.zeros(n)
    for i in range(n):
        if not (np.isfinite(forecast[i]) and np.isfinite(vol_r[i]) and vol_r[i] > 0 and np.isfinite(price[i])):
            continue
        notional[i] = np.clip(forecast[i] / TARGET_ABS * RISK_PER_MARKET * equity / vol_r[i],
                              -MAX_LEVER_POSITION * equity, MAX_LEVER_POSITION * equity)
    total = np.abs(notional).sum()
    if total > MAX_LEVER_TOTAL * equity:
        notional *= MAX_LEVER_TOTAL * equity / total
    units = np.zeros(n)
    for i in range(n):
        if notional[i]:
            units[i] = round_lots(notional[i] / (price[i] * usd[i]), specs[i])
            if abs(units[i]) * price[i] * usd[i] > MAX_LEVER_POSITION * equity:
                units[i] = 0.0  # the minimum lot alone is above the per-position cap
    return units


def swap_cost(units: float, spec: Spec, price: float, usd: float, nights: int, mult: float) -> float:
    """USD paid (positive) or received (negative) for holding `units` for `nights` nights."""
    if units == 0 or nights == 0 or spec.swap_mode == 0:
        return 0.0
    rate = spec.swap_long if units > 0 else spec.swap_short
    lots = abs(units) / spec.contract
    if spec.swap_mode == 1:  # points per lot
        got = rate * spec.point * spec.contract * lots * usd
    elif spec.swap_mode in (2, 3, 4):  # money per lot (taken as USD-valued: base/margin converted at usd)
        got = rate * lots * (1.0 if spec.swap_mode == 4 else usd)
    elif spec.swap_mode in (5, 6, 7, 8):  # annual % of the price
        got = rate / 100 / 360 * abs(units) * price * usd
    else:
        got = 0.0
    return -got * nights * mult


def nights_held(day: pd.Timestamp, spec: Spec, weekend_bars: bool) -> int:
    if weekend_bars:
        return 1
    return 3 if (day.dayofweek + 1) % 7 == spec.triple_day else 1


@dataclass
class Result:
    equity: np.ndarray
    days: pd.DatetimeIndex
    orders: int = 0
    entries: int = 0
    spread_paid: float = 0.0
    swap_paid: float = 0.0
    per_market: dict = field(default_factory=dict)
    traded_markets: list = field(default_factory=list)


def simulate(m: Market, specs: list[Spec], start: int, end: int, capital: float = CAPITAL, mult: float = 1.0,
             use_lots: bool = True) -> Result:
    """Orders at the next trading day's open of each market; marked at the close in USD."""
    fc, vol_r = forecasts_on_own_days(m)
    n = len(specs)
    weekend = [bool(m.traded[i][m.days.dayofweek >= 5].any()) for i in range(n)]
    cash, q = capital, np.zeros(n)
    eq: list[float] = []
    res = Result(np.array([]), m.days[start:end], per_market={s.name: 0.0 for s in specs})
    pending: Optional[np.ndarray] = None
    last_mark = m.close[:, start - 1].copy() if start > 0 else m.close[:, start].copy()
    for t in range(start, end):
        if pending is not None:
            for i in range(n):
                if not m.traded[i, t] or not np.isfinite(m.open[i, t]):
                    continue
                want, cur = pending[i], q[i]
                if want == cur:
                    continue
                if cur != 0 and want != 0 and np.sign(want) == np.sign(cur) and abs(want - cur) <= BUFFER * abs(cur):
                    continue
                cash += q[i] * (m.open[i, t] - last_mark[i]) * m.usd[i, t]  # mark to the open before trading
                res.per_market[specs[i].name] += q[i] * (m.open[i, t] - last_mark[i]) * m.usd[i, t]
                last_mark[i] = m.open[i, t]
                spread = m.spread[i, t] if np.isfinite(m.spread[i, t]) else specs[i].spread_pts * specs[i].point
                spread = max(spread, specs[i].spread_pts * specs[i].point)
                cost = abs(want - cur) * spread / 2 * mult * m.usd[i, t]
                cash -= cost
                res.spread_paid += cost
                res.per_market[specs[i].name] -= cost
                res.orders += 1
                if want != 0 and (cur == 0 or np.sign(want) != np.sign(cur)):
                    res.entries += 1
                    if specs[i].name not in res.traded_markets:
                        res.traded_markets.append(specs[i].name)
                q[i] = want
        for i in range(n):
            if q[i] and m.traded[i, t]:
                pnl = q[i] * (m.close[i, t] - last_mark[i]) * m.usd[i, t]
                cash += pnl
                res.per_market[specs[i].name] += pnl
                last_mark[i] = m.close[i, t]
                sw = swap_cost(q[i], specs[i], m.close[i, t], m.usd[i, t], nights_held(m.days[t], specs[i], weekend[i]),
                               mult)
                cash -= sw
                res.swap_paid += sw
                res.per_market[specs[i].name] -= sw
            elif m.traded[i, t]:
                last_mark[i] = m.close[i, t]
        eq.append(cash)
        price = m.close[:, t]
        if use_lots:
            pending = target_units(fc[:, t], vol_r[:, t], price, m.usd[:, t], cash, specs)
        else:
            free = [Spec(s.name, s.contract, 1e-12, 1e-12, s.point, s.spread_pts, s.swap_long, s.swap_short,
                         s.swap_mode, s.triple_day, s.profit_ccy) for s in specs]
            pending = target_units(fc[:, t], vol_r[:, t], price, m.usd[:, t], cash, free)
    res.equity = np.array(eq)
    return res


def forecasts_on_own_days(m: Market) -> tuple[np.ndarray, np.ndarray]:
    """Forecasts computed on each market's own candles (no forward-filled days), then carried to the calendar."""
    n, T = m.close.shape
    fc = np.full((n, T), np.nan)
    vol_r = np.full((n, T), np.nan)
    for i in range(n):
        idx = np.where(m.traded[i])[0]
        if len(idx) == 0:
            continue
        f, v = forecasts(m.close[i, idx][None, :])
        tmp_f, tmp_v = np.full(T, np.nan), np.full(T, np.nan)
        tmp_f[idx], tmp_v[idx] = f[0], v[0]
        fc[i] = pd.Series(tmp_f).ffill().values
        vol_r[i] = pd.Series(tmp_v).ffill().values
    return fc, vol_r


# ---------------------------------------------------------------------------
# Judging
# ---------------------------------------------------------------------------

def summarize(r: Result, capital: float, n_decisive: int) -> dict:
    eq = r.equity if len(r.equity) else np.array([capital])
    curve = np.r_[capital, eq]
    peak = np.maximum.accumulate(curve)
    dd = float(((peak - curve) / peak).max() * 100)
    net = (eq[-1] / capital - 1) * 100
    m = rd.moments(pd.Series(curve).pct_change().dropna().reset_index(drop=True))  # calendar days
    m["sr_anual"] = m["sr_dia"] * np.sqrt(365)
    dsr = rd.deflated_sharpe(m["sr_dia"], m["T"], m["asimetria"], m["curtosis"], n_decisive, 1 / m["T"]) \
        if m["T"] > 2 and m["sr_dia"] != 0 else 0.0
    q = np.array_split(np.arange(len(eq)), 4)
    quarters = [round((eq[i[-1]] / (eq[i[0] - 1] if i[0] > 0 else capital) - 1) * 100, 1) for i in q if len(i)]
    return {"net_pct": round(net, 2), "max_dd_pct": round(dd, 2), "net_dd": round(net / dd, 2) if dd > 0 else None,
            "orders": r.orders, "entries": r.entries, "spread_pct": round(r.spread_paid / capital * 100, 2),
            "swap_pct": round(r.swap_paid / capital * 100, 2), "sharpe_anual": round(m["sr_anual"], 2),
            "dsr": round(dsr, 3), "quarters": quarters, "traded_markets": r.traded_markets,
            "per_market_pct": {k: round(v / capital * 100, 2) for k, v in r.per_market.items()},
            "daily_equity": {str(d.date()): round(float(v), 4) for d, v in zip(r.days, eq)}}


def passes(years: list[dict], key: str = "base") -> tuple[bool, bool, bool]:
    beats = all((y["rows"][key]["net_dd"] or -99) > y["desk"] for y in years)
    dsr_ok = years[-1]["rows"][key]["dsr"] >= rd.PASS_DSR
    return beats and dsr_ok, beats, dsr_ok


def lot_check(specs: list[Spec], m: Market, t: int, capital: float) -> list[dict]:
    """For each market: the minimum lot's notional against the equal-risk target at forecast 10."""
    _, vol_r = forecasts_on_own_days(m)
    out = []
    for i, s in enumerate(specs):
        px, usd = m.close[i, t], m.usd[i, t]
        min_notional = s.vmin * s.contract * px * usd
        target = RISK_PER_MARKET * capital / vol_r[i, t] if np.isfinite(vol_r[i, t]) and vol_r[i, t] > 0 else np.nan
        out.append({"market": s.name, "min_lot_usd": round(float(min_notional), 2),
                    "target_usd": round(float(target), 2) if np.isfinite(target) else None,
                    "ratio": round(float(min_notional / target), 1) if np.isfinite(target) and target > 0 else None,
                    "fits": bool(np.isfinite(target) and min_notional <= 2 * target
                                 and min_notional <= MAX_LEVER_POSITION * capital)})
    return out


def render(years: list[dict], lots: list[dict], n_decisive: int) -> str:
    ok, beats, dsr_ok = passes(years)
    fit = [x["market"] for x in lots if x["fits"]]
    L = ["# Cartera de tendencia multi-mercado en XM", "",
         "Preregistro: `docs/research/cartera_xm/PREREGISTRO.md`, escrito antes de correr. EWMAC de Carver (cuatro pares, "
         "escalas fijas) en todos los mercados a la vez, riesgo igual por mercado, lotes de XM; spread y swap de XM. "
         f"Sharpe deflactado con N = {n_decisive} decisorias y V = 1/T.", "", "## Veredicto", "",
         f"- **{'Pasa' if ok else 'No pasa'}.** Neto/caída con 200 USD "
         + " ; ".join(f"{y['rows']['base']['net_dd']}" for y in years)
         + f" contra la mesa {' ; '.join(str(y['desk']) for y in years)} ({'gana' if beats else 'no gana'} los dos "
         f"años); Sharpe deflactado 2025-26 {years[-1]['rows']['base']['dsr']} (listón {rd.PASS_DSR}"
         f"{', pasa' if dsr_ok else ', no pasa'}).",
         f"- **Lotes con 200 USD:** caben {len(fit)} de {len(lots)} mercados con riesgo igual ("
         + (", ".join(fit) if fit else "ninguno") + ")."]
    for y in years:
        L += ["", f"## {y['label']} (mesa de práctica neto/caída {y['desk']})", "",
              "| Fila | Neto % | Máx. caída | Neto/caída | Órdenes | Entradas | Spread % | Swap % | Sharpe anual | "
              "Sharpe deflactado | Trimestres (neto %) | Mercados operados |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for key, r in y["rows"].items():
            L.append(f"| {ROWS[key][0]} | {r['net_pct']:+.1f}% | {r['max_dd_pct']}% | {r['net_dd']} | {r['orders']} | "
                     f"{r['entries']} | {r['spread_pct']} | {r['swap_pct']} | {r['sharpe_anual']} | {r['dsr']} | "
                     + " / ".join(f"{q:+.1f}" for q in r["quarters"]) + f" | {len(r['traded_markets'])} |")
        L += ["", "Aporte por mercado, fila de 100.000 USD (neto % del capital): "
              + ", ".join(f"{k} {v:+.1f}" for k, v in y["rows"]["grande"]["per_market_pct"].items())]
    L += ["", "## Lote mínimo contra el tamaño de riesgo igual con 200 USD", "",
          "| Mercado | Lote mínimo (USD expuestos) | Tamaño buscado a pronóstico 10 (USD) | Veces | Cabe |", "|---|---|---|---|---|"]
    for x in lots:
        L.append(f"| {x['market']} | {x['min_lot_usd']} | {x['target_usd']} | {x['ratio']} | {'sí' if x['fits'] else 'no'} |")
    L += ["", "El spread y el swap son los de la ficha de hoy y el spread de cada vela; el swap histórico pudo ser otro. "
          "El capital diario está en el JSON. Un resultado pasado no promete uno futuro."]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# Data (files written by Claude local from the XM DEMO terminal)
# ---------------------------------------------------------------------------

def load_specs(path: Path) -> dict[str, Spec]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: Spec(k, float(v["contract"]), float(v["vmin"]), float(v["step"]), float(v["point"]),
                    float(v["spread_pts"]), float(v["swap_long"]), float(v["swap_short"]), int(v["swap_mode"]),
                    int(v["triple_day"]), str(v["profit_ccy"])) for k, v in data.items()}


def load_candles(path: Path, point: float) -> pd.DataFrame:
    df = pd.read_csv(path)
    t = df["time"]
    df.index = pd.to_datetime(t, unit="s", utc=True) if np.issubdtype(t.dtype, np.number) else pd.to_datetime(t, utc=True)
    df.index = df.index.floor("D")
    df = df[~df.index.duplicated(keep="last")]
    df["spread_px"] = df["spread"] * point if "spread" in df else np.nan
    return df


FX_FOR = {"USD": None, "EUR": ("EURUSD", False), "GBP": ("GBPUSD", False), "AUD": ("AUDUSD", False),
          "JPY": ("USDJPY", True), "CAD": ("USDCAD", True), "CHF": ("USDCHF", True)}


def build(frames: dict[str, pd.DataFrame], specs: dict[str, Spec]) -> Market:
    names = sorted(frames)
    days = pd.date_range(min(f.index.min() for f in frames.values()), max(f.index.max() for f in frames.values()),
                         freq="D", tz="UTC")
    T, n = len(days), len(names)
    op, cl, sp, tr, usd = (np.full((n, T), np.nan) for _ in range(5))
    for i, s in enumerate(names):
        f = frames[s].reindex(days)
        tr[i] = f["close"].notna().values
        op[i] = f["open"].values
        cl[i] = f["close"].ffill().values
        sp[i] = f["spread_px"].values
    for i, s in enumerate(names):
        ccy = specs[s].profit_ccy
        rule = FX_FOR.get(ccy, None)
        if rule is None:
            usd[i] = 1.0
            continue
        fx, invert = rule
        if fx not in frames:
            raise ValueError(f"{s}: falta {fx} para pasar {ccy} a USD")
        series = frames[fx]["close"].reindex(days).ffill().bfill().values
        usd[i] = 1 / series if invert else series
    return Market(days, names, op, cl, sp, tr.astype(bool), usd)


def year(m: Market, specs: list[Spec], a: str, b: str, n_decisive: int) -> dict:
    lo = int(m.days.searchsorted(pd.Timestamp(a, tz="UTC")))
    hi = int(m.days.searchsorted(pd.Timestamp(b, tz="UTC")))
    rows = {}
    for key, (_, cap, mult, lots) in ROWS.items():
        rows[key] = summarize(simulate(m, specs, lo, hi, cap, mult, lots), cap, n_decisive)
    return {"label": f"{a} → {b}", "desk": DESK[a], "rows": rows}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Cartera de tendencia multi-mercado en XM (investigación)")
    parser.add_argument("--datos", type=Path, default=DATA_DIR)
    parser.add_argument("--decisorias", type=int, default=DECISIVE_N)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    specs = load_specs(args.datos / "fichas.json")
    frames = {}
    for name, s in specs.items():
        path = args.datos / f"{name}_D1.csv"
        if path.exists():
            frames[name] = load_candles(path, s.point)
            print(f"{name}: {len(frames[name])} velas desde {frames[name].index[0].date()}")
        else:
            print(f"{name}: sin velas, fuera")
    m = build(frames, specs)
    ordered = [specs[s] for s in m.names]
    years = [year(m, ordered, a, b, args.decisorias) for a, b in YEARS]
    lots = lot_check(ordered, m, int(m.days.searchsorted(pd.Timestamp(YEARS[-1][1], tz="UTC"))) - 1, CAPITAL)
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    out: dict[str, Any] = {"years": years, "lots": lots}
    (args.salida / f"cartera_xm_{stamp}.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    report = render(years, lots, args.decisorias)
    (args.salida / f"cartera_xm_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
