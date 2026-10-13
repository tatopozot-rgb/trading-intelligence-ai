"""
Real-data check of the two-way futures engine before the owner approves real money. Owner,
2026-10-10: "No Apruebo los límites de futuros, deben ser analizados ... debe ser mejor analizado".

Replays the last N days on 5-minute bars for the futures symbols, with exactly the live rules:
- the signals of strategy/two_way_signals.py (every variant compared, plus "mesa": the desk —
  tendencia_rango_1h_top, then the sentiment weighing the quality and the Skeptic's hard rules from
  config/desk_rules.json), one decision per closed 5m bar (the live 30 s / 5 min cadence cannot be finer
  than the bars);
- stop and target from strategy/exit_plan.py at each entry (band 3-15%), the stop that follows the gain
  from +1R at R/2, an opposite signal closing the position;
- size (owner, 2026-10-10): risk from 1% to 15% of equity with the signal's quality, a position at most
  50% of equity at 1x, all positions within the equity, 3 positions, Binance's minimum notional (5 USDT;
  ETH 20, BTC 100) — with the owner's capital, so small-account limits show up;
- session loss limit 45% and goal +58%;
- costs: 0.05% taker fee per side and the real funding rate of each 8-hour period (0.01% when missing).
- the Skeptic's vetoes are followed forward: did the refused trade hit its stop (veto right) or its
  target (veto wrong) first?

Data (no account, no key): 5m/1h klines from data-api.binance.vision (SPOT prices, a proxy for the
USDⓈ-M perpetuals, which track spot closely); Binance's top traders' position ratio and funding rates
from the futures archive on data.binance.vision.
A stop and a target touched in the same bar count as the stop (pessimistic). Past results do not
promise future ones: this compares the variants on the same recent market, it does not forecast.

    python -m trading_intelligence.backtesting.two_way_backtest --dias 30
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.request
import zipfile
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import real_data_validation as rdv
from trading_intelligence.live import desk as D
from trading_intelligence.regime.detector import detect_regime
from trading_intelligence.strategy.exit_plan import plan_exits
from trading_intelligence.strategy.two_way_signals import (
    BB_PERIOD,
    BB_STD,
    FAST,
    SLOW,
    VARIANTS,
    Reading,
    decide,
    quality,
    top_direction,
)

SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT",
           "LTCUSDT", "TRXUSDT", "DOTUSDT")
MIN_NOTIONAL = {"BTCUSDT": 100.0, "ETHUSDT": 20.0}
DEFAULT_MIN_NOTIONAL = 5.0
FEE, FUNDING_PER_8H = 0.0005, 0.0001
RISK_MIN, RISK_MAX, MAX_POSITION, MAX_OPEN, LEVERAGE = 0.01, 0.15, 0.50, 3, 1.0
# "mesa" is what runs live: the desk with config/desk_rules.json's take profit and the bull-run mode.
# "mesa_sin_alcista" drops the bull-run mode; "mesa_libre" has no take-profit band and no bull-run mode, as the
# desk was on 2026-10-10; "mesa_meta_3_5" keeps the owner's 3-5% band (2026-10-11) to keep measuring it.
# "mesa_r1_5" / "mesa_r2" / "mesa_r3": the target at 1.5, 2 or 3 times the risk (owner, 2026-10-11: "replantea la
# ganancia que recompense el riesgo"), to pick the reward that pays best.
R_VARIANTS = {"mesa_r1_5": Decimal("1.5"), "mesa_r2": Decimal("2"), "mesa_r3": Decimal("3")}
DESK_VARIANTS = ("mesa", "mesa_sin_alcista", "mesa_libre", "mesa_meta_3_5", *R_VARIANTS)
ALL_VARIANTS = (*VARIANTS, *DESK_VARIANTS)
VISION = "https://data.binance.vision/data/futures/um"
VETO_LOOKAHEAD = 288  # bars (24 h) to score a veto
LOSS_LIMIT, GOAL = 0.45, 0.58
MAINTENANCE = 0.005  # isolated-margin maintenance rate (approx.): a stop beyond liquidation is refused


@dataclass(frozen=True)
class Sizing:
    """How big each trade is. The default is the owner-approved live setting (config/futures_limits.json)."""
    name: str = "actual"
    risk_min: float = RISK_MIN
    risk_max: float = RISK_MAX
    max_position: float = MAX_POSITION  # notional of one position / equity
    leverage: float = LEVERAGE

    def liquidation_distance(self) -> float:
        return 1 / self.leverage - MAINTENANCE  # fraction of the entry price


# Research only: what higher risk per trade would have done. Live limits change only with the owner's approval.
RISK_SCENARIOS = (
    Sizing("actual: 1x, posición 50%, riesgo 1-15%"),
    Sizing("3x, posición 150%, riesgo 1-15%", max_position=1.5, leverage=3.0),
    Sizing("5x, posición 250%, riesgo 15-30%", risk_min=0.15, risk_max=0.30, max_position=2.5, leverage=5.0),
)
TRAIL_START_R, TRAIL_DISTANCE_R = 1.0, 0.5
WINDOW, WARMUP = 300, 300
BAR_HOURS = 5 / 60
OUT_DIR = Path("docs/two_way_backtest")

Fetcher = Callable[[str, str, datetime, datetime], pd.DataFrame]


def fetch(symbol: str, interval: str, start: datetime, end: datetime) -> pd.DataFrame:
    rdv.INTERVAL_MS.setdefault("5m", 300_000)
    rdv.INTERVAL_MS.setdefault("1h", 3_600_000)
    return rdv.fetch_klines(symbol, interval, start, end)


def _zip_rows(url: str) -> list[dict]:
    with urllib.request.urlopen(url, timeout=30) as resp:  # public archive: no key, no account
        blob = resp.read(50_000_001)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = z.namelist()[0]
        return list(csv.DictReader(io.StringIO(z.read(name).decode("utf-8"))))


def fetch_top_traders(symbol: str, start: datetime, end: datetime) -> pd.Series:
    """Top traders' long/short POSITION ratio every 5 minutes (daily 'metrics' files). Empty if missing."""
    points: dict[pd.Timestamp, float] = {}
    day = start.date()
    while day <= end.date():
        try:
            for row in _zip_rows(f"{VISION}/daily/metrics/{symbol}/{symbol}-metrics-{day.isoformat()}.zip"):
                points[pd.Timestamp(row["create_time"], tz="UTC")] = float(row["sum_toptrader_long_short_ratio"])
        except Exception:  # noqa: BLE001 - a missing day only leaves a gap
            pass
        day += timedelta(days=1)
    return pd.Series(points, dtype=float).sort_index()


