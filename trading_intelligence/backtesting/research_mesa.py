"""
Robustness and tuning of the live desk (mesa_r3) over a year, research only (docs/research/PROTOCOLO.md).

Leader, 2026-10-12 (owner: "si no ganamos no tiene sentido, busca estrategias"):
  1. mesa_r3 over 365 days, per quarter, against BTC buy-and-hold: does it survive bear and range markets?
  2. exits, walk-forward (fit 90 days, test the next 30): target_r, trailing start/distance, a time exit;
  3. Skeptic audit per distinct setup (not per bar), and the effect of removing each rule;
  4. sizing: risk 1-15% by quality vs fixed 2/5/10% vs half Kelly, at 1x and 3x (practice-only scenarios).

The desk is replayed exactly as two_way_backtest.simulate("mesa_r3") does it (a test proves it, trade for
trade, with slippage 0), on 5-minute bars with real funding and top traders, plus the protocol's 0.02%
slippage per side. Signals, stops and sentiment are computed once per bar (the expensive part), then each
scenario is a cheap array replay. The year is cut into 30-day blocks, each started fresh with 1,000 USDT
(the desk works month by month: loss limit 45%, goal +58%); positions open at a block's end are closed.
Public data only: no account, no key, no orders. Nothing here changes config/ or live/.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import real_data_validation as rdv
from trading_intelligence.backtesting import two_way_backtest as tw
from trading_intelligence.live import desk as D
from trading_intelligence.strategy.exit_plan import plan_exits
from trading_intelligence.strategy.two_way_signals import decide, quality

BASE = "tendencia_rango_1h_top"
DAYS, BLOCK_DAYS, FIT_BLOCKS = 365, 30, 3
BLOCK_BARS = BLOCK_DAYS * 288
CAPITAL, SLIPPAGE = 1000.0, 0.0002
VETO_LOOKAHEAD = tw.VETO_LOOKAHEAD
RULES = ("rr", "redondo", "financiacion", "sentimiento")
OUT_DIR = Path("docs/research/mesa")


@dataclass(frozen=True)
class Exits:
    target_r: float = 3.0
    trail_start: float = tw.TRAIL_START_R
    trail_dist: float = tw.TRAIL_DISTANCE_R
    max_hold_bars: Optional[int] = None
    close_on_signal: bool = True  # an opposite signal closes the position

    def label(self) -> str:
        hold = f", salida {self.max_hold_bars // 12} h" if self.max_hold_bars else ""
        sig = "" if self.close_on_signal else ", sin cierre por señal"
        return f"{self.target_r:g}R, trailing desde {self.trail_start:g}R a {self.trail_dist:g}R{hold}{sig}"


BASELINE = Exits()
GRID = [Exits(r, s, d, h) for r, (s, d), h in itertools.product(
    (2.5, 3.0, 4.0, 5.0), ((1.0, 0.5), (1.5, 1.0), (2.0, 1.0)), (None, 72 * 12))]


@dataclass(frozen=True)
class Sizing:
    name: str
    risk: Optional[float] = None  # None: 1-15% by quality; "kelly" handled by the caller via `risk`
    leverage: float = 1.0
    max_position: float = tw.MAX_POSITION


SIZINGS = [Sizing("calidad 1-15%, 1x"), Sizing("fijo 2%, 1x", 0.02), Sizing("fijo 5%, 1x", 0.05),
           Sizing("fijo 10%, 1x", 0.10), Sizing("calidad 1-15%, 3x", None, 3.0, 1.5),
           Sizing("fijo 5%, 3x", 0.05, 3.0, 1.5), Sizing("fijo 10%, 3x", 0.10, 3.0, 1.5)]


# ---------------------------------------------------------------------------
# Per-symbol arrays (computed once)
# ---------------------------------------------------------------------------

@dataclass
class Sym:
    times: np.ndarray  # int64 ns
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    side: np.ndarray  # +1 BUY, -1 SELL, 0 none (the desk's signal at this bar)
    qual: np.ndarray
    stop: np.ndarray  # plan_exits stop where side != 0 (NaN if no plan)
    mood: np.ndarray
    funding: np.ndarray  # % per 8h in force (NaN when unknown)
    near_round: np.ndarray  # bool: the stop sits on a round number


def arrays(p: tw.Prepared, rules: D.DeskRules) -> Sym:
    bars = p.bars
    n = len(bars)
    side = np.zeros(n, dtype=np.int8)
    qual = np.zeros(n)
    stop = np.full(n, np.nan)
    mood = np.zeros(n)
    near = np.zeros(n, dtype=bool)
    funding = np.array([np.nan if f is None else f for f in (p.funding or [None] * n)], dtype=float)
    closes = bars["close"].values
    for i in range(n):
        mood[i] = D.sentiment(p.funding[i] if p.funding else None, p.top_ratio[i] if p.top_ratio else None,
                              None).score
        r = p.readings[i]
        s = decide(r, BASE) if r is not None else None
        if s is None or r is None:
            continue
        side[i] = 1 if s == "BUY" else -1
        qual[i] = quality(r, s)
        window = bars.iloc[max(0, i - tw.WINDOW + 1): i + 1]
        try:
            plan = plan_exits(window, Decimal(str(float(closes[i]))), side=s)
        except ValueError:
            continue
        stop[i] = float(plan.stop)
        near[i] = D._near_round(plan.stop, rules.round_number_buffer_pct) is not None
    return Sym(pd.DatetimeIndex(bars.index).as_unit("ns").asi8, bars["open"].values.astype(float), bars["high"].values.astype(float),
               bars["low"].values.astype(float), closes.astype(float), side, qual, stop, mood, funding, near)


def align(syms: dict[str, Sym]) -> tuple[np.ndarray, dict[str, Sym]]:
    """Reindex every symbol to the union of times (NaN close = no bar)."""
    times = np.unique(np.concatenate([s.times for s in syms.values()]))
    out = {}
    for name, s in syms.items():
        pos = np.searchsorted(times, s.times)

        def put(a: np.ndarray, fill: float | int | bool, dtype: Any = float, _pos: np.ndarray = pos) -> np.ndarray:
            full = np.full(len(times), fill, dtype=dtype)
            full[_pos] = a
            return full
        out[name] = Sym(times, put(s.open, np.nan), put(s.high, np.nan), put(s.low, np.nan), put(s.close, np.nan),
                        put(s.side, 0, np.int8), put(s.qual, 0.0), put(s.stop, np.nan), put(s.mood, 0.0),
                        put(s.funding, np.nan), put(s.near_round, False, bool))
    return times, out


# ---------------------------------------------------------------------------
# Regime gates (leader, 2026-10-12): which sides may be open at each bar. Bit 1 = longs, bit 2 = shorts.
# Daily and 4h values count only once their bar has closed (no look-ahead); unknown (warm-up) = no gate.
# ---------------------------------------------------------------------------

LONG, SHORT, BOTH = 1, 2, 3
GATE_NAMES = {
    "a": "a) BTC sobre su media de 200 días: solo largos; si no, fuera",
    "b": "b) BTC sobre su media de 50 días: solo largos; si no, fuera",
    "c": "c) tendencia 4h de la moneda y diaria de BTC (medias 50) de acuerdo: ese lado; si no, fuera",
    "d": "d) largos sobre la media de 200 días de BTC, cortos debajo",
    "e": "e) sin operar si BTC cae en 30 días",
    "f": "f) sin entradas de 12 h antes a 12 h después de cada decisión FOMC y dato de IPC (CPI) de EE. UU.",
    "g1": "g1) largos solo tras una purga: interés abierto −5% o más en 24 h con precio ≥ −3% (en las últimas 24 h)",
    "g2": "g2) sin largos si el interés abierto sube 10% o más en 7 días con el precio plano (±3%)",
}
ENTRY_ONLY = frozenset({"f", "g1", "g2"})  # these gates only stop new entries; open positions run their course

# US macro events (times in New York). FOMC: statement day, 14:00 ET (federalreserve.gov/monetarypolicy/
# fomccalendars.htm). CPI: 8:30 ET (bls.gov/schedule/news_release/cpi.htm); 2025 shutdown: September CPI moved
# to Oct 24, October CPI cancelled, November CPI on Dec 18 (bls.gov/bls/092025-cpi-reschedule-notice.htm).
FOMC_DAYS = ("2024-11-07", "2024-12-18", "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30",
             "2025-09-17", "2025-10-29", "2025-12-10", "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
             "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09")
CPI_DAYS = ("2024-10-10", "2024-11-13", "2024-12-11", "2025-01-15", "2025-02-12", "2025-03-12", "2025-04-10",
            "2025-05-13", "2025-06-11", "2025-07-15", "2025-08-12", "2025-09-11", "2025-10-24", "2025-12-18",
            "2026-01-13", "2026-02-13", "2026-03-11", "2026-04-10", "2026-05-12", "2026-06-10", "2026-07-14",
            "2026-08-12", "2026-09-11", "2026-10-14", "2026-11-10", "2026-12-10")
EVENT_HOURS = 12


def macro_events() -> list[pd.Timestamp]:
    ny = ZoneInfo("America/New_York")
    out = [pd.Timestamp(f"{d} 14:00", tz=ny) for d in FOMC_DAYS] + [pd.Timestamp(f"{d} 08:30", tz=ny) for d in CPI_DAYS]
    return sorted(t.tz_convert("UTC") for t in out)


def near_event(times: np.ndarray, events: list[pd.Timestamp], hours: int = EVENT_HOURS) -> np.ndarray:
    """True for bars within `hours` before or after any event."""
    ev = np.array(sorted(pd.DatetimeIndex(events).as_unit("ns").asi8))
    w = hours * 3_600_000_000_000
    j = np.searchsorted(ev, times)
    after = np.where(j < len(ev), ev[np.clip(j, 0, len(ev) - 1)] - times, np.iinfo(np.int64).max)
    before = np.where(j > 0, times - ev[np.clip(j - 1, 0, None)], np.iinfo(np.int64).max)
    return (after <= w) | (before <= w)


def change_over(values: np.ndarray, times: np.ndarray, hours: float) -> np.ndarray:
    """values[k] / (value as of times[k] - hours) - 1; NaN where unknown."""
    lag = times - int(hours * 3_600_000_000_000)
    j = np.searchsorted(times, lag, side="right") - 1
    past = np.where(j >= 0, values[np.clip(j, 0, None)], np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        return values / past - 1


def flush_masks(close: np.ndarray, oi: np.ndarray, times: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """g1: longs only within 24 h after OI fell >= 5% in 24 h with price >= -3%; g2: no longs while OI rose
    >= 10% in 7 days with price within +-3%. Shorts are untouched. Unknown OI = no gate."""
    c = pd.Series(close).ffill().values
    o = pd.Series(oi).ffill().values
    oi24, px24 = change_over(o, times, 24), change_over(c, times, 24)
    oi7, px7 = change_over(o, times, 168), change_over(c, times, 168)
    flush = (oi24 <= -0.05) & (px24 >= -0.03)
    hit = np.where(flush, times, np.iinfo(np.int64).min)
    recent = np.maximum.accumulate(hit) >= times - 24 * 3_600_000_000_000
    g1 = np.where(np.isnan(oi24), BOTH, np.where(recent, BOTH, SHORT)).astype(np.int8)
    fragile = (oi7 >= 0.10) & (np.abs(px7) <= 0.03)
    g2 = np.where(np.isnan(oi7), BOTH, np.where(fragile, SHORT, BOTH)).astype(np.int8)
    return g1, g2


def trend(closes: pd.Series, interval: pd.Timedelta, n: int, times: np.ndarray) -> np.ndarray:
    """+1 / -1 if the last CLOSED bar is above / below its n-bar mean as of each time; NaN while unknown."""
    sma = closes.rolling(n).mean()
    sign = np.where(sma.isna(), np.nan, np.sign(closes.values - sma.values))
    avail = pd.DatetimeIndex(closes.index + interval).as_unit("ns").asi8
    j = np.searchsorted(avail, times, side="right") - 1
    return np.where(j >= 0, sign[np.clip(j, 0, None)], np.nan)


def gates(times: np.ndarray, names: list[str], btc_d1: pd.Series, h4: dict[str, pd.Series],
          oi: Optional[dict[str, np.ndarray]] = None, close: Optional[dict[str, np.ndarray]] = None) -> dict[str, dict]:
    day, four = pd.Timedelta(days=1), pd.Timedelta(hours=4)
    b200, b50 = trend(btc_d1, day, 200, times), trend(btc_d1, day, 50, times)
    ret =(btc_d1 / btc_d1.shift(30) - 1).values
    avail = pd.DatetimeIndex(btc_d1.index + day).as_unit("ns").asi8
    j = np.searchsorted(avail, times, side="right") - 1
    r30 = np.where(j >= 0, ret[np.clip(j, 0, None)], np.nan)

    def mask(cond_long: np.ndarray, cond_short: np.ndarray, unknown: np.ndarray) -> np.ndarray:
        m = np.where(cond_long, LONG, 0) | np.where(cond_short, SHORT, 0)
        return np.where(unknown, BOTH, m).astype(np.int8)

    events = np.where(near_event(times, macro_events()), 0, BOTH).astype(np.int8)
    out: dict[str, dict] = {"f": {name: events for name in names}, "g1": {}, "g2": {}}
    for name in names:
        if oi and close and name in oi:
            out["g1"][name], out["g2"][name] = flush_masks(close[name], oi[name], times)
        else:
            out["g1"][name] = out["g2"][name] = np.full(len(times), BOTH, dtype=np.int8)
    for g in ("a", "b", "c", "d", "e"):
        per = {}
        for name in names:
            if g == "a":
                per[name] = mask(b200 > 0, np.zeros(len(times), bool), np.isnan(b200))
            elif g == "b":
                per[name] = mask(b50 > 0, np.zeros(len(times), bool), np.isnan(b50))
            elif g == "c":
                c4 = trend(h4[name], four, 50, times) if name in h4 else np.full(len(times), np.nan)
                per[name] = mask((c4 > 0) & (b50 > 0), (c4 < 0) & (b50 < 0), np.isnan(c4) | np.isnan(b50))
            elif g == "d":
                per[name] = mask(b200 > 0, b200 < 0, np.isnan(b200))
            else:
                per[name] = mask(r30 >= 0, r30 >= 0, np.isnan(r30))
        out[g] = per
    return {g: out[g] for g in GATE_NAMES}


# ---------------------------------------------------------------------------
# The desk, replayed (mirror of two_way_backtest.simulate for "mesa_r3")
# ---------------------------------------------------------------------------

@dataclass
class _Pos:
    side: int
    qty: float
    entry: float
    sl: float
    tp: float
    r: float
    k0: int
    fee_in: float
    funding: float = 0.0


@dataclass
class Replay:
    trades: list[dict] = field(default_factory=list)
    curve: list[float] = field(default_factory=list)
    end: str = "fin del bloque"
    skipped_liquidation: int = 0
    peak: float = 0.0  # highest bar-close equity seen (drawdown brake)
    paused: bool = False  # the drawdown brake stopped new entries
    halved: int = 0  # entries taken at half risk by the drawdown brake
    capped: int = 0  # signals kept out by the open-risk cap (a run of bars on one symbol counts once)


def vetoes(s: Sym, k: int, side: int, target_r: float, rules: D.DeskRules) -> list[str]:
    out = []
    if Decimal(str(target_r)) < rules.min_reward_risk:
        out.append("rr")
    if s.near_round[k]:
        out.append("redondo")
    f = s.funding[k]
    if not math.isnan(f) and Decimal(str(f if side > 0 else -f)) > rules.max_funding_against_pct:
        out.append("financiacion")
    lean = s.mood[k] if side > 0 else -s.mood[k]
    if lean <= rules.min_sentiment_against:
        out.append("sentimiento")
    return out


def replay(syms: dict[str, Sym], lo: int, hi: int, exits: Exits = BASELINE, sizing: Sizing = SIZINGS[0],
           rules_on: frozenset[str] = frozenset(RULES), rules: Optional[D.DeskRules] = None,
           slippage: float = SLIPPAGE, capital: float = CAPITAL, risk_override: Optional[float] = None,
           allow: Optional[dict[str, np.ndarray]] = None, close_on_gate: bool = True,
           entry_allow: Optional[dict[str, np.ndarray]] = None,
           dd_brake: Optional[tuple[float, float]] = None, peak: Optional[float] = None,
           paused: bool = False, risk_scale: Optional[np.ndarray] = None,
           open_risk_cap: Optional[float] = None) -> Replay:
    """`dd_brake` (half, pause): from a drawdown of `half` off the highest bar-close equity (`peak` carries it in
    from earlier blocks) new entries take half the risk; from `pause` on there are no new entries for the rest of
    the block (`paused` carries a pause in). It only lowers risk, never raises it. `risk_scale`: a per-bar factor
    (<= 1) on the risk of new entries.
    `allow`: a regime gate per symbol (bit 1 longs, bit 2 shorts); a closed side is not opened, and a position
    on it is closed at the bar's close ("régimen") unless `close_on_gate` is False (the gate only stops entries).
    `entry_allow`: a second mask, same bits, that only stops new entries (combined with `allow`).
    `open_risk_cap`: no new entry while the open positions on the same side would lose more than this share of the
    bar's equity if every stop were hit (a stop trailed past its entry counts 0)."""
    rules = rules or D.DeskRules.load()
    res = Replay(peak=max(capital, peak or 0.0), paused=paused)
    cash = capital
    pos: dict[str, _Pos] = {}
    liq = 1 / sizing.leverage - tw.MAINTENANCE
    last_capped: dict[str, int] = {}

    def close_pos(name: str, p: _Pos, price: float, why: str, k: int) -> float:
        long = p.side > 0
        price = price * (1 - slippage) if long else price * (1 + slippage)
        gross = (price - p.entry) * p.qty if long else (p.entry - price) * p.qty
        fee_out = price * p.qty * tw.FEE
        res.trades.append({"symbol": name, "side": "BUY" if long else "SELL", "k0": p.k0, "k1": k, "why": why,
                           "pnl": gross - fee_out - p.fee_in - p.funding, "fees": fee_out + p.fee_in,
                           "funding": p.funding, "risk_usdt": p.r * p.qty})
        return gross - fee_out - p.funding

    for k in range(lo, hi):
        marks: dict[str, float] = {}
        for name, s in syms.items():
            c = s.close[k]
            if math.isnan(c):
                continue
            marks[name] = c
            p = pos.get(name)
            if p is None:
                continue
            long = p.side > 0
            f = s.funding[k]
            rate = f / 100 if not math.isnan(f) else tw.FUNDING_PER_8H
            p.funding += p.qty * c * rate * tw.BAR_HOURS / 8 * (1 if long else -1)
            hit_sl = s.low[k] <= p.sl if long else s.high[k] >= p.sl
            hit_tp = s.high[k] >= p.tp if long else s.low[k] <= p.tp
            sig = int(s.side[k])
            if hit_sl or hit_tp:
                cash += close_pos(name, p, p.sl if hit_sl else p.tp, "stop" if hit_sl else "meta", k)
            elif exits.close_on_signal and sig != 0 and sig != p.side:
                cash += close_pos(name, p, c, "señal contraria", k)
            elif close_on_gate and allow is not None and not allow[name][k] & (LONG if long else SHORT):
                cash += close_pos(name, p, c, "régimen", k)
            elif exits.max_hold_bars is not None and k - p.k0 >= exits.max_hold_bars:
                cash += close_pos(name, p, c, "tiempo", k)
            else:
                gain = c - p.entry if long else p.entry - c
                if p.r > 0 and gain >= exits.trail_start * p.r:
                    new = c - exits.trail_dist * p.r if long else c + exits.trail_dist * p.r
                    p.sl = max(p.sl, new) if long else min(p.sl, new)
                continue
            del pos[name]
        equity = cash + sum(((marks.get(n, q.entry) - q.entry) * q.qty if q.side > 0
                             else (q.entry - marks.get(n, q.entry)) * q.qty) for n, q in pos.items())
        res.curve.append(equity)
        res.peak = max(res.peak, equity)
        drawdown = 1 - equity / res.peak
        if dd_brake is not None and drawdown >= dd_brake[1]:
            res.paused = True
        if equity <= capital * (1 - tw.LOSS_LIMIT) or equity >= capital * (1 + tw.GOAL):
            for name, q in list(pos.items()):
                cash += close_pos(name, q, marks.get(name, q.entry), "fin de sesión", k)
            pos.clear()
            res.end = "límite de pérdida" if equity <= capital * (1 - tw.LOSS_LIMIT) else "meta"
            break
        for name, s in syms.items():
            if res.paused and dd_brake is not None:
                break
            if name in pos or len(pos) >= tw.MAX_OPEN:
                continue
            sig = int(s.side[k])
            c = s.close[k]
            if sig == 0 or math.isnan(c) or math.isnan(s.stop[k]):
                continue
            if allow is not None and not allow[name][k] & (LONG if sig > 0 else SHORT):
                continue
            if entry_allow is not None and not entry_allow[name][k] & (LONG if sig > 0 else SHORT):
                continue
            sl = float(s.stop[k])
            if [v for v in vetoes(s, k, sig, exits.target_r, rules) if v in rules_on]:
                continue
            dist = abs(c - sl)
            if dist <= 0:
                continue
            if dist / c >= liq:
                res.skipped_liquidation += 1
                continue
            if open_risk_cap is not None:
                at_risk = sum(max(0.0, (o.entry - o.sl) * o.side) * o.qty for o in pos.values() if o.side == sig)
                if at_risk > open_risk_cap * equity:
                    res.capped += int(last_capped.get(name) != k - 1)
                    last_capped[name] = k
                    continue
            qual = max(0.0, min(1.0, float(s.qual[k])))  # no sentiment tilt on the size, as the desk since f8912db
            if risk_override is not None:
                risk = risk_override
            elif sizing.risk is not None:
                risk = sizing.risk
            else:
                risk = tw.RISK_MIN + (tw.RISK_MAX - tw.RISK_MIN) * qual
            if risk_scale is not None:
                risk *= min(1.0, float(risk_scale[k]))
            halve = dd_brake is not None and drawdown >= dd_brake[0]
            if halve:
                risk *= 0.5
            used = sum(o.qty * o.entry for o in pos.values())
            qty = min(equity * risk / dist, equity * sizing.max_position / c,
                      max(0.0, sizing.leverage * equity - used) * 0.95 / c)
            if qty * c < tw.MIN_NOTIONAL.get(name, tw.DEFAULT_MIN_NOTIONAL):
                continue
            entry = c * (1 + slippage) if sig > 0 else c * (1 - slippage)
            fee_in = qty * entry * tw.FEE
            cash -= fee_in
            tp = c + sig * exits.target_r * dist
            pos[name] = _Pos(sig, qty, entry, sl, tp, dist, k, fee_in)
            res.halved += int(halve)
    else:
        last = hi - 1
        for name, q in list(pos.items()):
            c = syms[name].close[last]
            cash += close_pos(name, q, q.entry if math.isnan(c) else c, "fin del bloque", last)
    return res


