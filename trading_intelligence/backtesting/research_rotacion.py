"""
Rotation and reversion research for Binance USDⓈ-M futures (research only: public data, no key, no orders).

Leader's task, 2026-10-12 (protocol: docs/research/PROTOCOLO.md). Three families on 1-hour bars:
  rotacion:  cross-sectional momentum. At 00:00 UTC every `rebalance` days, rank the coins by their
             `lookback`-day return. largo3 = long the top 3; largo3_btc50 = the same, only while BTC
             closes above its 50-day mean (else flat); ls = long the top 1 and short the bottom 1.
             Equal weights (1/3 each, 1/2 each for ls). A coin that stays in the basket is not traded.
  reversion: short-term fades in weak trends (ADX(14) < 20 on 1h). rsi2 = RSI(2) < 10 / > 90;
             rsi4 = RSI(4) < 20 / > 80; bb2 / bb2.5 = close beyond the 20-bar Bollinger band at 2 / 2.5σ.
             Target = the 20-bar mean at the signal, stop = `stop_atr` x ATR(14), time exit after `hold` h.
  pares:     ETH/BTC and SOL/ETH, z-score of log(A/B) over `lookback` days. |z| >= z_in: short the rich
             leg, long the cheap one (25% of equity each). Exit when z crosses 0, at |z| >= z_stop, or
             after `lookback` days.
Optional (--top30): rotacion on today's top 30 Spot USDT pairs by volume (survivorship bias: they are
today's winners).

Every decision is taken at a bar's close and filled at the next bar's open. Costs: 0.05% fee and
0.02% slippage per side, real funding per hour (0.01%/8h when missing). A stop and a target in the
same bar count as the stop; a gap through the stop fills at the open. Capital 1000 USDT, 1x, at most
3 positions, a position at most 50% of equity (a pair counts as one position).

Walk-forward: fit 90 days, test the next 30, roll 30. In each fold the grid combination with the best
net/drawdown in the fit window (>= 5 trades) runs in the test window; if even the best one lost in
the fit window, the family stays flat for that test window ("no se opera"). Each test window starts
at 1000 USDT and closes everything at its end; the out-of-sample result is the sum of the windows.
Baselines on the same windows: mesa_r3 (two_way_backtest on 5-minute bars, with 0.02% slippage per
side added) and BTC buy-and-hold.

    python -m trading_intelligence.backtesting.research_rotacion --dias 365
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from multiprocessing import Pool
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd
from scipy import stats

from trading_intelligence.backtesting import two_way_backtest as tw

CAPITAL = 1000.0
FEE, SLIP = tw.FEE, 0.0002
MAX_POSITION, MAX_OPEN, LEVERAGE = tw.MAX_POSITION, tw.MAX_OPEN, tw.LEVERAGE
FIT_DAYS, TEST_DAYS, WARM_DAYS = 90, 30, 60
MIN_FIT_TRADES, MIN_OOS_TRADES = 5, 100
HOUR = pd.Timedelta(hours=1)
PAIRS = (("ETHUSDT", "BTCUSDT"), ("SOLUSDT", "ETHUSDT"))
ADX_MAX = 20.0
REVERSION_SIGNALS = {"rsi2": (2, 10.0), "rsi4": (4, 20.0), "bb2": (None, 2.0), "bb2.5": (None, 2.5)}
GRIDS: dict[str, list[dict]] = {
    "rotacion": [{"lookback": lb, "rebalance": rb, "mode": md}
                 for lb, rb, md in itertools.product((7, 14, 30), (1, 7), ("largo3", "largo3_btc50", "ls"))],
    "reversion": [{"signal": s, "hold": h, "stop_atr": k}
                  for s, h, k in itertools.product(REVERSION_SIGNALS, (6, 24), (1.5, 3.0))],
    "pares": [{"lookback": lb, "z_in": z, "z_stop": zs}
              for lb, z, zs in itertools.product((7, 14, 30), (2.0, 2.5), (3.5, None))],
}
DESK_BASELINE = "mesa_r3"
OUT_DIR = Path("docs/research/rotacion")


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------

@dataclass
class Market:
    times: pd.DatetimeIndex  # hourly open times
    open: pd.DataFrame  # times x symbols, NaN where missing
    high: pd.DataFrame
    low: pd.DataFrame
    close: pd.DataFrame
    funding: pd.DataFrame  # fraction per 8 h in force at each bar

    @property
    def symbols(self) -> list[str]:
        return list(self.close.columns)


def _funding_at(series: Optional[pd.Series], times: pd.DatetimeIndex) -> np.ndarray:
    out = np.full(len(times), tw.FUNDING_PER_8H)
    if series is None or series.empty:
        return out
    s = series.sort_index()
    j = np.searchsorted(s.index.values, times.values, side="right") - 1
    ok = j >= 0
    out[ok] = s.values[j[ok]] / 100  # % -> fraction
    return out


def build_market(bars: dict[str, pd.DataFrame], funding: dict[str, pd.Series], times: pd.DatetimeIndex) -> Market:
    cols = {k: pd.DataFrame({s: b[k].reindex(times) for s, b in bars.items()}, index=times)
            for k in ("open", "high", "low", "close")}
    fr = pd.DataFrame({s: _funding_at(funding.get(s), times) for s in bars}, index=times)
    return Market(times, cols["open"], cols["high"], cols["low"], cols["close"], fr)


# ---------------------------------------------------------------------------
# Indicators (Wilder)
# ---------------------------------------------------------------------------

def _wilder(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int) -> pd.Series:
    d = close.diff()
    up, dn = _wilder(d.clip(lower=0), n), _wilder(-d.clip(upper=0), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 100 - 100 / (1 + up / dn)
    return out.where(dn > 0, 100.0).where(up.notna())


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return _wilder(tr, n)


def adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    up, dn = high.diff(), -low.diff()
    plus = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=high.index)
    minus = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=high.index)
    a = atr(high, low, close, n)
    pdi, mdi = 100 * _wilder(plus, n) / a, 100 * _wilder(minus, n) / a
    total = pdi + mdi
    dx = (100 * (pdi - mdi).abs() / total.where(total > 0)).where(total.isna() | (total > 0), 0.0)
    return _wilder(dx, n)  # NaN until both averages have warmed up


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

Leg = tuple[str, str, float]  # symbol, side, weight (fraction of equity)


@dataclass(frozen=True)
class Signal:
    i: int  # entry at this bar's open
    key: str  # one open position per key
    legs: tuple[Leg, ...]
    exit_i: int  # planned exit at this bar's open (decided at the previous close)
    exit_why: str = "tiempo"
    stop: Optional[float] = None  # single-leg positions only
    target: Optional[float] = None
    priority: float = 0.0  # higher first when several compete for a slot


def rebalance_bars(m: Market, lo: int, hi: int, every: int) -> list[int]:
    out = []
    for i in range(max(lo, 1), hi):
        t = m.times[i]
        if t.hour == 0 and (t.normalize() - pd.Timestamp("1970-01-01", tz="UTC")).days % every == 0:
            out.append(i)
    return out


def btc_above_mean(m: Market, days: int = 50) -> pd.Series:
    """Per hourly bar: did BTC's last DAILY close (before this bar's day) sit above its `days`-day mean?"""
    if "BTCUSDT" not in m.close:
        return pd.Series(True, index=m.times)
    daily = m.close["BTCUSDT"].resample("1D").last()
    ok = (daily > daily.rolling(days).mean()).shift(1)  # yesterday's close vs yesterday's mean
    return ok.reindex(m.times.normalize()).fillna(False).astype(bool).set_axis(m.times)


def rotation_signals(m: Market, lo: int, hi: int, lookback: int, rebalance: int, mode: str,
                     _btc: Optional[pd.Series] = None, eligible: Optional[np.ndarray] = None) -> list[Signal]:
    """`eligible` (bars x symbols, bool): only those coins are ranked at that bar (a point-in-time universe)."""
    ret = (m.close / m.close.shift(lookback * 24) - 1).values
    btc_ok = (_btc if _btc is not None else btc_above_mean(m)).values
    syms = m.symbols
    weight = 0.5 if mode == "ls" else 1 / 3
    held: dict[str, tuple[str, int]] = {}  # symbol -> (side, entry bar)
    out: list[Signal] = []

    def close(sym: str, i: int) -> None:
        side, start = held.pop(sym)
        out.append(Signal(start, sym, ((sym, side, weight),), i, "rebalanceo"))

    for i in rebalance_bars(m, lo, hi, rebalance):
        r = ret[i - 1] if eligible is None else np.where(eligible[i], ret[i - 1], np.nan)
        ranked = [syms[j] for j in np.argsort(-np.nan_to_num(r, nan=-np.inf)) if not math.isnan(r[j])]
        basket: dict[str, str] = {}
        if len(ranked) >= 4:
            if mode == "ls":
                basket = {ranked[0]: "BUY", ranked[-1]: "SELL"}
            elif mode == "largo3" or (mode == "largo3_btc50" and btc_ok[i]):
                basket = {s: "BUY" for s in ranked[:3]}
        for sym in [s for s, (side, _) in held.items() if basket.get(s) != side]:
            close(sym, i)
        for sym, side in basket.items():
            if sym not in held:
                held[sym] = (side, i)
    for sym in list(held):
        close(sym, hi)  # the window's end closes it
    return out


_IND_CACHE: dict[tuple[int, str], dict[str, np.ndarray]] = {}


def _indicators(m: Market, sym: str) -> dict[str, np.ndarray]:
    key = (id(m), sym)
    if key not in _IND_CACHE:
        f = pd.DataFrame({"h": m.high[sym], "l": m.low[sym], "c": m.close[sym]}).dropna()
        mid, sd = f["c"].rolling(20).mean(), f["c"].rolling(20).std()
        ind = {"rsi2": rsi(f["c"], 2), "rsi4": rsi(f["c"], 4), "mid": mid, "z": (f["c"] - mid) / sd,
               "adx": adx(f["h"], f["l"], f["c"]), "atr": atr(f["h"], f["l"], f["c"]), "c": f["c"]}
        _IND_CACHE[key] = {k: v.reindex(m.times).to_numpy(dtype=float) for k, v in ind.items()}
    return _IND_CACHE[key]


def reversion_signals(m: Market, signal: str, hold: int, stop_atr: float) -> list[Signal]:
    n_rsi, level = REVERSION_SIGNALS[signal]
    out: list[Signal] = []
    n = len(m.times)
    for sym in m.symbols:
        ind = _indicators(m, sym)
        with np.errstate(invalid="ignore"):
            if n_rsi is not None:
                x = ind[f"rsi{n_rsi}"]
                buy, sell, strength = x < level, x > 100 - level, np.abs(x - 50)
            else:
                x = ind["z"]
                buy, sell, strength = x < -level, x > level, np.abs(x)
            calm = ind["adx"] < ADX_MAX
        for i in np.nonzero((buy | sell) & calm)[0]:
            if i + 1 >= n or math.isnan(ind["atr"][i]):
                continue
            side = "BUY" if buy[i] else "SELL"
            c, mid, a = ind["c"][i], ind["mid"][i], ind["atr"][i]
            stop = c - stop_atr * a if side == "BUY" else c + stop_atr * a
            target = mid if (side == "BUY" and mid > c) or (side == "SELL" and mid < c) else None
            out.append(Signal(int(i) + 1, sym, ((sym, side, 1 / 3),), int(i) + 1 + hold, "tiempo", stop, target,
                              float(strength[i])))
    return out


def pairs_signals(m: Market, lookback: int, z_in: float, z_stop: Optional[float]) -> list[Signal]:
    """z_stop None: no z stop (only z = 0 or time)."""
    stop_z = math.inf if z_stop is None else z_stop
    out: list[Signal] = []
    n, w = len(m.times), lookback * 24
    for a, b in PAIRS:
        if a not in m.close or b not in m.close:
            continue
        s = np.log(m.close[a]) - np.log(m.close[b])
        z = ((s - s.rolling(w, min_periods=w // 2).mean()) / s.rolling(w, min_periods=w // 2).std()).values
        i = 0
        while i < n - 1:
            zi = z[i]
            if math.isnan(zi) or abs(zi) < z_in or abs(zi) >= stop_z:
                i += 1
                continue
            sign = 1.0 if zi > 0 else -1.0
            j, why = i + 1, "tiempo"
            while j < n - 1:
                zj = z[j]
                if not math.isnan(zj):
                    if zj * sign <= 0:
                        why = "z=0"
                        break
                    if abs(zj) >= stop_z:
                        why = "stop z"
                        break
                if j - i >= w:
                    break
                j += 1
            legs = ((a, "SELL", 0.25), (b, "BUY", 0.25)) if sign > 0 else ((a, "BUY", 0.25), (b, "SELL", 0.25))
            out.append(Signal(i + 1, f"{a[:-4]}/{b[:-4]}", legs, j + 1, why, priority=abs(zi)))
            i = j + 1
    return out


# ---------------------------------------------------------------------------
# Portfolio simulation
# ---------------------------------------------------------------------------

@dataclass
class _Open:
    s: Signal
    qty: list[float]
    entry: list[float]
    fee_in: float
    funding: float = 0.0


@dataclass
class Run:
    trades: list[dict] = field(default_factory=list)
    curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))  # equity at each bar's close
    skipped: int = 0


def _fill(price: float, side: str, opening: bool) -> float:
    buying = (side == "BUY") == opening
    return price * (1 + SLIP) if buying else price * (1 - SLIP)


def simulate(m: Market, signals: list[Signal], lo: int, hi: int, capital: float = CAPITAL) -> Run:
    """Entries with lo <= i < hi - 1; everything still open is closed at bar hi - 1's close."""
    col = {s: k for k, s in enumerate(m.symbols)}
    Op, Hh, L = m.open.values, m.high.values, m.low.values
    C, F = m.close.ffill().values, m.funding.values
    by_i: dict[int, list[Signal]] = {}
    for s in signals:
        if lo <= s.i < hi - 1:
            by_i.setdefault(s.i, []).append(s)
    run = Run()
    cash, equity = capital, capital
    pos: dict[str, _Open] = {}
    curve = np.empty(hi - lo)

    def close(key: str, prices: list[float], why: str, i: int) -> None:
        nonlocal cash
        p = pos.pop(key)
        gross = fee_out = 0.0
        for (sym, side, _), q, e, px in zip(p.s.legs, p.qty, p.entry, prices):
            x = _fill(px, side, opening=False)
            gross += (x - e) * q if side == "BUY" else (e - x) * q
            fee_out += x * q * FEE
        cash += gross - fee_out - p.funding
        notional = sum(q * e for q, e in zip(p.qty, p.entry))
        pnl = gross - fee_out - p.fee_in - p.funding
        sides = {leg[1] for leg in p.s.legs}
        run.trades.append({"key": key, "side": sides.pop() if len(sides) == 1 else "PAR",
                           "entry_at": m.times[p.s.i].isoformat(), "exit_at": m.times[i].isoformat(), "why": why,
                           "pnl": pnl, "fees": fee_out + p.fee_in, "funding": p.funding,
                           "ret_pct": pnl / notional * 100 if notional > 0 else 0.0})

    for i in range(lo, hi):
        for key in [k for k, p in pos.items() if p.s.exit_i <= i]:
            legs = pos[key].s.legs
            prices = [Op[i, col[sym]] if not math.isnan(Op[i, col[sym]]) else C[i - 1, col[sym]] for sym, _, _ in legs]
            close(key, prices, pos[key].s.exit_why, i)
        for s in sorted(by_i.get(i, []), key=lambda x: -x.priority):
            if s.key in pos or len(pos) >= MAX_OPEN:
                continue
            opens = [Op[i, col[sym]] for sym, _, _ in s.legs]
            if any(math.isnan(o) for o in opens):
                continue
            used = sum(q * C[i - 1, col[leg[0]]] for p in pos.values() for leg, q in zip(p.s.legs, p.qty))
            want = sum(min(w, MAX_POSITION) for _, _, w in s.legs) * equity
            room = LEVERAGE * equity - used
            scale = min(1.0, room / want) if want > 0 else 0.0
            if scale < 0.5:  # not even half the position fits within 1x
                run.skipped += 1
                continue
            fills = [_fill(o, side, opening=True) for o, (_, side, _) in zip(opens, s.legs)]
            qty = [min(w, MAX_POSITION) * equity * scale / f for f, (_, _, w) in zip(fills, s.legs)]
            fee_in = sum(f * q * FEE for f, q in zip(fills, qty))
            cash -= fee_in
            pos[s.key] = _Open(s, qty, fills, fee_in)
        for key, p in list(pos.items()):
            if p.s.stop is None and p.s.target is None:
                continue
            sym, side, _ = p.s.legs[0]
            o, h, low = Op[i, col[sym]], Hh[i, col[sym]], L[i, col[sym]]
            if math.isnan(h):
                continue
            long = side == "BUY"
            if p.s.stop is not None and (low <= p.s.stop if long else h >= p.s.stop):
                close(key, [min(p.s.stop, o) if long else max(p.s.stop, o)], "stop", i)
            elif p.s.target is not None and (h >= p.s.target if long else low <= p.s.target):
                close(key, [max(p.s.target, o) if long else min(p.s.target, o)], "meta", i)
        upnl = accrued = 0.0
        for p in pos.values():
            for (sym, side, _), q, e in zip(p.s.legs, p.qty, p.entry):
                c, sign = C[i, col[sym]], (1.0 if side == "BUY" else -1.0)
                p.funding += q * c * F[i, col[sym]] / 8 * sign  # 1 hour of the 8-hour rate; longs pay when > 0
                upnl += (c - e) * q * sign
            accrued += p.funding
        equity = cash + upnl - accrued
        curve[i - lo] = equity
    for key in list(pos):
        close(key, [C[hi - 1, col[sym]] for sym, _, _ in pos[key].s.legs], "fin de ventana", hi - 1)
    curve[-1] = cash
    run.curve = pd.Series(curve, index=m.times[lo:hi])
    return run


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def max_dd_pct(curve: pd.Series, capital: float = CAPITAL) -> float:
    """Largest fall from a peak, in % of the starting capital. The test windows are summed, not
    compounded (each starts at `capital`), so the fall is measured against that capital, not the peak."""
    if curve.empty:
        return 0.0
    v = curve.to_numpy(dtype=float)
    peak = np.maximum.accumulate(np.r_[capital, v])[1:]
    return float(max(0.0, (peak - v).max()) / capital * 100)