def fetch_funding(symbol: str, start: datetime, end: datetime) -> pd.Series:
    """Funding rate per 8-hour period, in % (monthly 'fundingRate' files). Empty if missing."""
    points: dict[pd.Timestamp, float] = {}
    month = start.replace(day=1)
    while month <= end:
        try:
            for row in _zip_rows(f"{VISION}/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{month:%Y-%m}.zip"):
                points[pd.Timestamp(int(row["calc_time"]), unit="ms", tz="UTC")] = float(row["last_funding_rate"]) * 100
        except Exception:  # noqa: BLE001
            pass
        month = (month + timedelta(days=32)).replace(day=1)
    return pd.Series(points, dtype=float).sort_index()


@dataclass
class Prepared:
    bars: pd.DataFrame
    readings: list[Optional[Reading]]  # one per bar (None during warm-up)
    top_ratio: list[Optional[float]] = field(default_factory=list)
    funding: list[Optional[float]] = field(default_factory=list)  # % per 8h in force at the bar


def _asof(series: Optional[pd.Series], t: pd.Timestamp) -> Optional[float]:
    if series is None or series.empty:
        return None
    j = int(series.index.searchsorted(t, side="right")) - 1
    return float(series.iloc[j]) if j >= 0 else None


def prepare(m5: pd.DataFrame, h1: pd.DataFrame, warmup: int = WARMUP, top: Optional[pd.Series] = None,
            funding: Optional[pd.Series] = None) -> Prepared:
    close = m5["close"]
    fast, slow = close.rolling(FAST).mean(), close.rolling(SLOW).mean()
    mid, sd = close.rolling(BB_PERIOD).mean(), close.rolling(BB_PERIOD).std()
    hc = h1["close"]
    hf, hs = hc.rolling(FAST).mean(), hc.rolling(SLOW).mean()
    hdir = np.where((hf > hs) & (hc > hs), "BUY", np.where((hf < hs) & (hc < hs), "SELL", ""))
    h_close_times = (h1.index + pd.Timedelta(hours=1)).values
    readings: list[Optional[Reading]] = []
    tops: list[Optional[float]] = []
    fundings: list[Optional[float]] = []
    for i in range(len(m5)):
        bar_close = m5.index[i] + pd.Timedelta(minutes=5)
        tops.append(_asof(top, bar_close))
        fundings.append(_asof(funding, bar_close))
        if i < warmup:
            readings.append(None)
            continue
        window = m5.iloc[max(0, i - WINDOW + 1): i + 1]
        try:
            snap = detect_regime(window)
            regime, confidence = snap.regime, float(snap.confidence)
        except Exception:  # noqa: BLE001
            regime, confidence = None, 0.0
        j = int(np.searchsorted(h_close_times, bar_close.to_datetime64(), side="right")) - 1  # last closed hour
        htf = (hdir[j] or None) if j >= SLOW else None
        readings.append(Reading(regime, float(close.iloc[i]), float(fast.iloc[i]), float(slow.iloc[i]),
                                float(mid.iloc[i] - BB_STD * sd.iloc[i]), float(mid.iloc[i] + BB_STD * sd.iloc[i]),
                                htf, confidence, top_direction(tops[-1])))
    return Prepared(m5, readings, tops, fundings)