def stats(rep: Replay, capital: float = CAPITAL) -> dict:
    pnl = [t["pnl"] for t in rep.trades]
    wins, losses = [p for p in pnl if p > 0], [p for p in pnl if p <= 0]
    curve = np.array(rep.curve or [capital])
    peak = np.maximum.accumulate(curve)
    by = {s: [t["pnl"] for t in rep.trades if t["side"] == s] for s in ("BUY", "SELL")}
    return {"trades": len(pnl), "win_rate": round(len(wins) / len(pnl) * 100, 1) if pnl else 0.0,
            "net_pct": round(sum(pnl) / capital * 100, 2), "max_dd_pct": round(float(((peak - curve) / peak).max() * 100), 2),
            "avg_win": round(float(np.mean(wins)), 2) if wins else 0.0,
            "avg_loss": round(float(np.mean(losses)), 2) if losses else 0.0,
            "fees": round(sum(t["fees"] for t in rep.trades), 2), "funding": round(sum(t["funding"] for t in rep.trades), 2),
            "long_n": len(by["BUY"]), "long_net_pct": round(sum(by["BUY"]) / capital * 100, 2),
            "short_n": len(by["SELL"]), "short_net_pct": round(sum(by["SELL"]) / capital * 100, 2),
            "end": rep.end, "skipped_liquidation": rep.skipped_liquidation}


