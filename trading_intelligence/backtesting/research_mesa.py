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
from typing import Optional

import numpy as np
import pandas as pd

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

    def label(self) -> str:
        hold = f", salida {self.max_hold_bars // 12} h" if self.max_hold_bars else ""
        return f"{self.target_r:g}R, trailing desde {self.trail_start:g}R a {self.trail_dist:g}R{hold}"


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
    return Sym(bars.index.values.astype("int64"), bars["open"].values.astype(float), bars["high"].values.astype(float),
               bars["low"].values.astype(float), closes.astype(float), side, qual, stop, mood, funding, near)


def align(syms: dict[str, Sym]) -> tuple[np.ndarray, dict[str, Sym]]:
    """Reindex every symbol to the union of times (NaN close = no bar)."""
    times = np.unique(np.concatenate([s.times for s in syms.values()]))
    out = {}
    for name, s in syms.items():
        pos = np.searchsorted(times, s.times)

        def put(a: np.ndarray, fill: float | int | bool, dtype: object = float, _pos: np.ndarray = pos) -> np.ndarray:
            full = np.full(len(times), fill, dtype=dtype)
            full[_pos] = a
            return full
        out[name] = Sym(times, put(s.open, np.nan), put(s.high, np.nan), put(s.low, np.nan), put(s.close, np.nan),
                        put(s.side, 0, np.int8), put(s.qual, 0.0), put(s.stop, np.nan), put(s.mood, 0.0),
                        put(s.funding, np.nan), put(s.near_round, False, bool))
    return times, out


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
           slippage: float = SLIPPAGE, capital: float = CAPITAL, risk_override: Optional[float] = None) -> Replay:
    rules = rules or D.DeskRules.load()
    res = Replay()
    cash = capital
    pos: dict[str, _Pos] = {}
    liq = 1 / sizing.leverage - tw.MAINTENANCE

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
            elif sig != 0 and sig != p.side:
                cash += close_pos(name, p, c, "señal contraria", k)
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
        if equity <= capital * (1 - tw.LOSS_LIMIT) or equity >= capital * (1 + tw.GOAL):
            for name, q in list(pos.items()):
                cash += close_pos(name, q, marks.get(name, q.entry), "fin de sesión", k)
            pos.clear()
            res.end = "límite de pérdida" if equity <= capital * (1 - tw.LOSS_LIMIT) else "meta"
            break
        for name, s in syms.items():
            if name in pos or len(pos) >= tw.MAX_OPEN:
                continue
            sig = int(s.side[k])
            c = s.close[k]
            if sig == 0 or math.isnan(c) or math.isnan(s.stop[k]):
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
            qual = max(0.0, min(1.0, float(s.qual[k]) + 0.2 * (s.mood[k] if sig > 0 else -s.mood[k])))
            if risk_override is not None:
                risk = risk_override
            elif sizing.risk is not None:
                risk = sizing.risk
            else:
                risk = tw.RISK_MIN + (tw.RISK_MAX - tw.RISK_MIN) * qual
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


def _block(task: tuple) -> tuple:
    key, lo, hi, exits, sizing, rules_on, risk = task
    rep = replay(SYMS, lo, hi, exits, sizing, rules_on, RULES_OBJ, risk_override=risk)
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
    res = run_tasks(tasks, workers)
    base = res[("grid", BASELINE)]
    los = [lo for lo, _ in bl]

    def series(key: tuple, use: Optional[list[int]] = None) -> dict:
        sel = [lo for lo in los if use is None or lo in use]
        st = [res[key][lo][0] for lo in sel]
        return {"total": chain(st, [res[key][lo][1] for lo in sel]), "blocks": st}

    # 1. quarters (3 blocks each) for mesa_r3, with BTC buy-and-hold
    btc = SYMS.get("BTCUSDT")
    quarters = []
    for q in range(0, len(bl) - len(bl) % 3, 3):
        qlos = los[q:q + 3]
        st = [base[lo][0] for lo in qlos]
        tot = chain(st, [base[lo][1] for lo in qlos])
        a, b = bl[q][0], bl[q + 2][1] - 1
        bh = None
        if btc is not None and not math.isnan(btc.close[a]) and not math.isnan(btc.close[b]):
            bh = round((btc.close[b] / btc.close[a] - 1) * 100, 2)
        quarters.append({"from": str(pd.Timestamp(times[a], tz="UTC").date()),
                         "to": str(pd.Timestamp(times[b], tz="UTC").date()), **tot, "btc_buy_hold_pct": bh,
                         "long_n": sum(s["long_n"] for s in st), "long_net_pct": round(sum(s["long_net_pct"] for s in st), 2),
                         "short_n": sum(s["short_n"] for s in st),
                         "short_net_pct": round(sum(s["short_net_pct"] for s in st), 2),
                         "win_rate": round(np.mean([s["win_rate"] for s in st if s["trades"]]), 1) if any(s["trades"] for s in st) else 0.0})
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
            "sizing": sizing}


# ---------------------------------------------------------------------------
# Data and report
# ---------------------------------------------------------------------------

def _load_symbol(args: tuple) -> tuple[str, Optional[Sym], str]:
    sym, warm_iso, end_iso = args
    warm, end = datetime.fromisoformat(warm_iso), datetime.fromisoformat(end_iso)
    try:
        m5 = tw.fetch(sym, "5m", warm, end)
        h1 = tw.fetch(sym, "1h", warm - timedelta(hours=tw.SLOW + 5), end)
    except Exception as error:  # noqa: BLE001 - one symbol's data must not stop the others
        return sym, None, f"sin datos ({type(error).__name__})"
    top, funding = tw.fetch_top_traders(sym, warm, end), tw.fetch_funding(sym, warm, end)
    p = tw.prepare(m5, h1, tw.WARMUP, top, funding)
    return sym, arrays(p, D.DeskRules.load()), f"{len(m5)} velas, top traders {len(top)}, financiación {len(funding)}"


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
              "entre 1% y 15%; se compara con la fila \"(misma ventana)\".", "",
              "Advertencias: el precio Spot aproxima al perpetuo; los últimos ~60 días se usaron para elegir 3R (dentro "
              "de muestra para mesa_r3); un año es pocos ciclos; los bloques empiezan sin posiciones. Un resultado pasado "
              "no promete uno futuro."]
    return "\n".join(lines) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    global SYMS, RULES_OBJ
    parser = argparse.ArgumentParser(description="La mesa en un año: robustez y ajustes (investigación)")
    parser.add_argument("--dias", type=int, default=DAYS)
    parser.add_argument("--simbolos", nargs="+", default=list(tw.SYMBOLS))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    warm = end - timedelta(days=args.dias) - timedelta(minutes=5 * tw.WARMUP)
    with Pool(max(1, args.workers)) as pool:
        loaded = pool.map(_load_symbol, [(s, warm.isoformat(), end.isoformat()) for s in args.simbolos])
    for sym, _, note in loaded:
        print(f"{sym}: {note}")
    times, SYMS = align({s: a for s, a, _ in loaded if a is not None})
    RULES_OBJ = D.DeskRules.load()
    result = experiments(times, args.workers)
    meta = {"desde": (end - timedelta(days=args.dias)).date().isoformat(), "hasta": end.date().isoformat(),
            "simbolos": list(SYMS)}
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