@dataclass
class Pos:
    side: str
    qty: float
    entry: float
    sl: float
    tp: float
    r: float
    kind: str
    fee_in: float
    funding: float = 0.0
    rally: bool = False  # a bull-run long: closed only by its (trailing) stop


@dataclass
class Result:
    variant: str
    trades: list[dict] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    end: str = "fin del periodo"
    skipped_minimum: int = 0
    vetoes: dict = field(default_factory=lambda: {"evitó pérdida": 0, "dejó pasar ganancia": 0, "sin resultado": 0})
    risks: list[float] = field(default_factory=list)
    real_risks: list[float] = field(default_factory=list)  # loss at the stop / equity, after every cap
    skipped_liquidation: int = 0
    rally_entries: int = 0

    def summary(self, capital: float) -> dict:
        pnl = [t["pnl"] for t in self.trades]
        wins = [p for p in pnl if p > 0]
        curve = np.array(self.equity_curve or [capital])
        peak = np.maximum.accumulate(curve)
        dd = float(((peak - curve) / peak).max() * 100) if len(curve) else 0.0
        by = {}
        for key in ("BUY", "SELL"):
            sel = [t["pnl"] for t in self.trades if t["side"] == key]
            by[key] = {"operaciones": len(sel), "neto": round(sum(sel), 4)}
        for key in ("tendencia", "rango"):
            sel = [t["pnl"] for t in self.trades if t["kind"] == key]
            by[key] = {"operaciones": len(sel), "neto": round(sum(sel), 4)}
        return {"variante": self.variant, "operaciones": len(pnl), "ganadas": len(wins),
                "acierto_pct": round(len(wins) / len(pnl) * 100, 1) if pnl else 0.0,
                "neto_usdt": round(sum(pnl), 4), "neto_pct": round(sum(pnl) / capital * 100, 2),
                "comisiones_usdt": round(sum(t["fees"] for t in self.trades), 4),
                "financiacion_usdt": round(sum(t["funding"] for t in self.trades), 4),
                "max_caida_pct": round(dd, 2), "sin_minimo": self.skipped_minimum, "final": self.end, "por": by,
                "riesgo_medio_pct": round(float(np.mean(self.risks)) * 100, 2) if self.risks else 0.0,
                "riesgo_real_medio_pct": round(float(np.mean(self.real_risks)) * 100, 2) if self.real_risks else 0.0,
                "riesgo_real_max_pct": round(float(np.max(self.real_risks)) * 100, 2) if self.real_risks else 0.0,
                "sin_margen_liquidacion": self.skipped_liquidation, "entradas_alcistas": self.rally_entries,
                "vetos": self.vetoes}