def chain(block_stats: list[dict], curves: list[list[float]], capital: float = CAPITAL) -> dict:
    """Blocks compounded one after another: total return and the drawdown of the chained equity."""
    level, chained = 1.0, []
    for c in curves:
        arr = np.array(c or [capital]) / capital * level
        chained.extend(arr.tolist())
        level = arr[-1] if len(arr) else level
    arr = np.array(chained or [1.0])
    peak = np.maximum.accumulate(arr)
    dd = float(((peak - arr) / peak).max() * 100)
    net = (level - 1) * 100
    return {"net_pct": round(net, 2), "max_dd_pct": round(dd, 2), "net_dd": round(net / dd, 2) if dd > 0 else None,
            "trades": sum(b["trades"] for b in block_stats),
            "blocks_positive": sum(1 for b in block_stats if b["net_pct"] > 0), "blocks": len(block_stats)}


# ---------------------------------------------------------------------------
# Skeptic audit per distinct setup
# ---------------------------------------------------------------------------

def setup_outcome(s: Sym, k: int, side: int, target_r: float) -> str:
    c, sl = s.close[k], s.stop[k]
    tp = c + side * target_r * abs(c - sl)
    for j in range(k + 1, min(len(s.close), k + 1 + VETO_LOOKAHEAD)):
        if math.isnan(s.close[j]):
            continue
        if (side > 0 and s.low[j] <= sl) or (side < 0 and s.high[j] >= sl):
            return "evitó pérdida"
        if (side > 0 and s.high[j] >= tp) or (side < 0 and s.low[j] <= tp):
            return "dejó pasar ganancia"
    return "sin resultado"


