"""
Trend-following research for Binance USDⓈ-M futures, long and short (research only: public data, no key,
no orders). Leader's task, 2026-10-12: find a trend / time-series momentum strategy that beats the live
desk (mesa_r3) out of sample on net return per unit of max drawdown. Rules: docs/research/PROTOCOLO.md.

Families (small grids, each also with a BTC regime filter: longs only while BTC closes above its 200-day
mean, shorts only below):
  donchian: 4h / 1d close beyond the previous N-bar channel (N=20/55); exit at the opposite M-bar
            channel (M=10/20, touched intrabar) or an ATR trailing stop (2/3/4 ATR on closes).
  ema:      EMA fast/slow crossover (4h 20/50, 20/100, 50/200; 1d 20/50), exit on the cross back or
            an ATR trailing stop (2/3/4 ATR).
  tsmom:    sign of the 30/60/90-day return, the 3 strongest by return / volatility, sized by inverse
            volatility, re-checked every day (held while in the top 3 or top 6).
Mechanics: hourly bars (Spot prices as a proxy for the perpetuals). A signal on a 4h / 1d close fills at
the next hour's open. Stops are checked every hour on the high / low; a gap through the stop fills at the
open. Fees 0.05% per side, slippage 0.02% per side, the real funding of every 8 h (0.01% when missing)
accrued hourly. Capital 1000 USDT, 1x, a position at most 50% of equity, 3 positions, all within the
equity; risk 5% of equity to the stop for the stop-based families.

Walk-forward: every combination runs continuously over the whole period. For each 30-day test window,
each family takes the combination with the best net/drawdown over the previous 90 days and keeps it for
the 30 days (changing combination pays fees and slippage on both books). Only the test windows count.
The desk (mesa_r3, two_way_backtest on 5-minute bars, starting at 1000 USDT every window as a session
would) and BTC buy-and-hold are measured on the same windows.

    python -m trading_intelligence.backtesting.research_tendencia --dias 365
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import two_way_backtest as tw

CAPITAL = 1000.0
FEE, SLIP = tw.FEE, 0.0002
RISK = 0.05  # equity lost if a stop-based trade hits its stop (before the position caps)
MAX_POSITION, MAX_OPEN, LEVERAGE = tw.MAX_POSITION, tw.MAX_OPEN, tw.LEVERAGE
TSMOM_VOL_TARGET = 0.20  # a TSMOM position's notional = equity x 20% / the coin's annual volatility (<= 50%)
FIT_DAYS, TEST_DAYS, WARMUP_DAYS = 90, 30, 220
REGIME_DAYS = 200
MIN_OOS_TRADES = 100
DAY = pd.Timedelta(days=1)
RULES = {"4h": "4h", "1d": "1D"}
OUT_DIR = Path("docs/research/tendencia")
DESK = "mesa_r3"

GRIDS: dict[str, list[dict]] = {
    "donchian": [{"tf": tf, "n": n, "salida": s} for tf, n, s in itertools.product(
        ("4h", "1d"), (20, 55), ("canal10", "canal20", "atr2", "atr3", "atr4"))],
    "ema": [{"tf": "4h", "rapida": f, "lenta": s, "atr": k} for (f, s), k in itertools.product(
        ((20, 50), (20, 100), (50, 200)), (2, 3, 4))]
    + [{"tf": "1d", "rapida": 20, "lenta": 50, "atr": k} for k in (2, 3, 4)],
    "tsmom": [{"dias": n, "vol": v, "mantener": h} for n, v, h in itertools.product((30, 60, 90), (20, 60), (3, 6))],
}


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class Market:
    times: pd.DatetimeIndex  # hourly, UTC
    bars: dict[str, pd.DataFrame]  # open/high/low/close aligned to `times` (NaN where missing)
    funding: dict[str, np.ndarray]  # funding rate per 8 h in force at each hour (fraction)
    regime: np.ndarray  # +1 BTC above its 200-day mean (last closed day), -1 below, 0 unknown


def btc_regime(times: pd.DatetimeIndex, btc: Optional[pd.DataFrame]) -> np.ndarray:
    if btc is None:
        return np.zeros(len(times))
    daily = btc["close"].resample("1D").last().dropna()
    sign = np.sign(daily - daily.rolling(REGIME_DAYS).mean())
    sign.index = sign.index + DAY  # known once the day has closed
    return sign.reindex(times, method="ffill").fillna(0.0).to_numpy()


def build_market(bars: dict[str, pd.DataFrame], funding: dict[str, pd.Series], times: pd.DatetimeIndex) -> Market:
    aligned = {s: b[["open", "high", "low", "close"]].reindex(times) for s, b in bars.items()}
    rates = {}
    for s in aligned:
        f = funding.get(s)
        if f is None or f.empty:
            rates[s] = np.full(len(times), tw.FUNDING_PER_8H)
        else:
            rates[s] = (f.sort_index().reindex(times, method="ffill") / 100).fillna(tw.FUNDING_PER_8H).to_numpy()
    return Market(times, aligned, rates, btc_regime(times, aligned.get("BTCUSDT")))


def load(oos_days: int, end: datetime, symbols: list[str], fetcher: tw.Fetcher = tw.fetch,
         funding_fetcher: Callable[[str, datetime, datetime], pd.Series] = tw.fetch_funding) -> Market:
    start = end - timedelta(days=oos_days + FIT_DAYS + WARMUP_DAYS)
    times = pd.date_range(start, end - timedelta(hours=1), freq="1h", tz="UTC")
    bars, funding = {}, {}
    for sym in symbols:
        try:
            bars[sym] = fetcher(sym, "1h", start, end)
        except Exception as error:  # noqa: BLE001 - one symbol's data must not stop the others
            print(f"{sym}: sin datos ({type(error).__name__})")
            continue
        funding[sym] = funding_fetcher(sym, start, end)
        print(f"{sym}: {len(bars[sym])} velas de 1 h, financiación {len(funding[sym])} puntos")
    return build_market(bars, funding, times)


# ---------------------------------------------------------------------------
# Signals: per symbol, per hour (an action at hour i uses only bars closed by the open of hour i)
# ---------------------------------------------------------------------------

@dataclass
class Plan:
    entry: dict[str, np.ndarray]  # +1 / -1 where a position may open at that hour's open, 0 elsewhere
    exit_long: dict[str, np.ndarray]  # close a long at that hour's open
    exit_short: dict[str, np.ndarray]
    stop_long: dict[str, np.ndarray]  # new stop level from that hour on (NaN: no update); ratchets only
    stop_short: dict[str, np.ndarray]
    strength: dict[str, np.ndarray]  # ranks simultaneous entries
    weight: Optional[dict[str, np.ndarray]] = None  # notional / equity (no-stop families)


def resample(bars: pd.DataFrame, tf: str) -> pd.DataFrame:
    out = bars.resample(RULES[tf], label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"})
    return out.dropna()


def to_hours(times: pd.DatetimeIndex, frame_index: pd.DatetimeIndex, tf: str, values, fill=np.nan) -> np.ndarray:
    """Place values of signal bars at the hour their bar closes (label + timeframe)."""
    out = np.full(len(times), fill, dtype=float)
    pos = times.get_indexer(frame_index + pd.Timedelta(RULES[tf]))
    vals = np.asarray(values, dtype=float)
    ok = pos >= 0
    out[pos[ok]] = vals[ok]
    return out


def atr(f: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = f["close"].shift(1)
    tr = pd.concat([f["high"] - f["low"], (f["high"] - prev).abs(), (f["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _empty(times: pd.DatetimeIndex, symbols) -> dict:
    return {s: np.zeros(len(times)) for s in symbols}


def donchian_plan(m: Market, tf: str, n: int, salida: str) -> Plan:
    plan = Plan(_empty(m.times, m.bars), {}, {}, {}, {}, {})
    for sym, bars in m.bars.items():
        f = resample(bars, tf)
        c, a = f["close"], atr(f)
        upper, lower = f["high"].rolling(n).max().shift(1), f["low"].rolling(n).min().shift(1)
        side = np.where(c > upper, 1.0, np.where(c < lower, -1.0, 0.0)) * a.notna()
        if salida.startswith("canal"):
            m_bars = int(salida[5:])
            sl, ss = f["low"].rolling(m_bars).min(), f["high"].rolling(m_bars).max()
        else:
            k = float(salida[3:])
            sl, ss = c - k * a, c + k * a
        strength = np.where(side > 0, (c - upper) / a, (lower - c) / a)
        plan.entry[sym] = np.nan_to_num(to_hours(m.times, f.index, tf, side))
        plan.exit_long[sym] = np.zeros(len(m.times), dtype=bool)
        plan.exit_short[sym] = np.zeros(len(m.times), dtype=bool)
        plan.stop_long[sym] = to_hours(m.times, f.index, tf, sl)
        plan.stop_short[sym] = to_hours(m.times, f.index, tf, ss)
        plan.strength[sym] = np.nan_to_num(to_hours(m.times, f.index, tf, strength))
    return plan


def ema_plan(m: Market, tf: str, rapida: int, lenta: int, atr_k: float) -> Plan:
    plan = Plan(_empty(m.times, m.bars), {}, {}, {}, {}, {})
    for sym, bars in m.bars.items():
        f = resample(bars, tf)
        c, a = f["close"], atr(f)
        fast, slow = c.ewm(span=rapida, adjust=False).mean(), c.ewm(span=lenta, adjust=False).mean()
        above = (fast > slow).astype(float)
        ready = (np.arange(len(f)) >= lenta) & a.notna().to_numpy()
        cross = above.diff().fillna(0.0).to_numpy() * ready  # +1 up, -1 down
        plan.entry[sym] = np.nan_to_num(to_hours(m.times, f.index, tf, cross))
        plan.exit_long[sym] = to_hours(m.times, f.index, tf, (fast < slow) & ready, 0.0) > 0
        plan.exit_short[sym] = to_hours(m.times, f.index, tf, (fast > slow) & ready, 0.0) > 0
        plan.stop_long[sym] = to_hours(m.times, f.index, tf, c - atr_k * a)
        plan.stop_short[sym] = to_hours(m.times, f.index, tf, c + atr_k * a)
        plan.strength[sym] = np.nan_to_num(to_hours(m.times, f.index, tf, (fast - slow).abs() / a))
    return plan


def tsmom_plan(m: Market, dias: int, vol: int, mantener: int) -> Plan:
    closes = pd.DataFrame({s: resample(b, "1d")["close"] for s, b in m.bars.items()})
    ret = closes / closes.shift(dias) - 1
    sigma = np.log(closes).diff().rolling(vol).std() * math.sqrt(365)
    score = ret / sigma
    rank = score.abs().rank(axis=1, ascending=False, method="first")
    sign = np.sign(ret)
    weight: dict[str, np.ndarray] = {}
    plan = Plan({}, {}, {}, {}, {}, {}, weight)
    nan = np.full(len(m.times), np.nan)
    for sym in m.bars:
        r, s, sg = rank[sym], sign[sym], sigma[sym]
        valid = s.notna() & sg.notna() & (sg > 0)
        entry = np.where(valid & (r <= MAX_OPEN), s, 0.0)
        drop = valid & (r > mantener)
        plan.entry[sym] = np.nan_to_num(to_hours(m.times, closes.index, "1d", entry))
        plan.exit_long[sym] = to_hours(m.times, closes.index, "1d", drop | (valid & (s <= 0)), 0.0) > 0
        plan.exit_short[sym] = to_hours(m.times, closes.index, "1d", drop | (valid & (s >= 0)), 0.0) > 0
        plan.stop_long[sym], plan.stop_short[sym] = nan, nan
        plan.strength[sym] = np.nan_to_num(to_hours(m.times, closes.index, "1d", score[sym].abs()))
        w = np.minimum(MAX_POSITION, TSMOM_VOL_TARGET / sg)
        weight[sym] = np.nan_to_num(to_hours(m.times, closes.index, "1d", w))
    return plan


def make_plan(m: Market, family: str, params: dict) -> Plan:
    if family == "donchian":
        return donchian_plan(m, params["tf"], params["n"], params["salida"])
    if family == "ema":
        return ema_plan(m, params["tf"], params["rapida"], params["lenta"], params["atr"])
    if family == "tsmom":
        return tsmom_plan(m, params["dias"], params["vol"], params["mantener"])
    raise ValueError(family)


# ---------------------------------------------------------------------------
# Portfolio simulation
# ---------------------------------------------------------------------------

@dataclass
class _Pos:
    side: int
    qty: float
    entry: float
    stop: float  # NaN = no stop
    fee_in: float
    entry_at: pd.Timestamp
    funding: float = 0.0


@dataclass
class Sim:
    equity: np.ndarray  # at each hour's close (NaN before the start)
    exposure: np.ndarray  # gross notional / equity at each hour's close
    trades: list[dict] = field(default_factory=list)
    skipped: int = 0


def simulate(m: Market, plan: Plan, lo: int, regime_filter: bool = False, capital: float = CAPITAL) -> Sim:
    n = len(m.times)
    syms = list(m.bars)
    o = {s: m.bars[s]["open"].to_numpy() for s in syms}
    h = {s: m.bars[s]["high"].to_numpy() for s in syms}
    low = {s: m.bars[s]["low"].to_numpy() for s in syms}
    c = {s: m.bars[s]["close"].to_numpy() for s in syms}
    last = {s: math.nan for s in syms}
    sim = Sim(np.full(n, np.nan), np.zeros(n))
    cash, eq = capital, capital
    pos: dict[str, _Pos] = {}

    def close(sym: str, raw: float, why: str, t: pd.Timestamp) -> None:
        nonlocal cash
        p = pos.pop(sym)
        price = raw * (1 - SLIP * p.side)
        gross = (price - p.entry) * p.qty * p.side
        fee_out = price * p.qty * FEE
        cash += gross - fee_out - p.funding
        sim.trades.append({"symbol": sym, "side": "BUY" if p.side > 0 else "SELL", "entry_at": p.entry_at.isoformat(),
                           "exit_at": t.isoformat(), "why": why, "pnl": gross - fee_out - p.fee_in - p.funding,
                           "fees": fee_out + p.fee_in, "funding": p.funding,
                           "ret_pct": (gross - fee_out - p.fee_in - p.funding) / (p.qty * p.entry) * 100})

    for i in range(lo, n):
        t = m.times[i]
        # 1. at the open: exits and stop updates from the bars that just closed
        for sym in list(pos):
            p, op = pos[sym], o[sym][i]
            if math.isnan(op):
                continue
            ex = plan.exit_long[sym][i] if p.side > 0 else plan.exit_short[sym][i]
            if ex or plan.entry[sym][i] == -p.side:
                close(sym, op, "señal", t)
                continue
            new = (plan.stop_long if p.side > 0 else plan.stop_short)[sym][i]
            if not math.isnan(new):
                p.stop = new if math.isnan(p.stop) else (max(p.stop, new) if p.side > 0 else min(p.stop, new))
        # 2. entries at the open, strongest first
        cands = [(plan.strength[s][i], s, int(plan.entry[s][i])) for s in syms
                 if plan.entry[s][i] != 0 and s not in pos and not math.isnan(o[s][i])]
        for _, sym, side in sorted(cands, reverse=True):
            if len(pos) >= MAX_OPEN:
                break
            if regime_filter and m.regime[i] != side:
                continue
            price = o[sym][i] * (1 + SLIP * side)
            used = sum(q.qty * q.entry for q in pos.values())
            room = max(0.0, LEVERAGE * eq - used) * 0.95 / price
            if plan.weight is not None:
                stop, qty = math.nan, min(eq * plan.weight[sym][i] / price, eq * MAX_POSITION / price, room)
            else:
                stop = (plan.stop_long if side > 0 else plan.stop_short)[sym][i]
                dist = (price - stop) * side
                if math.isnan(stop) or dist <= 0:
                    continue
                qty = min(eq * RISK / dist, eq * MAX_POSITION / price, room)
            if qty * price < tw.MIN_NOTIONAL.get(sym, tw.DEFAULT_MIN_NOTIONAL):
                sim.skipped += 1
                continue
            fee_in = qty * price * FEE
            cash -= fee_in
            pos[sym] = _Pos(side, qty, price, stop, fee_in, t)
        # 3. during the hour: funding, then stops (a gap through the stop fills at the open)
        for sym in list(pos):
            p = pos[sym]
            if math.isnan(c[sym][i]):
                continue
            p.funding += p.qty * c[sym][i] * m.funding[sym][i] / 8 * p.side  # longs pay a positive rate
            if math.isnan(p.stop):
                continue
            if p.side > 0 and low[sym][i] <= p.stop:
                close(sym, min(o[sym][i], p.stop), "stop", t)
            elif p.side < 0 and h[sym][i] >= p.stop:
                close(sym, max(o[sym][i], p.stop), "stop", t)
        # 4. mark to market at the close
        for s in syms:
            if not math.isnan(c[s][i]):
                last[s] = c[s][i]
        unreal, gross_n = 0.0, 0.0
        for sym, p in pos.items():
            mark = p.entry if math.isnan(last[sym]) else last[sym]
            unreal += (mark - p.entry) * p.qty * p.side - p.funding
            gross_n += mark * p.qty
        eq = cash + unreal
        sim.equity[i] = eq
        sim.exposure[i] = gross_n / eq if eq > 0 else 0.0
    t_end = m.times[-1]
    for sym in list(pos):
        close(sym, last[sym] if not math.isnan(last[sym]) else pos[sym].entry, "fin del periodo", t_end)
    if n:
        sim.equity[-1] = cash
    return sim


# ---------------------------------------------------------------------------
# Walk-forward
# ---------------------------------------------------------------------------

def daily(times: pd.DatetimeIndex, values: np.ndarray) -> pd.Series:
    return pd.Series(values, index=times).dropna().resample("1D").last().ffill()


def returns(equity: pd.Series, capital: float = CAPITAL) -> pd.Series:
    return equity / equity.shift(1).fillna(capital) - 1


def path_stats(r: pd.Series) -> tuple[float, float]:
    """(net %, max drawdown %) of a daily-return path."""
    if r.empty:
        return 0.0, 0.0
    eq = np.r_[1.0, np.cumprod(1 + r.to_numpy())]
    peak = np.maximum.accumulate(eq)
    return float((eq[-1] - 1) * 100), float(((peak - eq) / peak).max() * 100)


def net_dd(net: float, dd: float) -> Optional[float]:
    return round(net / dd, 2) if dd > 0 else None


def fit_score(r: pd.Series) -> float:
    net, dd = path_stats(r)
    return net / max(dd, 1.0) if net > 0 else net


def windows(test_start: pd.Timestamp, end: pd.Timestamp) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    out, ws = [], test_start
    while ws < end:
        out.append((ws, min(ws + pd.Timedelta(days=TEST_DAYS), end)))
        ws += pd.Timedelta(days=TEST_DAYS)
    return out


@dataclass
class Combo:
    params: dict
    r: pd.Series  # daily returns
    exposure: pd.Series  # daily, at the day's close
    equity: pd.Series  # daily
    trades: list[dict]


def run_combo(m: Market, family: str, params: dict, lo: int, regime_filter: bool) -> Combo:
    sim = simulate(m, make_plan(m, family, params), lo, regime_filter)
    eq = daily(m.times, sim.equity)
    return Combo(params, returns(eq), daily(m.times, np.where(np.isnan(sim.equity), np.nan, sim.exposure)), eq,
                 sim.trades)


def walk_forward(combos: list[Combo], wins: list[tuple[pd.Timestamp, pd.Timestamp]]) -> dict:
    """Pick per test window the combination with the best net/drawdown on the previous FIT_DAYS."""
    parts, trades, chosen, cost_total = [], [], [], 0.0
    prev: Optional[int] = None
    stitched = CAPITAL
    for ws, we in wins:
        fit_days = pd.date_range(ws - pd.Timedelta(days=FIT_DAYS), ws - DAY, freq="1D", tz="UTC")
        scores = [fit_score(cb.r.reindex(fit_days).dropna()) for cb in combos]
        k = int(np.argmax(scores))
        cb = combos[k]
        days = pd.date_range(ws, we - DAY, freq="1D", tz="UTC")
        r = cb.r.reindex(days).fillna(0.0).copy()
        before = ws - DAY
        if k != prev:  # adopting another book: trade out of the old one and into the new one
            swap = float(cb.exposure.get(before, 0.0) or 0.0)
            if prev is not None:
                swap += float(combos[prev].exposure.get(before, 0.0) or 0.0)
            cost = swap * (FEE + SLIP)
            if len(r):
                r.iloc[0] -= cost
            cost_total += cost * stitched
        scale = stitched / float(cb.equity.get(before, CAPITAL))
        for t in cb.trades:
            if ws <= pd.Timestamp(t["exit_at"]) < we:
                trades.append({**t, "pnl": t["pnl"] * scale, "fees": t["fees"] * scale,
                               "funding": t["funding"] * scale})
        stitched *= float(np.prod(1 + r.to_numpy()))
        parts.append(r)
        chosen.append({"desde": ws.date().isoformat(), "hasta": we.date().isoformat(), "parametros": cb.params,
                       "ajuste_puntaje": round(scores[k], 3)})
        prev = k
    r_all = pd.concat(parts) if parts else pd.Series(dtype=float)
    return {"r": r_all, "trades": trades, "chosen": chosen, "switch_cost": cost_total}


def trade_stats(trades: list[dict]) -> dict:
    pnl = [t["pnl"] for t in trades]
    wins, losses = [p for p in pnl if p > 0], [p for p in pnl if p <= 0]
    return {"operaciones": len(pnl), "acierto_pct": round(len(wins) / len(pnl) * 100, 1) if pnl else 0.0,
            "ganancia_media_usdt": round(float(np.mean(wins)), 2) if wins else 0.0,
            "perdida_media_usdt": round(float(np.mean(losses)), 2) if losses else 0.0,
            "comisiones_usdt": round(sum(t.get("fees", 0.0) for t in trades), 2),
            "financiacion_usdt": round(sum(t.get("funding", 0.0) for t in trades), 2),
            "compras": sum(1 for t in trades if t["side"] == "BUY"),
            "ventas": sum(1 for t in trades if t["side"] == "SELL")}


def quarter(ts: pd.Timestamp) -> str:
    return f"{ts.year}-T{(ts.month - 1) // 3 + 1}"


def by_quarter(r: pd.Series, trades: Optional[list[dict]] = None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if r.empty:
        return out
    for q, part in r.groupby([quarter(t) for t in r.index]):
        net, dd = path_stats(part)
        row: dict = {"neto_pct": round(net, 2), "max_caida_pct": round(dd, 2), "dias": len(part)}
        if trades is not None:
            row["operaciones"] = sum(1 for t in trades if quarter(pd.Timestamp(t["exit_at"])) == q)
        out[str(q)] = row
    return out


def corr(a: pd.Series, b: Optional[pd.Series]) -> Optional[float]:
    if b is None or a.empty or b.empty:
        return None
    x, y = a.align(b, join="inner")
    if len(x) < 10 or x.std() == 0 or y.std() == 0:
        return None
    return round(float(np.corrcoef(x, y)[0, 1]), 3)


def summarize(r: pd.Series, trades: list[dict], desk_r: Optional[pd.Series] = None, extra_fees: float = 0.0) -> dict:
    net, dd = path_stats(r)
    st = trade_stats(trades)
    st["comisiones_usdt"] = round(st["comisiones_usdt"] + extra_fees, 2)
    quarters = by_quarter(r, trades)
    return {"neto_pct": round(net, 2), "max_caida_pct": round(dd, 2), "neto_caida": net_dd(net, dd), **st,
            "correlacion_mesa": corr(r, desk_r), "trimestres": quarters,
            "trimestres_positivos": sum(1 for q in quarters.values() if q["neto_pct"] > 0)}


def verdict(s: dict, desk: Optional[dict]) -> str:
    desk_ratio = desk.get("neto_caida") if desk else None
    n_q = len(s["trimestres"])
    need_q = max(1, math.ceil(n_q * 0.75))
    if s["operaciones"] < MIN_OOS_TRADES:
        tag = f"muestra corta ({s['operaciones']} operaciones < {MIN_OOS_TRADES})"
        return tag if s["neto_pct"] <= 0 else tag + ", positiva"
    if s["neto_pct"] <= 0:
        return "pierde fuera de muestra"
    beats = desk_ratio is None or (s["neto_caida"] is not None and s["neto_caida"] > desk_ratio)
    steady = s["trimestres_positivos"] >= need_q
    if beats and steady and desk_ratio is not None:
        return "GANA a la mesa (neto/caída) y es estable por trimestres"
    if beats and steady:
        return "positiva y estable (sin mesa para comparar)"
    low_corr = s["correlacion_mesa"] is not None and abs(s["correlacion_mesa"]) < 0.3
    if low_corr:
        return "gana algo, no supera a la mesa, pero no se parece a ella (podría sumar)"
    return "positiva, pero no supera a la mesa o no es estable por trimestres"


# ---------------------------------------------------------------------------
# Benchmarks on the same windows: the desk (mesa_r3) and BTC buy-and-hold
# ---------------------------------------------------------------------------

Extras = Callable[[str, datetime, datetime], tuple[pd.Series, pd.Series]]


def _public_extras(sym: str, a: datetime, b: datetime) -> tuple[pd.Series, pd.Series]:
    return tw.fetch_top_traders(sym, a, b), tw.fetch_funding(sym, a, b)


def desk_window(ws: pd.Timestamp, we: pd.Timestamp, symbols: list[str], fetcher: tw.Fetcher = tw.fetch,
                extras: Extras = _public_extras) -> dict:
    """mesa_r3 on 5-minute bars over one test window, starting at CAPITAL (a fresh session)."""
    start, end = ws.to_pydatetime(), we.to_pydatetime()
    warm = start - timedelta(minutes=5 * tw.WARMUP)
    prepared = {}
    data: dict[str, dict] = {}
    for sym in symbols:
        try:
            m5 = fetcher(sym, "5m", warm, end)
            h1 = fetcher(sym, "1h", warm - timedelta(hours=tw.SLOW + 5), end)
        except Exception:  # noqa: BLE001 - one symbol's data must not stop the others
            continue
        top, fund = extras(sym, warm, end)
        prepared[sym] = tw.prepare(m5, h1, tw.WARMUP, top, fund)
        # how much of the window has the top traders' ratio (the desk's base signal uses it)
        covered = sum(1 for x in prepared[sym].top_ratio[tw.WARMUP:] if x is not None)
        data[sym] = {"velas_5m": len(m5), "top_puntos": len(top), "financiacion_puntos": len(fund),
                     "velas_con_top_pct": round(covered / max(1, len(m5) - tw.WARMUP) * 100, 1)}
    if not prepared:
        return {"equity": {}, "trades": [], "datos": data}
    res = tw.simulate(prepared, DESK, CAPITAL)
    times = sorted(set().union(*[set(p.bars.index) for p in prepared.values()]))
    curve = pd.Series(res.equity_curve, index=pd.DatetimeIndex(times[:len(res.equity_curve)]))
    days = pd.date_range(ws, we - DAY, freq="1D", tz="UTC")
    eq = curve[curve.index >= ws].resample("1D").last().reindex(days).ffill()
    final = CAPITAL + sum(t["pnl"] for t in res.trades)
    eq = eq.fillna(CAPITAL)
    if len(eq):
        eq.iloc[-1] = final  # every position is closed at the end of the window
    trades = [{"symbol": t["symbol"], "side": t["side"], "exit_at": t["at"], "pnl": t["pnl"], "fees": t["fees"],
               "funding": t["funding"]} for t in res.trades]
    return {"equity": {d.isoformat(): float(v) for d, v in eq.items()}, "trades": trades, "final": res.end,
            "datos": data, "sin_minimo": res.skipped_minimum, "vetos": res.vetoes}


def _desk_job(job: tuple) -> dict:
    ws, we, symbols = job
    return desk_window(ws, we, symbols)


def desk_benchmark(wins: list[tuple[pd.Timestamp, pd.Timestamp]], symbols: list[str], workers: int = 1,
                   fetcher: tw.Fetcher = tw.fetch,
                   extras: Extras = _public_extras) -> tuple[pd.Series, list[dict], list[dict]]:
    jobs = [(ws, we, symbols) for ws, we in wins]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_desk_job, jobs))
    else:
        results = [desk_window(ws, we, symbols, fetcher, extras) for ws, we, _ in jobs]
    parts, trades, stitched = [], [], CAPITAL
    checks = [{"desde": ws.date().isoformat(), "operaciones": len(res["trades"]), "final": res.get("final"),
               "sin_minimo": res.get("sin_minimo"), "vetos": res.get("vetos"), "datos": res.get("datos", {})}
              for (ws, _), res in zip(wins, results)]
    for res in results:
        eq = pd.Series({pd.Timestamp(k): v for k, v in res["equity"].items()}, dtype=float)
        if eq.empty:
            continue
        r = returns(eq)
        scale = stitched / CAPITAL
        trades += [{**t, "pnl": t["pnl"] * scale, "fees": t["fees"] * scale, "funding": t["funding"] * scale}
                   for t in res["trades"]]
        stitched *= float(np.prod(1 + r.to_numpy()))
        parts.append(r)
    return (pd.concat(parts) if parts else pd.Series(dtype=float)), trades, checks


def btc_hold(m: Market, wins: list[tuple[pd.Timestamp, pd.Timestamp]]) -> pd.Series:
    if "BTCUSDT" not in m.bars or not wins:
        return pd.Series(dtype=float)
    close = m.bars["BTCUSDT"]["close"].dropna().resample("1D").last().ffill()
    r = close.pct_change()
    days = pd.date_range(wins[0][0], wins[-1][1] - DAY, freq="1D", tz="UTC")
    return r.reindex(days).fillna(0.0)


# ---------------------------------------------------------------------------
# Study and report
# ---------------------------------------------------------------------------

def study(m: Market, oos_days: int, desk_r: Optional[pd.Series] = None, desk_trades: Optional[list[dict]] = None,
          families: Optional[list[str]] = None) -> dict:
    end = m.times[-1] + pd.Timedelta(hours=1)
    test_start = end - pd.Timedelta(days=oos_days)
    fit_start = test_start - pd.Timedelta(days=FIT_DAYS)
    lo = int(m.times.searchsorted(fit_start))
    wins = windows(test_start, end)
    out: dict = {"ventanas": [(a.date().isoformat(), b.date().isoformat()) for a, b in wins], "familias": {},
                 "fijas": {}}
    desk = summarize(desk_r, desk_trades or []) if desk_r is not None and not desk_r.empty else None
    out["mesa"] = desk
    btc_r = btc_hold(m, wins)
    out["btc"] = summarize(btc_r, [], desk_r) if not btc_r.empty else None
    oos_days_idx = pd.date_range(test_start, end - DAY, freq="1D", tz="UTC")
    for family in families or list(GRIDS):
        for filt in (False, True):
            name = family + ("_filtro" if filt else "")
            combos = [run_combo(m, family, p, lo, filt) for p in GRIDS[family]]
            wf = walk_forward(combos, wins)
            s = summarize(wf["r"], wf["trades"], desk_r, wf["switch_cost"])
            s["costo_cambios_usdt"] = round(wf["switch_cost"], 2)
            s["veredicto"] = verdict(s, desk)
            s["elegidas"] = wf["chosen"]
            out["familias"][name] = s
            fixed = []
            for cb in combos:  # every combination over the whole test span (hindsight: does not count)
                r = cb.r.reindex(oos_days_idx).fillna(0.0)
                net, dd = path_stats(r)
                ops = sum(1 for t in cb.trades if pd.Timestamp(t["exit_at"]) >= test_start)
                fixed.append({"parametros": cb.params, "neto_pct": round(net, 2), "max_caida_pct": round(dd, 2),
                              "neto_caida": net_dd(net, dd), "operaciones": ops})
            out["fijas"][name] = fixed
            print(f"{name}: neto {s['neto_pct']:+.2f}%, caída {s['max_caida_pct']}%, {s['operaciones']} ops — "
                  f"{s['veredicto']}")
    return out


PREREGISTERED: dict[str, tuple[str, dict]] = {  # docs/research/tendencia/PREREGISTRO.md (2026-10-12): never re-fit
    "ema_1d_20_50_atr3": ("ema", {"tf": "1d", "rapida": 20, "lenta": 50, "atr": 3}),
    "tsmom_60d": ("tsmom", {"dias": 60, "vol": 20, "mantener": 3}),
}


def prereg_verdict(s: dict, desk: Optional[dict]) -> str:
    need_q = max(1, math.ceil(len(s["trimestres"]) * 0.75))
    desk_ratio = desk.get("neto_caida") if desk else None
    checks = {"neto positivo": s["neto_pct"] > 0,
              "neto/caída mejor que la mesa": desk_ratio is None or (
                  s["neto_caida"] is not None and s["neto_caida"] > desk_ratio),
              f"positiva en {need_q}+ trimestres": s["trimestres_positivos"] >= need_q}
    failed = [k for k, ok in checks.items() if not ok]
    if failed:
        return "NO se sostiene: falla " + ", ".join(failed)
    if s["operaciones"] < MIN_OOS_TRADES:
        return f"muestra corta, favorable ({s['operaciones']} operaciones < {MIN_OOS_TRADES})"
    return "SE SOSTIENE en el año que no se usó para elegirla" + ("" if desk_ratio is not None else " (sin mesa)")


def preregistered(m: Market, days: int, desk_r: Optional[pd.Series] = None,
                  desk_trades: Optional[list[dict]] = None) -> dict:
    """The pre-registered fixed rules over the last `days` days: start with CAPITAL, never re-fit."""
    end = m.times[-1] + pd.Timedelta(hours=1)
    test_start = end - pd.Timedelta(days=days)
    lo = int(m.times.searchsorted(test_start))
    wins = windows(test_start, end)
    test_days = pd.date_range(test_start, end - DAY, freq="1D", tz="UTC")
    desk = summarize(desk_r, desk_trades or []) if desk_r is not None and not desk_r.empty else None
    btc_r = btc_hold(m, wins)
    out: dict = {"ventanas": [(a.date().isoformat(), b.date().isoformat()) for a, b in wins], "mesa": desk,
                 "btc": summarize(btc_r, [], desk_r) if not btc_r.empty else None, "reglas": {}}
    for name, (family, params) in PREREGISTERED.items():
        cb = run_combo(m, family, params, lo, False)
        r = cb.r.reindex(test_days).fillna(0.0)
        s = summarize(r, cb.trades, desk_r)
        s["parametros"] = params
        s["veredicto"] = prereg_verdict(s, desk)
        out["reglas"][name] = s
        print(f"{name}: neto {s['neto_pct']:+.2f}%, caída {s['max_caida_pct']}%, {s['operaciones']} ops — "
              f"{s['veredicto']}")
    return out


def render_prereg(res: dict, meta: dict) -> str:
    desk, btc = res.get("mesa"), res.get("btc")
    lines = [f"# Preregistro: dos reglas de tendencia fijas en un año no usado ({meta['prueba_desde']} a "
             f"{meta['hasta']})", "",
             "Reglas escritas el 2026-10-12 en `PREREGISTRO.md`, elegidas en retrospectiva sobre 2025-10-12 a "
             "2026-10-12 y probadas aquí sin cambiar nada en el año anterior. Parámetros fijos, nunca reajustados; "
             "empiezan con 1.000 USDT. Mismos costes y tamaños que el estudio de tendencia. La mesa (mesa_r3) y comprar "
             "y mantener BTC se miden en las mismas ventanas de 30 días.", "",
             "| Estrategia | Operaciones | Neto % | Máx. caída | Neto/caída | Acierto | Ganancia media | Pérdida media | "
             "Comisiones | Financiación | Correlación con la mesa | Trimestres positivos | Veredicto |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]

    def row(name: str, s: dict, v: str) -> str:
        return (f"| {name} | {s['operaciones']} | {s['neto_pct']:+.2f}% | {s['max_caida_pct']}% | "
                f"{_fmt(s['neto_caida'])} | {s['acierto_pct']}% | {s['ganancia_media_usdt']:+.2f} | "
                f"{s['perdida_media_usdt']:+.2f} | {s['comisiones_usdt']:.2f} | {s['financiacion_usdt']:+.2f} | "
                f"{_fmt(s['correlacion_mesa'])} | {s['trimestres_positivos']} de {len(s['trimestres'])} | {v} |")

    if desk:
        lines.append(row("**mesa_r3 (la mesa en vivo)**", desk, "referencia"))
    if btc:
        lines.append(f"| BTC comprar y mantener | — | {btc['neto_pct']:+.2f}% | {btc['max_caida_pct']}% | "
                     f"{_fmt(btc['neto_caida'])} | — | — | — | — | — | {_fmt(btc['correlacion_mesa'])} | "
                     f"{btc['trimestres_positivos']} de {len(btc['trimestres'])} | referencia |")
    for name, s in res["reglas"].items():
        lines.append(row(name, s, s["veredicto"]))
    rows = [("mesa_r3", desk), ("BTC", btc), *res["reglas"].items()]
    quarters = sorted({q for _, s in rows if s for q in s["trimestres"]})
    lines += ["", "## Por trimestre (neto %)", "", "| Estrategia | " + " | ".join(quarters) + " |",
              "|---|" + "---|" * len(quarters)]
    for name, s in rows:
        if s:
            lines.append(f"| {name} | " + " | ".join(
                "—" if q not in s["trimestres"] else f"{s['trimestres'][q]['neto_pct']:+.2f}%" for q in quarters) + " |")
    lines += ["", "Advertencias: el precio Spot aproxima al perpetuo; un año más de historia no garantiza el futuro."]
    return "\n".join(lines) + "\n"


def render_desk_checks(checks: list[dict]) -> str:
    """How much top-trader data the desk replay had, window by window (its base signal uses it)."""
    if not checks:
        return ""
    lines = ["", "## Datos de la mesa por ventana (control)", "",
             "| Ventana | Operaciones | Sin mínimo | Vetos (evitó pérdida / dejó pasar ganancia) | Final | "
             "Velas con top traders (mín. / media por moneda) |", "|---|---|---|---|---|---|"]
    for c in checks:
        pct = [d["velas_con_top_pct"] for d in c["datos"].values()]
        v = c.get("vetos") or {}
        cov = f"{min(pct)}% / {round(sum(pct) / len(pct), 1)}%" if pct else "—"
        lines.append(f"| {c['desde']} | {c['operaciones']} | {c.get('sin_minimo')} | "
                     f"{v.get('evitó pérdida', '—')} / {v.get('dejó pasar ganancia', '—')} | {c.get('final')} | {cov} |")
    return "\n".join(lines) + "\n"


def _fmt(x: Optional[float]) -> str:
    return "—" if x is None else f"{x}"


def render(res: dict, meta: dict) -> str:
    desk, btc = res.get("mesa"), res.get("btc")
    fams = res["familias"]
    lines = [f"# Seguir la tendencia en futuros (largos y cortos), fuera de muestra ({meta['prueba_desde']} a "
             f"{meta['hasta']})", "",
             "Investigación con datos públicos de Binance (sin cuenta, sin claves, sin órdenes). Monedas: "
             f"{', '.join(meta['simbolos'])}. Velas de 1 hora (precio Spot como aproximación del perpetuo).", "",
             "**Cómo se midió.** Cada combinación de parámetros corre todo el periodo. Cada 30 días, cada familia elige "
             "la combinación con mejor neto/caída en los 90 días anteriores y la usa los 30 siguientes; solo cuentan "
             f"esos 30 días ({len(res['ventanas'])} ventanas). Capital 1.000 USDT, 1x, posición máx. 50%, 3 posiciones, "
             "riesgo 5% al stop (familias con stop) o tamaño por volatilidad (tsmom). Comisión 0,05% y deslizamiento "
             "0,02% por lado, financiación real cada 8 h. Un stop que se salta con hueco se llena en la apertura. "
             "La mesa (mesa_r3, velas de 5 min, empieza cada ventana con 1.000 USDT como una sesión) y comprar y "
             "mantener BTC se miden en las mismas ventanas. Caída máxima medida con el cierre de cada día.", "",
             "## Resultado fuera de muestra", "",
             "| Estrategia | Operaciones | Neto % | Máx. caída | Neto/caída | Acierto | Ganancia media | Pérdida media | "
             "Comisiones | Financiación | Correlación con la mesa | Trimestres positivos | Veredicto |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]

    def row(name: str, s: dict, v: str) -> str:
        return (f"| {name} | {s['operaciones']} | {s['neto_pct']:+.2f}% | {s['max_caida_pct']}% | "
                f"{_fmt(s['neto_caida'])} | {s['acierto_pct']}% | {s['ganancia_media_usdt']:+.2f} | "
                f"{s['perdida_media_usdt']:+.2f} | {s['comisiones_usdt']:.2f} | {s['financiacion_usdt']:+.2f} | "
                f"{_fmt(s['correlacion_mesa'])} | {s['trimestres_positivos']} de {len(s['trimestres'])} | {v} |")

    if desk:
        lines.append(row("**mesa_r3 (la mesa en vivo)**", desk, "referencia"))
    else:
        lines.append("| mesa_r3 | — | — | — | — | — | — | — | — | — | — | — | no se midió en esta corrida |")
    if btc:
        lines.append(f"| BTC comprar y mantener | — | {btc['neto_pct']:+.2f}% | {btc['max_caida_pct']}% | "
                     f"{_fmt(btc['neto_caida'])} | — | — | — | — | — | {_fmt(btc['correlacion_mesa'])} | "
                     f"{btc['trimestres_positivos']} de {len(btc['trimestres'])} | referencia |")
    for name, s in fams.items():
        lines.append(row(name, s, s["veredicto"]))
    quarters = sorted({q for s in [desk, btc, *fams.values()] if s for q in s["trimestres"]})
    lines += ["", "## Por trimestre (neto %, fuera de muestra)", "",
              "| Estrategia | " + " | ".join(quarters) + " |", "|---|" + "---|" * len(quarters)]
    for name, s in [("mesa_r3", desk), ("BTC", btc), *fams.items()]:
        if not s:
            continue
        cells = []
        for q in quarters:
            v = s["trimestres"].get(q)
            cells.append("—" if v is None else f"{v['neto_pct']:+.2f}%"
                         + (f" ({v['operaciones']} ops)" if "operaciones" in v and name != "BTC" else ""))
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += ["", "## Combinaciones fijas en todo el periodo de prueba (en retrospectiva: NO cuenta, solo muestra "
              "si la idea es robusta o depende de un parámetro)", ""]
    for name, rows in res["fijas"].items():
        if name.endswith("_filtro"):
            continue
        pos = sum(1 for r in rows if r["neto_pct"] > 0)
        best = max(rows, key=lambda r: r["neto_caida"] if r["neto_caida"] is not None else -1e9)
        worst = min(rows, key=lambda r: r["neto_pct"])
        med = float(np.median([r["neto_pct"] for r in rows]))
        lines.append(f"- **{name}**: {pos} de {len(rows)} combinaciones ganan; mediana {med:+.2f}%; mejor "
                     f"{best['parametros']} {best['neto_pct']:+.2f}% (caída {best['max_caida_pct']}%, "
                     f"{best['operaciones']} ops); peor {worst['parametros']} {worst['neto_pct']:+.2f}%.")
    lines += ["", "## Veredicto", ""]
    winners = [n for n, s in fams.items() if s["veredicto"].startswith("GANA")]
    valid = [n for n, s in fams.items() if s["operaciones"] >= MIN_OOS_TRADES]
    best_name = max(valid or fams, key=lambda n: (fams[n]["neto_caida"] or -1e9)) if fams else None
    if winners:
        w = max(winners, key=lambda n: fams[n]["neto_caida"] or 0)
        s = fams[w]
        lines.append(f"**{w}** gana a la mesa fuera de muestra: neto {s['neto_pct']:+.2f}% con caída máxima "
                     f"{s['max_caida_pct']}% (neto/caída {s['neto_caida']} contra {_fmt(desk and desk['neto_caida'])} "
                     f"de la mesa), {s['operaciones']} operaciones, positiva en {s['trimestres_positivos']} de "
                     f"{len(s['trimestres'])} trimestres. Correlación diaria con la mesa: {_fmt(s['correlacion_mesa'])}. "
                     "Merece un bot de práctica (dinero ficticio) antes de cualquier otra cosa.")
    elif best_name:
        s = fams[best_name]
        lines.append("**Ninguna estrategia de tendencia gana a la mesa** con las reglas del protocolo. "
                     f"La mejor fue **{best_name}**: neto {s['neto_pct']:+.2f}%, caída {s['max_caida_pct']}%, "
                     f"neto/caída {_fmt(s['neto_caida'])} (mesa: {_fmt(desk and desk['neto_caida'])}), "
                     f"{s['operaciones']} operaciones, {s['trimestres_positivos']} de {len(s['trimestres'])} trimestres "
                     f"positivos. Veredicto: {s['veredicto']}.")
    lines += ["", "Advertencias: el precio Spot aproxima al perpetuo; un año es una sola historia de mercado; la "
              "mesa se mide con sus propias reglas de sesión (límite de pérdida y meta) reiniciadas cada 30 días; "
              "elegir parámetros con el pasado (walk-forward) es honesto pero no garantiza el futuro."]
    return "\n".join(lines) + "\n"


def _jsonable(res: dict) -> dict:
    return json.loads(json.dumps(res, default=str))


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Investigación: seguir la tendencia en futuros")
    parser.add_argument("--dias", type=int, default=365, help="días fuera de muestra (más 90 de ajuste)")
    parser.add_argument("--simbolos", nargs="+", default=list(tw.SYMBOLS))
    parser.add_argument("--sin-mesa", action="store_true", help="no medir mesa_r3 (mucho más rápido)")
    parser.add_argument("--procesos", type=int, default=4, help="procesos para medir la mesa")
    parser.add_argument("--hasta", type=str, default=None, help="fin del periodo, AAAA-MM-DD (por defecto hoy)")
    parser.add_argument("--preregistro", action="store_true",
                        help="solo las reglas fijas de PREREGISTRO.md, sin walk-forward")
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    if args.hasta:
        end = datetime.strptime(args.hasta, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    m = load(args.dias, end, args.simbolos)
    test_start = pd.Timestamp(end) - pd.Timedelta(days=args.dias)
    desk_r: Optional[pd.Series] = None
    desk_trades: Optional[list[dict]] = None
    checks: list[dict] = []
    if not args.sin_mesa:
        desk_r, desk_trades, checks = desk_benchmark(windows(test_start, pd.Timestamp(end)), list(m.bars),
                                                     args.procesos)
        print(f"mesa_r3: {len(desk_trades)} operaciones")
    meta = {"prueba_desde": test_start.date().isoformat(), "hasta": end.date().isoformat(),
            "simbolos": list(m.bars), "dias_fuera_de_muestra": args.dias, "ajuste_dias": FIT_DAYS,
            "prueba_dias": TEST_DAYS, "comision": FEE, "deslizamiento": SLIP, "riesgo_stop": RISK,
            "con_mesa": desk_r is not None, "preregistro": args.preregistro}
    if args.preregistro:
        res = preregistered(m, args.dias, desk_r, desk_trades)
        report = render_prereg(res, meta)
        name = "preregistro"
    else:
        res = study(m, args.dias, desk_r, desk_trades)
        report = render(res, meta)
        name = "tendencia"
    res["control_mesa"] = checks
    report += render_desk_checks(checks)
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = end.date().isoformat() + ("_sin_mesa" if args.sin_mesa else "")
    (args.salida / f"{name}_{stamp}.json").write_text(json.dumps({"meta": meta, **_jsonable(res)}, indent=1),
                                                      encoding="utf-8")
    (args.salida / f"{name}_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