def _exit(pos: Pos, price: float, why: str, t: pd.Timestamp, sym: str) -> tuple[float, dict]:
    gross = (price - pos.entry) * pos.qty if pos.side == "BUY" else (pos.entry - price) * pos.qty
    fee_out = price * pos.qty * FEE
    pnl = gross - fee_out - pos.fee_in - pos.funding
    return gross - fee_out - pos.funding, {"symbol": sym, "side": pos.side, "kind": pos.kind, "entry": pos.entry,
                                            "exit": price, "why": why, "at": t.isoformat(), "pnl": pnl,
                                            "fees": fee_out + pos.fee_in, "funding": pos.funding}


def _veto_outcome(p: Prepared, i: int, side: str, sl: float, tp: float) -> str:
    for k in range(i + 1, min(len(p.bars), i + 1 + VETO_LOOKAHEAD)):
        bar = p.bars.iloc[k]
        if (side == "BUY" and bar["low"] <= sl) or (side == "SELL" and bar["high"] >= sl):
            return "evitó pérdida"
        if (side == "BUY" and bar["high"] >= tp) or (side == "SELL" and bar["low"] <= tp):
            return "dejó pasar ganancia"
    return "sin resultado"


def simulate(prepared: dict[str, Prepared], variant: str, capital: float,
             rules: Optional[D.DeskRules] = None, sizing: Sizing = Sizing(),
             on_skip: Optional[Callable[[dict], None]] = None) -> Result:
    """on_skip (research only): called with the sizing details of every entry refused for the minimum notional."""
    res = Result(variant)
    desk = variant in DESK_VARIANTS
    band = variant in ("mesa", "mesa_sin_alcista", "mesa_meta_3_5", *R_VARIANTS)
    ride = variant == "mesa"
    base = "tendencia_rango_1h_top" if desk else variant
    daily = {s: p.bars["close"].resample("1D").last().dropna() for s, p in prepared.items()} if ride else {}
    rules = rules or D.DeskRules.load()
    if variant == "mesa_meta_3_5":
        rules = replace(rules, target_min_pct=Decimal("3"), target_max_pct=Decimal("5"))
    if variant in R_VARIANTS:
        rules = replace(rules, target_r=R_VARIANTS[variant], target_min_pct=None, target_max_pct=None)
    cash = capital
    positions: dict[str, Pos] = {}
    times = sorted(set().union(*[set(p.bars.index) for p in prepared.values()]))
    idx = {s: {t: i for i, t in enumerate(p.bars.index)} for s, p in prepared.items()}
    for t in times:
        marks: dict[str, float] = {}
        for sym, p in prepared.items():
            i = idx[sym].get(t)
            if i is None:
                continue
            bar, reading = p.bars.iloc[i], p.readings[i]
            close = float(bar["close"])
            marks[sym] = close
            pos = positions.get(sym)
            if pos is not None:
                long = pos.side == "BUY"
                f_pct = p.funding[i] if p.funding else None
                rate = f_pct / 100 if f_pct is not None else FUNDING_PER_8H
                pos.funding += pos.qty * close * rate * BAR_HOURS / 8 * (1 if long else -1)  # longs pay when > 0
                hit_sl = bar["low"] <= pos.sl if long else bar["high"] >= pos.sl
                hit_tp = bar["high"] >= pos.tp if long else bar["low"] <= pos.tp
                signal = decide(reading, base) if reading is not None else None
                if hit_sl or hit_tp:
                    cash_delta, trade = _exit(pos, pos.sl if hit_sl else pos.tp, "stop" if hit_sl else "meta", t, sym)
                elif signal is not None and signal != pos.side and not pos.rally:
                    cash_delta, trade = _exit(pos, close, "señal contraria", t, sym)
                else:
                    gain = close - pos.entry if long else pos.entry - close
                    if pos.r > 0 and gain >= TRAIL_START_R * pos.r:
                        new = close - TRAIL_DISTANCE_R * pos.r if long else close + TRAIL_DISTANCE_R * pos.r
                        pos.sl = max(pos.sl, new) if long else min(pos.sl, new)
                    continue
                cash += cash_delta
                res.trades.append(trade)
                del positions[sym]
        equity = cash + sum(((marks.get(s, q.entry) - q.entry) * q.qty if q.side == "BUY"
                             else (q.entry - marks.get(s, q.entry)) * q.qty) for s, q in positions.items())
        res.equity_curve.append(equity)
        if equity <= capital * (1 - LOSS_LIMIT) or equity >= capital * (1 + GOAL):
            for sym, q in list(positions.items()):
                cash_delta, trade = _exit(q, marks.get(sym, q.entry), "fin de sesión", t, sym)
                cash += cash_delta
                res.trades.append(trade)
            res.end = "límite de pérdida" if equity <= capital * (1 - LOSS_LIMIT) else "meta"
            positions.clear()
            break
        for sym, p in prepared.items():
            i = idx[sym].get(t)
            if i is None or sym in positions or len(positions) >= MAX_OPEN:
                continue
            reading = p.readings[i]
            side = decide(reading, base) if reading is not None else None
            if side is None or reading is None:
                continue
            qual = quality(reading, side)
            close = float(p.bars["close"].iloc[i])
            window = p.bars.iloc[max(0, i - WINDOW + 1): i + 1]
            try:
                plan = plan_exits(window, Decimal(str(close)), side=side)
            except ValueError:
                continue
            sl, tp = float(plan.stop), float(plan.target)
            run = False
            if ride and side == "BUY":
                past = daily[sym][daily[sym].index < t.normalize()]
                closes = pd.concat([past, pd.Series([close], index=[t])])
                run = D.rally(sym, pd.DataFrame({"close": closes}), rules) is not None
            if band:
                ftp = D.shape_target(Decimal(str(close)), plan.target, side, rules, run, plan.stop)
                tp, plan = float(ftp), replace(plan, target=ftp)
            if desk:
                mood = D.sentiment(p.funding[i], p.top_ratio[i], None)
                # no sentiment tilt on the size, as live (docs/research/sentimiento/)
                verdict = D.skeptic(side, Decimal(str(close)), plan.stop, plan.target, mood, p.funding[i], rules)
                if not verdict.approved:
                    res.vetoes[_veto_outcome(p, i, side, sl, tp)] += 1
                    continue
            dist = abs(close - sl)
            if dist <= 0:
                continue
            if dist / close >= sizing.liquidation_distance():  # the exchange would liquidate before the stop
                res.skipped_liquidation += 1
                continue
            risk = sizing.risk_min + (sizing.risk_max - sizing.risk_min) * qual
            used = sum(o.qty * o.entry for o in positions.values())
            qty = min(equity * risk / dist, equity * sizing.max_position / close,
                      max(0.0, sizing.leverage * equity - used) * 0.95 / close)
            if qty * close < MIN_NOTIONAL.get(sym, DEFAULT_MIN_NOTIONAL):
                res.skipped_minimum += 1
                if on_skip is not None:
                    on_skip({"symbol": sym, "i": i, "at": t, "side": side, "close": close, "stop": sl, "target": tp,
                             "dist_pct": dist / close * 100, "risk": risk, "equity": equity, "used": used,
                             "open": len(positions), "minimum": MIN_NOTIONAL.get(sym, DEFAULT_MIN_NOTIONAL),
                             "by_risk": equity * risk / dist * close,
                             "by_position": equity * sizing.max_position,
                             "by_room": max(0.0, sizing.leverage * equity - used) * 0.95})
                continue
            fee_in = qty * close * FEE
            cash -= fee_in
            res.risks.append(risk)
            res.real_risks.append(qty * dist / equity)
            positions[sym] = Pos(side, qty, close, sl, tp, dist, plan.kind, fee_in, rally=run)
            if run:
                res.rally_entries += 1
    else:
        t_end = times[-1] if times else None
        for sym, q in list(positions.items()):
            last = float(prepared[sym].bars["close"].iloc[-1])
            cash_delta, trade = _exit(q, last, "fin del periodo", t_end, sym)
            cash += cash_delta
            res.trades.append(trade)
    return res