def veto_audit(syms: dict[str, Sym], lo: int, hi: int, rules: D.DeskRules, target_r: float = 3.0) -> dict:
    """A setup = a run of consecutive bars with the same symbol, side and veto reasons; scored once, from its
    first bar, as stop-first or target-first (3R) within 24 h."""
    out = {r: {"setups": 0, "solo": 0, "evitó pérdida": 0, "dejó pasar ganancia": 0, "sin resultado": 0,
               "solo_evitó": 0, "solo_dejó": 0} for r in RULES}
    for s in syms.values():
        prev: Optional[tuple[int, tuple[str, ...]]] = None
        for k in range(lo, hi):
            sig = int(s.side[k])
            if sig == 0 or math.isnan(s.close[k]) or math.isnan(s.stop[k]):
                prev = None
                continue
            reasons = tuple(vetoes(s, k, sig, target_r, rules))
            key = (sig, reasons)
            if not reasons or key == prev:
                prev = key if reasons else None
                continue
            prev = key
            outcome = setup_outcome(s, k, sig, target_r)
            for r in reasons:
                out[r]["setups"] += 1
                out[r][outcome] += 1
                if len(reasons) == 1:
                    out[r]["solo"] += 1
                    if outcome == "evitó pérdida":
                        out[r]["solo_evitó"] += 1
                    elif outcome == "dejó pasar ganancia":
                        out[r]["solo_dejó"] += 1
    return out