def net_dd(net_pct: float, dd_pct: float) -> Optional[float]:
    return round(net_pct / dd_pct, 2) if dd_pct > 0 else None


def daily_pnl(curve: pd.Series, capital: float = CAPITAL) -> pd.Series:
    if curve.empty:
        return pd.Series(dtype=float)
    d = curve.resample("1D").last().ffill()
    return d.diff().fillna(d.iloc[0] - capital)


def quarter(t: pd.Timestamp) -> str:
    return f"{t.year}-T{(t.month - 1) // 3 + 1}"


def by_quarter(daily: pd.Series) -> dict[str, float]:
    if daily.empty:
        return {}
    g = daily.groupby([quarter(t) for t in daily.index]).sum()
    return {k: round(float(v) / CAPITAL * 100, 2) for k, v in g.items()}


def metrics(trades: list[dict], curve: pd.Series) -> dict:
    pnl = [t["pnl"] for t in trades]
    wins, losses = [p for p in pnl if p > 0], [p for p in pnl if p <= 0]
    net = float(curve.iloc[-1] - CAPITAL) if not curve.empty else 0.0
    dd = max_dd_pct(curve)
    daily = daily_pnl(curve)
    p_value = float(stats.ttest_1samp(daily, 0).pvalue) if len(daily) > 2 and daily.std() > 0 else 1.0
    quarters = by_quarter(daily)
    return {"operaciones": len(pnl), "neto_usdt": round(net, 2), "neto_pct": round(net / CAPITAL * 100, 2),
            "max_caida_pct": round(dd, 2), "neto_caida": net_dd(net / CAPITAL * 100, dd),
            "acierto_pct": round(len(wins) / len(pnl) * 100, 1) if pnl else 0.0,
            "ganancia_media": round(float(np.mean(wins)), 2) if wins else 0.0,
            "perdida_media": round(float(np.mean(losses)), 2) if losses else 0.0,
            "factor_beneficio": round(sum(wins) / abs(sum(losses)), 2) if losses and sum(losses) < 0 else None,
            "comisiones_usdt": round(sum(t.get("fees", 0.0) for t in trades), 2),
            "financiacion_usdt": round(sum(t.get("funding", 0.0) for t in trades), 2),
            "p_diario": round(1.0 if math.isnan(p_value) else p_value, 4), "trimestres": quarters,
            "trimestres_positivos": f"{sum(v > 0 for v in quarters.values())}/{len(quarters)}"}