def render(summaries: list[dict], meta: dict) -> str:
    lines = [f"# Futuros en los dos sentidos: prueba con datos reales ({meta['desde']} a {meta['hasta']})", "",
             f"Capital {meta['capital']} USDT · {len(meta['simbolos'])} monedas · velas de 5 minutos · riesgo de 1% a 15% "
             "según la calidad de la señal, posición máx. 50%, 3 posiciones, 1x · stop y meta del mercado (3-15%), stop "
             "que sigue la ganancia desde +1R · límite de pérdida 45%, meta 58% · comisión 0,05% por lado y financiación "
             f"real · top traders con datos: {meta.get('con_top_traders', 0)} monedas.", "",
             "| Variante | Operaciones | Acierto | Neto USDT | Neto % | Máx. caída | Riesgo medio | Comisiones | "
             "Compras (neto) | Ventas en corto (neto) | Final |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in summaries:
        lines.append(f"| {s['variante']} | {s['operaciones']} | {s['acierto_pct']}% | {s['neto_usdt']:+.2f} | "
                     f"{s['neto_pct']:+.2f}% | {s['max_caida_pct']}% | {s['riesgo_medio_pct']}% | "
                     f"{s['comisiones_usdt']:.2f} | "
                     f"{s['por']['BUY']['operaciones']} ({s['por']['BUY']['neto']:+.2f}) | "
                     f"{s['por']['SELL']['operaciones']} ({s['por']['SELL']['neto']:+.2f}) | {s['final']} |")
    lines += ["", "Variantes de la mesa: **mesa** = lo que corre en vivo (meta según config/desk_rules.json y modo alcista); "
                  "**mesa_sin_alcista** = sin el modo alcista; **mesa_libre** = sin banda de meta ni modo alcista, como el "
                  "2026-10-10; **mesa_meta_3_5** = la meta de 3-5% del dueño; **mesa_r1_5 / mesa_r2 / mesa_r3** = meta a 1,5, 2 y 3 "
                  "veces el riesgo. Entradas en modo alcista (mesa): "
                  + str(next((s.get("entradas_alcistas", 0) for s in summaries if s["variante"] == "mesa"), 0)) + "."]
    mesa = next((s for s in summaries if s["variante"] == "mesa"), None)
    if mesa is not None:
        v = mesa["vetos"]
        lines += ["", f"Vetos del Escéptico (mesa): {v['evitó pérdida']} evitaron una pérdida, "
                      f"{v['dejó pasar ganancia']} dejaron pasar una ganancia, {v['sin resultado']} sin resultado en 24 h."]
    lines += ["", "Riesgo medio = el que pide la señal (1-15%). Riesgo real = lo que se pierde de la cuenta si salta el stop, "
                  "después de los topes de posición y margen: " + ", ".join(
                      f"{s['variante']} {s.get('riesgo_real_medio_pct', 0)}% (máx. {s.get('riesgo_real_max_pct', 0)}%)"
                      for s in summaries) + "."]
    scen = meta.get("escenarios") or []
    if scen:
        lines += ["", "## Escenarios de riesgo (solo investigación; la mesa con otros tamaños)", "",
                  "| Escenario | Operaciones | Acierto | Neto % | Máx. caída | Riesgo real medio | Riesgo real máx. | "
                  "Sin margen | Final |", "|---|---|---|---|---|---|---|---|---|"]
        for s in scen:
            lines.append(f"| {s['escenario']} | {s['operaciones']} | {s['acierto_pct']}% | {s['neto_pct']:+.2f}% | "
                         f"{s['max_caida_pct']}% | {s['riesgo_real_medio_pct']}% | {s['riesgo_real_max_pct']}% | "
                         f"{s['sin_margen_liquidacion']} | {s['final']} |")
        lines += ["", "Con apalancamiento, un stop más lejos que la liquidación no se abre (columna \"Sin margen\"). "
                      "Cambiar el apalancamiento o el riesgo en vivo exige la aprobación escrita del dueño."]
    valid = [s for s in summaries if s["operaciones"] >= 30]
    best = max(valid, key=lambda s: s["neto_usdt"]) if valid else None
    lines += ["", "## Veredicto", ""]
    short = [s for s in summaries if 0 < s["operaciones"] < 30 and s["neto_usdt"] > 0]
    if short:
        lines.append("Con menos de 30 operaciones, por eso no cuentan para el veredicto: "
                     + "; ".join(f"**{s['variante']}** {s['neto_usdt']:+.2f} USDT en {s['operaciones']}"
                                 for s in short)
                     + ". Son positivas, pero la muestra es corta para confirmarlas.")
        lines.append("")
    if best is None:
        lines.append("Ninguna variante llegó a 30 operaciones: la muestra es corta para decidir.")
    elif best["neto_usdt"] <= 0:
        lines.append(f"Entre las de 30 operaciones o más, ninguna ganó. La que menos perdió fue **{best['variante']}** "
                     f"({best['neto_usdt']:+.2f} USDT). No se recomienda dinero real con estas reglas todavía.")
    else:
        lines.append(f"La mejor en este periodo fue **{best['variante']}**: {best['neto_usdt']:+.2f} USDT "
                     f"({best['neto_pct']:+.2f}%) en {best['operaciones']} operaciones, caída máxima "
                     f"{best['max_caida_pct']}%.")
    lines += ["", "Datos: velas públicas de Binance Spot como aproximación de los perpetuos USDⓈ-M; la financiación "
              "es aproximada; un stop y una meta en la misma vela cuentan como stop. Un resultado pasado no promete "
              "uno futuro: esto compara variantes en el mismo mercado reciente."]
    return "\n".join(lines) + "\n"


def run(days: int, symbols: list[str], capital: float, out_dir: Path = OUT_DIR, fetcher: Fetcher = fetch,
        end: Optional[datetime] = None, warmup: int = WARMUP,
        extras: Optional[Callable[[str, datetime, datetime], tuple[pd.Series, pd.Series]]] = None) -> list[dict]:
    end = end or datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)
    warm = start - timedelta(minutes=5 * warmup)
    prepared = {}
    for sym in symbols:
        try:
            m5 = fetcher(sym, "5m", warm, end)
            h1 = fetcher(sym, "1h", warm - timedelta(hours=SLOW + 5), end)
        except Exception as error:  # noqa: BLE001 - one symbol's data must not stop the others
            print(f"{sym}: sin datos ({type(error).__name__})")
            continue
        top, funding = (extras or (lambda s, a, b: (fetch_top_traders(s, a, b), fetch_funding(s, a, b))))(
            sym, warm, end)
        prepared[sym] = prepare(m5, h1, warmup, top, funding)
        print(f"{sym}: {len(m5)} velas, top traders {len(top)} puntos, financiación {len(funding)} puntos")
    summaries = [simulate(prepared, v, capital).summary(capital) for v in ALL_VARIANTS]
    scenarios = [{"escenario": z.name, **simulate(prepared, "mesa", capital, sizing=z).summary(capital)}
                 for z in RISK_SCENARIOS]
    meta = {"desde": start.date().isoformat(), "hasta": end.date().isoformat(), "capital": capital,
            "simbolos": list(prepared), "escenarios": scenarios,
            "con_top_traders": sum(1 for p in prepared.values() if any(x is not None for x in p.top_ratio))}
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = end.date().isoformat()
    (out_dir / f"{stamp}.json").write_text(json.dumps({"meta": meta, "resultados": summaries}, indent=1),
                                           encoding="utf-8")
    report = render(summaries, meta)
    (out_dir / f"{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return summaries


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Futuros en los dos sentidos: prueba con datos reales")
    parser.add_argument("--dias", type=int, default=30)
    parser.add_argument("--simbolos", nargs="+", default=list(SYMBOLS))
    parser.add_argument("--capital", type=float, default=37.0)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    run(args.dias, args.simbolos, args.capital, args.salida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