# ---------------------------------------------------------------------------
# Experiments (blocks run in parallel; SYMS is shared with the workers by fork)
# ---------------------------------------------------------------------------

SYMS: dict[str, Sym] = {}
RULES_OBJ: Optional[D.DeskRules] = None
GATES: dict[str, dict] = {}


def _block(task: tuple) -> tuple:
    key, lo, hi, exits, sizing, rules_on, risk, *gate = task
    allow = GATES[gate[0]] if gate and gate[0] else None
    rep = replay(SYMS, lo, hi, exits, sizing, rules_on, RULES_OBJ, risk_override=risk, allow=allow,
                 close_on_gate=not (gate and gate[0] in ENTRY_ONLY))
    return key, lo, stats(rep), rep.curve, [{k: t[k] for k in ("pnl", "side", "risk_usdt")} for t in rep.trades]


def blocks(n_bars: int, start: int) -> list[tuple[int, int]]:
    out, lo = [], start
    while lo + BLOCK_BARS <= n_bars:
        out.append((lo, lo + BLOCK_BARS))
        lo += BLOCK_BARS
    return out


def run_tasks(tasks: list[tuple], workers: int) -> dict:
    with Pool(max(1, workers)) as pool:
        results = pool.map(_block, tasks)
    out: dict = {}
    for key, lo, st, curve, trades in results:
        out.setdefault(key, {})[lo] = (st, curve, trades)
    return out


def half_kelly(trades: list[dict]) -> float:
    """Half Kelly in fraction of equity risked per trade, from P&L measured in R (pnl / money at risk)."""
    rs = [t["pnl"] / t["risk_usdt"] for t in trades if t.get("risk_usdt")]
    if len(rs) < 10:
        return tw.RISK_MIN
    wins = [r for r in rs if r > 0]
    losses = [-r for r in rs if r <= 0]
    if not wins or not losses:
        return tw.RISK_MIN
    p, b = len(wins) / len(rs), np.mean(wins) / np.mean(losses)
    f = p - (1 - p) / b
    return float(min(tw.RISK_MAX, max(tw.RISK_MIN, f / 2)))


def experiments(times: np.ndarray, workers: int) -> dict:
    bl = blocks(len(times), tw.WARMUP)
    rules = RULES_OBJ or D.DeskRules.load()
    tasks: list[tuple] = [(("grid", g), lo, hi, g, SIZINGS[0], frozenset(RULES), None) for g in GRID for lo, hi in bl]
    tasks += [(("rules_off", r), lo, hi, BASELINE, SIZINGS[0], frozenset(RULES) - {r}, None)
              for r in RULES for lo, hi in bl]
    tasks += [(("rules_off", "todas"), lo, hi, BASELINE, SIZINGS[0], frozenset(), None) for lo, hi in bl]
    tasks += [(("sizing", z.name), lo, hi, BASELINE, z, frozenset(RULES), None) for z in SIZINGS for lo, hi in bl]
    tasks += [(("gate", g), lo, hi, BASELINE, SIZINGS[0], frozenset(RULES), None, g) for g in GATES for lo, hi in bl]
    res = run_tasks(tasks, workers)
    base = res[("grid", BASELINE)]
    los = [lo for lo, _ in bl]

    def series(key: tuple, use: Optional[list[int]] = None) -> dict:
        sel = [lo for lo in los if use is None or lo in use]
        st = [res[key][lo][0] for lo in sel]
        return {"total": chain(st, [res[key][lo][1] for lo in sel]), "blocks": st}

    # 1. quarters (3 blocks each) for mesa_r3, with BTC buy-and-hold
    btc = SYMS.get("BTCUSDT")

    def quarter_rows(per: dict) -> list[dict]:
        rows = []
        for q in range(0, len(bl) - len(bl) % 3, 3):
            qlos = los[q:q + 3]
            st = [per[lo][0] for lo in qlos]
            tot = chain(st, [per[lo][1] for lo in qlos])
            a, b = bl[q][0], bl[q + 2][1] - 1
            bh = None
            if btc is not None and not math.isnan(btc.close[a]) and not math.isnan(btc.close[b]):
                bh = round((btc.close[b] / btc.close[a] - 1) * 100, 2)
            rows.append({"from": str(pd.Timestamp(times[a], tz="UTC").date()),
                         "to": str(pd.Timestamp(times[b], tz="UTC").date()), **tot, "btc_buy_hold_pct": bh,
                         "long_n": sum(s["long_n"] for s in st), "long_net_pct": round(sum(s["long_net_pct"] for s in st), 2),
                         "short_n": sum(s["short_n"] for s in st),
                         "short_net_pct": round(sum(s["short_net_pct"] for s in st), 2),
                         "win_rate": round(np.mean([s["win_rate"] for s in st if s["trades"]]), 1) if any(s["trades"] for s in st) else 0.0})
        return rows

    quarters = quarter_rows(base)
    # 5. regime gates: each gate per quarter and over the year, plus a gate chosen walk-forward
    gate_rows = {}
    for g in GATES:
        qs = quarter_rows(res[("gate", g)])
        year = series(("gate", g))["total"]
        positive = sum(1 for x in qs if x["net_pct"] > 0)
        gate_rows[g] = {"name": GATE_NAMES[g], "quarters": qs, "year": year, "quarters_positive": positive,
                        "passes": positive >= 3 and len(qs) >= 4 and (year["net_dd"] or 0) > 1}
    options: dict[str, dict] = {"ninguno": base, **{g: res[("gate", g)] for g in GATES}}
    gate_wf = []
    for j in range(FIT_BLOCKS, len(los)):
        fit = los[j - FIT_BLOCKS: j]

        def gscore(g: str, _fit: list[int] = fit) -> float:
            c = chain([options[g][lo][0] for lo in _fit], [options[g][lo][1] for lo in _fit])
            return c["net_pct"] / max(c["max_dd_pct"], 1.0)
        gate_wf.append((los[j], max(options, key=gscore)))
    gwf_total = chain([options[g][lo][0] for lo, g in gate_wf], [options[g][lo][1] for lo, g in gate_wf])
    gates_out = {"rows": gate_rows,
                 "walk_forward": {"oos": gwf_total, "chosen": [{"block_from": str(pd.Timestamp(times[lo], tz="UTC").date()),
                                                                "gate": g} for lo, g in gate_wf],
                                  "baseline_same_blocks": series(("grid", BASELINE), [lo for lo, _ in gate_wf])["total"]}}
    # 2. walk-forward exits: pick on the previous FIT_BLOCKS blocks by chained net/drawdown, test the next block
    wf, chosen = [], []
    for j in range(FIT_BLOCKS, len(los)):
        fit = los[j - FIT_BLOCKS: j]

        def score(g: Exits, _fit: list[int] = fit) -> float:
            c = chain([res[("grid", g)][lo][0] for lo in _fit], [res[("grid", g)][lo][1] for lo in _fit])
            return c["net_pct"] / max(c["max_dd_pct"], 1.0)
        best = max(GRID, key=score)
        chosen.append(best)
        wf.append((los[j], best))
    oos_los = [lo for lo, _ in wf]
    wf_stats = [res[("grid", g)][lo][0] for lo, g in wf]
    wf_total = chain(wf_stats, [res[("grid", g)][lo][1] for lo, g in wf])
    base_oos = series(("grid", BASELINE), oos_los)
    # 3. Skeptic: per setup over the whole year, and ablations
    audit = veto_audit(SYMS, bl[0][0], bl[-1][1], rules)
    ablation = {r: series(("rules_off", r))["total"] for r in (*RULES, "todas")}
    # 4. sizing (fixed schemes, plus half Kelly fitted walk-forward on mesa_r3's own trades)
    sizing = {z.name: series(("sizing", z.name))["total"] for z in SIZINGS}
    kelly_tasks = []
    for j in range(FIT_BLOCKS, len(los)):
        trades = [t for lo in los[j - FIT_BLOCKS: j] for t in base[lo][2]]
        k = half_kelly(trades)
        for z in (SIZINGS[0], SIZINGS[4]):
            kelly_tasks.append((("kelly", z.leverage), los[j], los[j] + BLOCK_BARS, BASELINE, z, frozenset(RULES), k))
    kres = run_tasks(kelly_tasks, workers)
    for lev, per in kres.items():
        sel = sorted(per)
        sizing[f"medio Kelly (walk-forward), {lev[1]:g}x"] = chain([per[lo][0] for lo in sel], [per[lo][1] for lo in sel])
    sizing["(misma ventana) calidad 1-15%, 1x"] = base_oos["total"]
    return {"blocks": [{"from": str(pd.Timestamp(times[lo], tz="UTC").date()), **base[lo][0]} for lo in los],
            "baseline_year": series(("grid", BASELINE))["total"], "quarters": quarters,
            "walk_forward": {"chosen": [{"block_from": str(pd.Timestamp(times[lo], tz="UTC").date()), "exits": g.label()}
                                        for lo, g in wf],
                             "oos": wf_total, "baseline_same_blocks": base_oos["total"]},
            "skeptic": {"per_setup": audit, "ablation": ablation, "baseline": series(("grid", BASELINE))["total"]},
            "sizing": sizing, "gates": gates_out}