def chain(curves: list[pd.Series], capital: float = CAPITAL) -> pd.Series:
    """Windows that each start at `capital`, chained: each one's P&L is added to the ones before."""
    parts, offset = [], 0.0
    for c in curves:
        if c.empty:
            continue
        parts.append(c + offset)
        offset += float(c.iloc[-1]) - capital
    return pd.concat(parts) if parts else pd.Series(dtype=float)


# ---------------------------------------------------------------------------
# Walk-forward
# ---------------------------------------------------------------------------

Window = tuple[int, int, int]  # fit start, test start, test end (bar indices)


def windows(m: Market, days: int) -> list[Window]:
    n, out = len(m.times), []
    hi = n
    for _ in range(days // TEST_DAYS):
        lo = hi - TEST_DAYS * 24
        flo = lo - FIT_DAYS * 24
        if flo < WARM_DAYS * 24:
            break
        out.append((flo, lo, hi))
        hi = lo
    return out[::-1]


def _generator(family: str, m: Market, eligible: Optional[np.ndarray] = None
               ) -> Callable[[dict, int, int], list[Signal]]:
    if family.startswith("rotacion"):
        btc = btc_above_mean(m)
        return lambda p, lo, hi: rotation_signals(m, lo, hi, _btc=btc, eligible=eligible, **p)
    cache: dict[str, list[Signal]] = {}
    gen = reversion_signals if family == "reversion" else pairs_signals

    def get(p: dict, lo: int, hi: int) -> list[Signal]:
        key = json.dumps(p, sort_keys=True, default=str)
        if key not in cache:
            cache[key] = gen(m, **p)
        return cache[key]
    return get


def _score(s: dict) -> float:
    if s["operaciones"] < MIN_FIT_TRADES:
        return -math.inf
    return s["neto_pct"] / max(s["max_caida_pct"], 1.0)


def walk_forward(m: Market, family: str, grid: list[dict], wins: list[Window],
                 eligible: Optional[np.ndarray] = None) -> dict:
    gen = _generator(family, m, eligible)
    folds, curves, trades = [], [], []
    fixed: dict[str, list[Run]] = {json.dumps(p, default=str): [] for p in grid}
    for flo, lo, hi in wins:
        fits = []
        for p in grid:
            run = simulate(m, gen(p, flo, lo), flo, lo)
            fits.append((p, metrics(run.trades, run.curve)))
            fixed[json.dumps(p, default=str)].append(simulate(m, gen(p, lo, hi), lo, hi))
        p, fit = max(fits, key=lambda f: _score(f[1]))
        if _score(fit) == -math.inf or fit["neto_pct"] <= 0:
            curve = pd.Series(CAPITAL, index=m.times[lo:hi], dtype=float)
            folds.append({"prueba": [str(m.times[lo])[:10], str(m.times[hi - 1])[:10]], "elegida": None,
                          "ajuste_neto_pct": fit["neto_pct"], "prueba_neto_pct": 0.0, "operaciones": 0})
        else:
            run = fixed[json.dumps(p, default=str)][-1]  # the same test run as the fixed table
            curve = run.curve
            trades += run.trades
            folds.append({"prueba": [str(m.times[lo])[:10], str(m.times[hi - 1])[:10]], "elegida": p,
                          "ajuste_neto_pct": fit["neto_pct"], "ajuste_caida_pct": fit["max_caida_pct"],
                          "prueba_neto_pct": round(float(curve.iloc[-1] - CAPITAL) / CAPITAL * 100, 2),
                          "operaciones": len(run.trades)})
        curves.append(curve)
    full = chain(curves)
    fixed_summary = []
    for key, runs in fixed.items():
        c = chain([r.curve for r in runs])
        s = metrics([t for r in runs for t in r.trades], c)
        fixed_summary.append({"parametros": json.loads(key),
                              **{k: s[k] for k in ("operaciones", "neto_pct", "max_caida_pct", "neto_caida",
                                                   "trimestres_positivos")}})
    return {"oos": metrics(trades, full), "folds": folds, "fijas": fixed_summary, "curva": full}


def buy_and_hold(m: Market, wins: list[Window], symbol: str = "BTCUSDT") -> pd.Series:
    curves = []
    for _, lo, hi in wins:
        o = m.open[symbol].iloc[lo]
        entry = o * (1 + SLIP)
        qty = CAPITAL / entry / (1 + FEE)
        c = m.close[symbol].iloc[lo:hi].ffill()
        cash = CAPITAL - qty * entry * (1 + FEE)
        curve = cash + qty * c
        last = float(c.iloc[-1]) * (1 - SLIP)
        curve.iloc[-1] = cash + qty * last * (1 - FEE)
        curves.append(curve)
    return chain(curves)


# ---------------------------------------------------------------------------
# The desk (mesa_r3) on the same test windows
# ---------------------------------------------------------------------------

def _prepare_one(args: tuple) -> tuple[str, Optional[tw.Prepared]]:
    sym, m5, h1, top, funding = args
    try:
        return sym, tw.prepare(m5, h1, tw.WARMUP, top, funding)
    except Exception as error:  # noqa: BLE001 - one symbol must not stop the others
        print(f"{sym}: mesa sin preparar ({type(error).__name__}: {error})")
        return sym, None


def _slice(p: tw.Prepared, a: pd.Timestamp, b: pd.Timestamp) -> tw.Prepared:
    i, j = int(p.bars.index.searchsorted(a)), int(p.bars.index.searchsorted(b))
    return tw.Prepared(p.bars.iloc[i:j], p.readings[i:j], p.top_ratio[i:j], p.funding[i:j])


def desk_curve(prepared: dict[str, tw.Prepared], m: Market, wins: list[Window]) -> tuple[pd.Series, list[dict]]:
    """mesa_r3 replayed window by window (each from 1000 USDT), minus 0.02% slippage per side."""
    curves, trades = [], []
    for _, lo, hi in wins:
        a, b = m.times[lo], m.times[hi - 1] + HOUR
        sl = {s: _slice(p, a, b) for s, p in prepared.items()}
        sl = {s: p for s, p in sl.items() if len(p.bars)}
        res = tw.simulate(sl, DESK_BASELINE, CAPITAL)
        times = sorted(set().union(*[set(p.bars.index) for p in sl.values()]))
        curve = pd.Series(res.equity_curve, index=pd.DatetimeIndex(times[:len(res.equity_curve)]), dtype=float)
        if len(curve) < len(times):  # the session's loss limit or goal stopped it: flat from there
            curve = curve.reindex(pd.DatetimeIndex(times)).ffill()
        slips = sorted((pd.Timestamp(t["at"]), t["fees"] * SLIP / FEE) for t in res.trades)
        if slips:
            at = pd.DatetimeIndex([s[0] for s in slips])
            cum = np.cumsum([s[1] for s in slips])
            k = at.searchsorted(curve.index, side="right")
            curve = curve - np.where(k > 0, cum[np.maximum(k - 1, 0)], 0.0)
        curves.append(curve)
        trades += [{"pnl": t["pnl"] - t["fees"] * SLIP / FEE, "fees": t["fees"] * (1 + SLIP / FEE),
                    "funding": t["funding"], "exit_at": t["at"]} for t in res.trades]
    return chain(curves), trades


# ---------------------------------------------------------------------------
# Comparison and verdict
# ---------------------------------------------------------------------------

def correlation(a: pd.Series, b: pd.Series) -> Optional[float]:
    days = a.index.union(b.index)
    x, y = a.reindex(days, fill_value=0.0), b.reindex(days, fill_value=0.0)
    if len(days) < 3 or x.std() == 0 or y.std() == 0:
        return None
    return round(float(np.corrcoef(x, y)[0, 1]), 3)


def half_and_half(a: pd.Series, b: pd.Series) -> dict:
    """Half the capital in each: daily P&L averaged; net and drawdown on the daily curve."""
    days = a.index.union(b.index)
    d = 0.5 * a.reindex(days, fill_value=0.0) + 0.5 * b.reindex(days, fill_value=0.0)
    curve = CAPITAL + d.cumsum()
    net = float(d.sum()) / CAPITAL * 100
    dd = max_dd_pct(pd.concat([pd.Series([CAPITAL]), curve]))
    return {"neto_pct": round(net, 2), "max_caida_pct": round(dd, 2), "neto_caida": net_dd(net, dd)}


def daily_net_dd(daily: pd.Series) -> Optional[float]:
    curve = CAPITAL + daily.cumsum()
    net = float(daily.sum()) / CAPITAL * 100
    return net_dd(net, max_dd_pct(pd.concat([pd.Series([CAPITAL]), curve])))


def verdict(oos: dict, desk: Optional[dict], corr: Optional[float], combo: Optional[dict],
            desk_daily_ratio: Optional[float], biased: bool = False) -> tuple[str, bool]:
    if biased:
        return ("no cuenta: la lista de monedas es la de hoy (las que más subieron), sesgo de supervivencia",
                False)
    if oos["operaciones"] < MIN_OOS_TRADES:
        return (f"muestra corta: {oos['operaciones']} operaciones fuera de muestra (< {MIN_OOS_TRADES})",
                False)
    pos, total = (int(x) for x in oos["trimestres_positivos"].split("/"))
    quarters_ok = total > 0 and pos / total >= 0.75
    if oos["neto_pct"] <= 0:
        return "pierde fuera de muestra", False
    if desk is not None and oos["neto_caida"] is not None and desk["neto_caida"] is not None \
            and oos["neto_caida"] > desk["neto_caida"] and quarters_ok:
        return "GANA: mejor neto/caída que mesa_r3 y positiva en 3 de cada 4 trimestres", True
    if combo is not None and desk_daily_ratio is not None and corr is not None and abs(corr) < 0.3 \
            and combo["neto_caida"] is not None and combo["neto_caida"] > desk_daily_ratio and quarters_ok:
        return ("SUMA: gana, sin correlación con la mesa, positiva en 3 de cada 4 trimestres, y mitad y mitad "
                "mejora el neto/caída de la mesa", True)
    if not quarters_ok:
        return "positiva, pero no en 3 de cada 4 trimestres", False
    return "positiva, pero no mejora a mesa_r3", False


# ---------------------------------------------------------------------------
# Data and report
# ---------------------------------------------------------------------------

def _fetch_hourly(sym: str, start: datetime, end: datetime) -> tuple[str, Optional[pd.DataFrame], pd.Series]:
    try:
        bars = tw.fetch(sym, "1h", start, end)
    except Exception as error:  # noqa: BLE001
        print(f"{sym}: sin velas 1h ({type(error).__name__})")
        return sym, None, pd.Series(dtype=float)
    return sym, bars, tw.fetch_funding(sym, start, end)


def load_market(symbols: list[str], start: datetime, end: datetime, workers: int = 8) -> tuple[Market, dict]:
    times = pd.date_range(start, end - HOUR, freq="1h", tz="UTC")
    with ThreadPoolExecutor(workers) as ex:
        got = list(ex.map(lambda s: _fetch_hourly(s, start, end), symbols))
    bars = {s: b for s, b, _ in got if b is not None}
    funding = {s: f for s, b, f in got if b is not None}
    for s in bars:
        print(f"{s}: {len(bars[s])} velas 1h, financiación {len(funding[s])} puntos")
    return build_market(bars, funding, times), funding


def load_desk(m: Market, funding: dict[str, pd.Series], wins: list[Window], processes: int) -> dict[str, tw.Prepared]:
    a = m.times[wins[0][1]].to_pydatetime() - timedelta(minutes=5 * tw.WARMUP)
    b = (m.times[-1] + HOUR).to_pydatetime()

    def one(sym: str) -> Optional[tuple]:
        try:
            m5 = tw.fetch(sym, "5m", a, b)
        except Exception as error:  # noqa: BLE001
            print(f"{sym}: sin velas 5m ({type(error).__name__})")
            return None
        h1 = pd.DataFrame({k: getattr(m, k)[sym] for k in ("open", "high", "low", "close")}).dropna()
        h1["volume"] = 0.0
        top = tw.fetch_top_traders(sym, a, b)
        print(f"{sym}: {len(m5)} velas 5m, top traders {len(top)} puntos (mesa)")
        return sym, m5, h1, top, funding.get(sym)

    with ThreadPoolExecutor(len(m.symbols)) as ex:
        jobs = [j for j in ex.map(one, m.symbols) if j is not None]
    with Pool(max(1, processes)) as pool:
        done = pool.map(_prepare_one, jobs)
    return {s: p for s, p in done if p is not None}


FAMILY_NAMES = {"rotacion": "Rotación por momentum (12 monedas)", "rotacion_top30": "Rotación por momentum (top 30)",
                "reversion": "Reversión corta en rangos (1h)", "pares": "Pares ETH/BTC y SOL/ETH"}


def _row(name: str, s: dict, corr: Optional[float] = None, extra: str = "") -> str:
    q = " · ".join(f"{k}: {v:+.1f}%" for k, v in s["trimestres"].items())
    return (f"| {name} | {s['operaciones']} | {s['neto_pct']:+.2f}% | {s['max_caida_pct']}% | {s['neto_caida']} | "
            f"{s['acierto_pct']}% | {s['ganancia_media']:+.2f} / {s['perdida_media']:+.2f} | "
            f"{s['comisiones_usdt']:.2f} | {s['financiacion_usdt']:+.2f} | {corr if corr is not None else '—'} | "
            f"{q} | {extra} |")


def render(result: dict, meta: dict) -> str:
    lines = [f"# Rotación y reversión: estudio fuera de muestra ({meta['desde']} a {meta['hasta']})", "",
             "Investigación con datos públicos de Binance (sin cuenta, sin claves, sin órdenes). Velas de 1 hora (precio "
             "Spot como aproximación del perpetuo USDⓈ-M). Capital de estudio 1.000 USDT, 1x, máximo 3 posiciones, "
             "posición máx. 50%. Comisión 0,05% y deslizamiento 0,02% por lado, financiación real cada hora. Un stop y "
             "una meta en la misma vela cuentan como stop.", "",
             f"**Walk-forward:** se ajusta en 90 días, se prueba en los 30 siguientes y se avanza 30 "
             f"({meta['ventanas']} ventanas de prueba). Solo cuenta la prueba. En cada ventana se usa la combinación "
             "con mejor neto/caída del ajuste; si hasta la mejor perdió en el ajuste, esa ventana no se opera. Cada "
             "ventana empieza con 1.000 USDT y cierra todo al final; el resultado es la suma de las ventanas.", "",
             "## Resultado fuera de muestra (misma ventana para todos)", "",
             "| Estrategia | Operaciones | Neto % | Máx. caída | Neto/caída | Acierto | Ganancia / pérdida media (USDT) | "
             "Comisiones | Financiación | Correlación diaria con la mesa | Por trimestre | Veredicto |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    desk, btc = result.get("mesa"), result["btc"]
    if desk:
        lines.append(_row(f"**{DESK_BASELINE} (la mesa en vivo)**", desk, None, "referencia"))
    lines.append(_row("BTC comprar y mantener", btc, result.get("btc_corr"), "referencia"))
    for fam, r in result["familias"].items():
        lines.append(_row(FAMILY_NAMES.get(fam, fam), r["oos"], r.get("corr_mesa"), r["veredicto"]))
    lines += ["", "Neto/caída = neto % dividido por la máxima caída %: cuánto se gana por cada punto de caída. La máxima caída "
              "se mide en % del capital de 1.000 USDT (las ventanas se suman, no se reinvierten). "
              "La mesa (mesa_r3) se repite con velas de 5 minutos y sus reglas reales, ventana por ventana, con el "
              "mismo deslizamiento agregado.", ""]
    for fam, r in result["familias"].items():
        lines += [f"## {FAMILY_NAMES.get(fam, fam)}", ""]
        if r.get("mitad_mesa"):
            c = r["mitad_mesa"]
            lines.append(f"Mitad del capital aquí y mitad en la mesa: neto {c['neto_pct']:+.2f}%, caída "
                         f"{c['max_caida_pct']}%, neto/caída {c['neto_caida']} (la mesa sola, medida igual por día: "
                         f"{result.get('mesa_neto_caida_diaria')}).")
            lines.append("")
        lines += ["Elección por ventana (ajuste → prueba):", "", "| Prueba | Parámetros elegidos | Ajuste neto % | "
                  "Prueba neto % | Operaciones |", "|---|---|---|---|---|"]
        for f in r["folds"]:
            lines.append(f"| {f['prueba'][0]} a {f['prueba'][1]} | {f['elegida'] or 'no se opera'} | "
                         f"{f['ajuste_neto_pct']:+.2f}% | {f['prueba_neto_pct']:+.2f}% | {f['operaciones']} |")
        good = [x for x in r["fijas"] if x["neto_pct"] > 0]
        best = max(r["fijas"], key=lambda x: (x["neto_caida"] is not None, x["neto_caida"] or 0))
        lines += ["", f"Cada combinación fija en todas las ventanas de prueba: {len(good)} de {len(r['fijas'])} "
                  f"ganan. La mejor a posteriori ({best['parametros']}: {best['neto_pct']:+.2f}%, caída "
                  f"{best['max_caida_pct']}%, {best['operaciones']} operaciones) no cuenta como evidencia: se eligió "
                  "mirando la prueba.", ""]
    lines += ["## Veredicto", ""]
    winners = [(f, r) for f, r in result["familias"].items() if r["gana"]]
    if winners:
        for f, r in winners:
            o = r["oos"]
            lines.append(f"- **{FAMILY_NAMES.get(f, f)}**: {r['veredicto']}. Neto {o['neto_pct']:+.2f}%, caída "
                         f"{o['max_caida_pct']}%, {o['operaciones']} operaciones, trimestres positivos "
                         f"{o['trimestres_positivos']}. Merece práctica con dinero ficticio, no dinero real todavía.")
    else:
        lines.append("**Ninguna candidata le gana a la mesa ni suma de forma clara fuera de muestra.** No se recomienda "
                     "llevar ninguna a práctica con estas reglas. Es un resultado útil: evita gastar comisiones en "
                     "estrategias que no ganan.")
    lines += ["", "Advertencias: el precio Spot aproxima al perpetuo; la rotación top 30 usa la lista de hoy (sesgo de "
              "supervivencia); cerrar todo al final de cada ventana agrega algo de comisión a la rotación; elegir "
              "entre ~20 combinaciones en el ajuste infla el ajuste (por eso solo cuenta la prueba). Un resultado "
              "pasado no promete uno futuro."]
    return "\n".join(lines) + "\n"


def study(m: Market, wins: list[Window], families: dict[str, Market],
          desk: Optional[tuple[pd.Series, list[dict]]]) -> dict:
    result: dict = {"familias": {}}
    btc_curve = buy_and_hold(m, wins)
    result["btc"] = metrics([], btc_curve)
    desk_daily = None
    desk_m = None
    if desk is not None:
        desk_m = metrics(desk[1], desk[0])
        desk_daily = daily_pnl(desk[0])
        result["mesa"] = desk_m
        result["mesa_neto_caida_diaria"] = daily_net_dd(desk_daily)
        result["btc_corr"] = correlation(daily_pnl(btc_curve), desk_daily)
    for fam, fm in families.items():
        grid = GRIDS["rotacion" if fam.startswith("rotacion") else fam]
        r = walk_forward(fm, fam, grid, wins)
        curve = r.pop("curva")
        daily = daily_pnl(curve)
        corr = combo = None
        if desk_daily is not None:
            corr = correlation(daily, desk_daily)
            combo = half_and_half(daily, desk_daily)
        r["corr_mesa"], r["mitad_mesa"] = corr, combo
        r["veredicto"], r["gana"] = verdict(r["oos"], desk_m, corr, combo, result.get("mesa_neto_caida_diaria"),
                                           biased=fam == "rotacion_top30")
        result["familias"][fam] = r
        print(f"{fam}: {r['oos']['operaciones']} operaciones, neto {r['oos']['neto_pct']:+.2f}%, "
              f"caída {r['oos']['max_caida_pct']}% -> {r['veredicto']}")
    return result


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Rotación y reversión (investigación, datos públicos)")
    parser.add_argument("--dias", type=int, default=365, help="days of out-of-sample test windows")
    parser.add_argument("--simbolos", nargs="+", default=list(tw.SYMBOLS))
    parser.add_argument("--sin-mesa", action="store_true", help="skip the mesa_r3 baseline (much faster)")
    parser.add_argument("--top30", action="store_true", help="also rotate over today's top 30 by volume")
    parser.add_argument("--procesos", type=int, default=4)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=args.dias + FIT_DAYS + WARM_DAYS + 2)
    m, funding = load_market(args.simbolos, start, end)
    wins = windows(m, args.dias)
    families: dict[str, Market] = {"rotacion": m, "reversion": m, "pares": m}
    if args.top30:
        from trading_intelligence.backtesting import universe_scan

        try:
            top = [r["symbol"] for r in universe_scan.scan()["top"]]
            m30, _ = load_market(top, start, end)
            families["rotacion_top30"] = m30
        except Exception as error:  # noqa: BLE001 - optional extra
            print(f"top 30 sin datos ({type(error).__name__}: {error})")
    desk = None
    if not args.sin_mesa:
        prepared = load_desk(m, funding, wins, args.procesos)
        desk = desk_curve(prepared, m, wins)
    result = study(m, wins, families, desk)
    meta = {"desde": str(m.times[wins[0][1]])[:10], "hasta": str(m.times[-1])[:10], "ventanas": len(wins),
            "simbolos": m.symbols, "top30": families["rotacion_top30"].symbols if "rotacion_top30" in families else None,
            "costes": {"comision_lado": FEE, "deslizamiento_lado": SLIP}, "capital": CAPITAL}
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = end.date().isoformat()
    (args.salida / f"rotacion_{stamp}.json").write_text(
        json.dumps({"meta": meta, **result}, indent=1, default=str), encoding="utf-8")
    report = render(result, meta)
    (args.salida / f"rotacion_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