# ---------------------------------------------------------------------------
# Data and report
# ---------------------------------------------------------------------------

def coverage(values: list[Optional[float]], n: int) -> float:
    """% of bars with a known value."""
    known = sum(1 for v in values if v is not None and not (isinstance(v, float) and math.isnan(v)))
    return round(known / n * 100, 1) if n else 0.0


def fetch_metrics(symbol: str, start: datetime, end: datetime) -> tuple[pd.Series, pd.Series]:
    """Top traders' long/short position ratio and open interest (contracts), every 5 minutes, from the daily
    'metrics' files of the public futures archive (one download for both). Empty where missing."""
    top: dict[pd.Timestamp, float] = {}
    oi: dict[pd.Timestamp, float] = {}
    day = start.date()
    while day <= end.date():
        try:
            for row in tw._zip_rows(f"{tw.VISION}/daily/metrics/{symbol}/{symbol}-metrics-{day.isoformat()}.zip"):
                t = pd.Timestamp(row["create_time"], tz="UTC")
                top[t] = float(row["sum_toptrader_long_short_ratio"])
                oi[t] = float(row["sum_open_interest"])
        except Exception:  # noqa: BLE001 - a missing day only leaves a gap
            pass
        day += timedelta(days=1)
    return pd.Series(top, dtype=float).sort_index(), pd.Series(oi, dtype=float).sort_index()


def _load_symbol(args: tuple) -> tuple[str, Optional[Sym], str, dict]:
    sym, warm_iso, end_iso = args
    warm, end = datetime.fromisoformat(warm_iso), datetime.fromisoformat(end_iso)
    rdv.INTERVAL_MS.setdefault("4h", 14_400_000)
    rdv.INTERVAL_MS.setdefault("1d", 86_400_000)
    try:
        m5 = tw.fetch(sym, "5m", warm, end)
        h1 = tw.fetch(sym, "1h", warm - timedelta(hours=tw.SLOW + 5), end)
        h4 = rdv.fetch_klines(sym, "4h", warm - timedelta(days=30), end)["close"]
        d1 = rdv.fetch_klines(sym, "1d", warm - timedelta(days=260), end)["close"]
    except Exception as error:  # noqa: BLE001 - one symbol's data must not stop the others
        return sym, None, f"sin datos ({type(error).__name__})", {}
    (top, oi), funding = fetch_metrics(sym, warm, end), tw.fetch_funding(sym, warm, end)
    p = tw.prepare(m5, h1, tw.WARMUP, top, funding)
    n = len(p.bars)
    oi_bars = oi.reindex(p.bars.index).values if not oi.empty else np.full(n, np.nan)
    extra = {"h4": h4, "d1": d1, "oi": (pd.DatetimeIndex(p.bars.index).as_unit("ns").asi8, oi_bars),
             "cov_top": coverage(p.top_ratio, n), "cov_funding": coverage(p.funding, n),
             "cov_oi": round(float(np.isfinite(oi_bars).mean() * 100), 1) if n else 0.0}
    note = f"{len(m5)} velas, top traders {len(top)} ({extra['cov_top']}% de velas), financiación {len(funding)}"
    return sym, arrays(p, D.DeskRules.load()), note, extra


def verdict(result: dict) -> list[str]:
    q = result["quarters"]
    losing = [x for x in q if x["net_pct"] <= 0]
    bearish = [x for x in q if x["btc_buy_hold_pct"] is not None and x["btc_buy_hold_pct"] < -5]
    lines = []
    if losing:
        lines.append(f"**ALERTA: mesa_r3 pierde en {len(losing)} de {len(q)} trimestres** "
                     + "; ".join(f"{x['from']}→{x['to']}: {x['net_pct']:+.1f}% (BTC {x['btc_buy_hold_pct']:+.1f}%)"
                                 for x in losing) + ".")
    else:
        lines.append(f"mesa_r3 gana en los {len(q)} trimestres.")
    for x in bearish:
        lines.append(f"Trimestre bajista ({x['from']}→{x['to']}, BTC {x['btc_buy_hold_pct']:+.1f}%): mesa_r3 "
                     f"{x['net_pct']:+.1f}%, cortos {x['short_n']} ({x['short_net_pct']:+.1f}%), largos {x['long_n']} "
                     f"({x['long_net_pct']:+.1f}%).")
    if not bearish:
        lines.append("Ningún trimestre fue claramente bajista para BTC (< −5%): la prueba de mercado bajista queda incompleta.")
    if "gates" in result:
        lines.append(gate_verdict(result["gates"]))
    return lines


def gate_verdict(gates_out: dict) -> str:
    passing = [r["name"] for r in gates_out["rows"].values() if r["passes"]]
    if passing:
        return "**Pasan el listón (≥3 de 4 trimestres positivos y neto/caída > 1):** " + "; ".join(passing) + "."
    return ("**Ningún filtro de régimen pasa el listón** (≥3 de 4 trimestres positivos y neto/caída > 1): la mesa es "
            "una herramienta de mercado alcista y debería quedarse fuera el resto del tiempo.")


def render_gates(gates_out: dict, base_quarters: list[dict]) -> list[str]:
    rows = gates_out["rows"]
    heads = [f"{q['from']} → {q['to']}" for q in base_quarters]
    lines = ["## 5. Filtros de régimen (por trimestre)", "",
             "Mismos bloques que la sección 1. Los valores diarios y de 4h cuentan solo cuando su vela cerró (sin "
             "mirar el futuro). En a–e un filtro cerrado no abre ese lado y cierra al precio de la vela la posición que "
             "ya estuviera abierta; f y g solo impiden entradas nuevas. El interés abierto (g) son contratos, de los "
             "archivos 'metrics' de data.binance.vision; sin dato, sin filtro. Los filtros no tienen parámetros "
             "ajustados aquí, pero se propusieron después de ver el año 2025-10 → 2026-10: ese año no es una prueba "
             "ciega para ellos, el anterior sí.", "",
             gate_verdict(gates_out), "",
             "| Filtro | " + " | ".join(heads) + " | Año: neto % / caída / neto/caída | Ops | Trimestres + | Pasa |",
             "|---|" + "---|" * len(heads) + "---|---|---|---|"]
    lines.append("| mesa_r3 sin filtro | " + " | ".join(f"{q['net_pct']:+.1f}%" for q in base_quarters) + " | | | "
                 f"{sum(1 for q in base_quarters if q['net_pct'] > 0)} | no |")
    for r in rows.values():
        y = r["year"]
        lines.append(f"| {r['name']} | " + " | ".join(f"{q['net_pct']:+.1f}%" for q in r["quarters"])
                     + f" | {y['net_pct']:+.1f}% / {y['max_dd_pct']}% / {y['net_dd']} | {y['trades']} | "
                     f"{r['quarters_positive']} | {'sí' if r['passes'] else 'no'} |")
    wf = gates_out["walk_forward"]
    o, b = wf["oos"], wf["baseline_same_blocks"]
    lines += ["", f"**Filtro elegido walk-forward** (el mejor neto/caída de los 90 días anteriores, entre ninguno y a–g): "
              f"{o['net_pct']:+.1f}% neto, caída {o['max_dd_pct']}%, neto/caída {o['net_dd']}, {o['trades']} operaciones, "
              f"{o['blocks_positive']}/{o['blocks']} bloques positivos; mesa_r3 sin filtro en los mismos bloques: "
              f"{b['net_pct']:+.1f}% / {b['max_dd_pct']}% / {b['net_dd']}.",
              "Elegidos: " + "; ".join(f"{c['block_from']}: {c['gate']}" for c in wf["chosen"])]
    return lines


def render(result: dict, meta: dict) -> str:
    y = result["baseline_year"]
    lines = [f"# La mesa (mesa_r3) en un año: robustez y ajustes ({meta['desde']} a {meta['hasta']})", "",
             "Investigación con datos públicos (sin cuenta, sin órdenes), según `docs/research/PROTOCOLO.md`. La mesa "
             "repetida exactamente como en vivo (meta 3R, trailing desde 1R a 0,5R, Escéptico completo), velas de 5 "
             "minutos, comisión 0,05% por lado, deslizamiento 0,02% por lado, financiación real. Capital 1.000 USDT por "
             "bloque de 30 días (límite de pérdida 45%, meta +58%), bloques encadenados.", "",
             f"**Año completo:** {y['net_pct']:+.1f}% neto, caída máx. {y['max_dd_pct']}%, neto/caída {y['net_dd']}, "
             f"{y['trades']} operaciones, {y['blocks_positive']}/{y['blocks']} bloques positivos.", "",
             "## Veredicto", "", *verdict(result), "",
             "## 1. Por trimestre (mesa_r3 frente a comprar y mantener BTC)", "",
             "| Trimestre | Neto % | Máx. caída | Neto/caída | Ops | Largos (neto %) | Cortos (neto %) | Acierto | BTC comprar y mantener |",
             "|---|---|---|---|---|---|---|---|---|"]
    for x in result["quarters"]:
        lines.append(f"| {x['from']} → {x['to']} | {x['net_pct']:+.1f}% | {x['max_dd_pct']}% | {x['net_dd']} | {x['trades']} | "
                     f"{x['long_n']} ({x['long_net_pct']:+.1f}%) | {x['short_n']} ({x['short_net_pct']:+.1f}%) | "
                     f"{x['win_rate']}% | {x['btc_buy_hold_pct']}% |")
    lines += ["", "| Bloque (30 días) | Neto % | Máx. caída | Ops | Acierto | Comisiones | Financiación | Final |",
              "|---|---|---|---|---|---|---|---|"]
    for b in result["blocks"]:
        lines.append(f"| {b['from']} | {b['net_pct']:+.1f}% | {b['max_dd_pct']}% | {b['trades']} | {b['win_rate']}% | "
                     f"{b['fees']} | {b['funding']} | {b['end']} |")
    wf = result["walk_forward"]
    lines += ["", "## 2. Salidas, walk-forward (ajuste 90 días, prueba 30)", "",
              f"Rejilla: meta 2,5/3/4/5R × trailing (1R→0,5R, 1,5R→1R, 2R→1R) × salida por tiempo (no, 72 h) = {len(GRID)} "
              "combinaciones; en cada bloque se elige la mejor neto/caída de los 90 días anteriores.", "",
              f"- **Fuera de muestra con las salidas elegidas:** {wf['oos']['net_pct']:+.1f}% neto, caída {wf['oos']['max_dd_pct']}%, "
              f"neto/caída {wf['oos']['net_dd']}, {wf['oos']['trades']} operaciones.",
              f"- **mesa_r3 sin cambios en los mismos bloques:** {wf['baseline_same_blocks']['net_pct']:+.1f}% neto, caída "
              f"{wf['baseline_same_blocks']['max_dd_pct']}%, neto/caída {wf['baseline_same_blocks']['net_dd']}, "
              f"{wf['baseline_same_blocks']['trades']} operaciones.",
              "- Elegidas: " + "; ".join(f"{c['block_from']}: {c['exits']}" for c in wf["chosen"])]
    sk = result["skeptic"]
    lines += ["", "## 3. Escéptico: por configuración distinta (no por vela) y al quitar cada regla", "",
              "| Regla | Configuraciones vetadas | Evitó pérdida | Dejó pasar ganancia (3R) | Sin resultado | "
              "Solo esta regla: evitó / dejó pasar | Año sin esta regla: neto % / caída / neto/caída |",
              "|---|---|---|---|---|---|---|"]
    names = {"rr": "beneficio/riesgo mínimo", "redondo": "stop en número redondo", "financiacion": "financiación saturada",
             "sentimiento": "sentimiento en contra"}
    for r in RULES:
        a, ab = sk["per_setup"][r], sk["ablation"][r]
        lines.append(f"| {names[r]} | {a['setups']} | {a['evitó pérdida']} | {a['dejó pasar ganancia']} | {a['sin resultado']} | "
                     f"{a['solo_evitó']} / {a['solo_dejó']} | {ab['net_pct']:+.1f}% / {ab['max_dd_pct']}% / {ab['net_dd']} |")
    allx, b = sk["ablation"]["todas"], sk["baseline"]
    lines += [f"| **sin Escéptico** | | | | | | {allx['net_pct']:+.1f}% / {allx['max_dd_pct']}% / {allx['net_dd']} |",
              f"| **mesa_r3 (todas las reglas)** | | | | | | {b['net_pct']:+.1f}% / {b['max_dd_pct']}% / {b['net_dd']} |", "",
              "Con meta 3R el beneficio/riesgo es siempre 3:1, así que la regla de mínimo 1,5:1 nunca veta. "
              "Una configuración = varias velas seguidas con la misma moneda, lado y motivos de veto; se puntúa una vez, "
              "desde su primera vela, con stop o meta 3R en 24 h (stop primero si caen en la misma vela)."]
    lines += ["", "## 4. Tamaño (escenarios de práctica; el apalancamiento real exige la aprobación escrita del dueño)", "",
              "| Esquema | Neto % | Máx. caída | Neto/caída | Ops |", "|---|---|---|---|---|"]
    for name, s in result["sizing"].items():
        lines.append(f"| {name} | {s['net_pct']:+.1f}% | {s['max_dd_pct']}% | {s['net_dd']} | {s['trades']} |")
    lines += ["", "Medio Kelly se calcula en cada bloque con las operaciones de mesa_r3 de los 90 días anteriores (en R), "
              "entre 1% y 15%; se compara con la fila \"(misma ventana)\"."]
    if "gates" in result:
        lines += ["", *render_gates(result["gates"], result["quarters"])]
    if meta.get("cobertura"):
        lines += ["", "## Cobertura de datos (% de velas de 5 minutos con dato)", "",
                  "| Moneda | Top traders | Financiación | Interés abierto |", "|---|---|---|---|"]
        for s, c in meta["cobertura"].items():
            lines.append(f"| {s} | {c['top_traders_pct']}% | {c['financiacion_pct']}% | "
                         f"{c.get('interes_abierto_pct', '—')}% |")
    lines += ["",
              "Advertencias: el precio Spot aproxima al perpetuo; los últimos ~60 días se usaron para elegir 3R (dentro "
              "de muestra para mesa_r3); un año es pocos ciclos; los bloques empiezan sin posiciones. Un resultado pasado "
              "no promete uno futuro."]
    return "\n".join(lines) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    global SYMS, RULES_OBJ, GATES
    parser = argparse.ArgumentParser(description="La mesa en un año: robustez y ajustes (investigación)")
    parser.add_argument("--dias", type=int, default=DAYS)
    parser.add_argument("--hasta", default=None, help="fin del periodo, AAAA-MM-DD (por defecto: ahora)")
    parser.add_argument("--simbolos", nargs="+", default=list(tw.SYMBOLS))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    if args.hasta:
        end = datetime.fromisoformat(args.hasta).replace(tzinfo=timezone.utc)
    else:
        end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    warm = end - timedelta(days=args.dias) - timedelta(minutes=5 * tw.WARMUP)
    with Pool(max(1, args.workers)) as pool:
        loaded = pool.map(_load_symbol, [(s, warm.isoformat(), end.isoformat()) for s in args.simbolos])
    for sym, _, note, _ in loaded:
        print(f"{sym}: {note}")
    extras = {s: x for s, a, _, x in loaded if a is not None}
    times, SYMS = align({s: a for s, a, _, _ in loaded if a is not None})
    if "BTCUSDT" in extras:
        btc_d1 = extras["BTCUSDT"]["d1"]
    else:
        rdv.INTERVAL_MS.setdefault("1d", 86_400_000)
        btc_d1 = rdv.fetch_klines("BTCUSDT", "1d", warm - timedelta(days=260), end)["close"]
    oi = {}
    for s, x in extras.items():
        t, v = x["oi"]
        full = np.full(len(times), np.nan)
        full[np.searchsorted(times, t)] = v
        oi[s] = full
    GATES = gates(times, list(SYMS), btc_d1, {s: x["h4"] for s, x in extras.items()}, oi,
                  {s: a.close for s, a in SYMS.items()})
    RULES_OBJ = D.DeskRules.load()
    result = experiments(times, args.workers)
    meta = {"desde": (end - timedelta(days=args.dias)).date().isoformat(), "hasta": end.date().isoformat(),
            "simbolos": list(SYMS),
            "cobertura": {s: {"top_traders_pct": x["cov_top"], "financiacion_pct": x["cov_funding"],
                              "interes_abierto_pct": x["cov_oi"]}
                          for s, x in extras.items()}}
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = end.date().isoformat()
    (args.salida / f"mesa_{stamp}.json").write_text(json.dumps({"meta": meta, **result}, indent=1, default=str),
                                                    encoding="utf-8")
    report = render(result, meta)
    (args.salida / f"mesa_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
