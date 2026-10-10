"""
Real-data check of the two-way futures engine before the owner approves real money. Owner,
2026-10-10: "No Apruebo los límites de futuros, deben ser analizados ... debe ser mejor analizado".

Replays the last N days on 5-minute bars for the futures symbols, with exactly the live rules:
- the signals of strategy/two_way_signals.py (each variant compared: "regimen", "tendencia_rango",
  "tendencia_rango_1h"), one decision per closed 5m bar (the live 2/5-minute cadence cannot be finer
  than the bars);
- stop and target from strategy/exit_plan.py at each entry (band 3-15%), the stop that follows the gain
  from +1R at R/2, an opposite signal closing the position;
- size: 1% of equity at risk, a position at most 40% of equity at 1x, 3 positions, Binance's minimum
  notional (5 USDT; ETH 20, BTC 100) — with the owner's capital, so small-account limits show up;
- session loss limit 45% and goal +58%;
- costs: 0.05% taker fee per side, funding approximated at 0.01% of notional per 8 hours held.

Data: Binance's public klines from data-api.binance.vision (no account, no key). These are SPOT
prices, used as a proxy for the USDⓈ-M perpetuals, which track spot closely; funding is approximated.
A stop and a target touched in the same bar count as the stop (pessimistic). Past results do not
promise future ones: this compares the variants on the same recent market, it does not forecast.

    python -m trading_intelligence.backtesting.two_way_backtest --dias 30
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import real_data_validation as rdv
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
)

SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT",
           "LTCUSDT", "TRXUSDT", "DOTUSDT")
MIN_NOTIONAL = {"BTCUSDT": 100.0, "ETHUSDT": 20.0}
DEFAULT_MIN_NOTIONAL = 5.0
FEE, FUNDING_PER_8H = 0.0005, 0.0001
RISK, MAX_POSITION, MAX_OPEN, LEVERAGE = 0.01, 0.40, 3, 1.0
LOSS_LIMIT, GOAL = 0.45, 0.58
TRAIL_START_R, TRAIL_DISTANCE_R = 1.0, 0.5
WINDOW, WARMUP = 300, 300
BAR_HOURS = 5 / 60
OUT_DIR = Path("docs/two_way_backtest")

Fetcher = Callable[[str, str, datetime, datetime], pd.DataFrame]


def fetch(symbol: str, interval: str, start: datetime, end: datetime) -> pd.DataFrame:
    rdv.INTERVAL_MS.setdefault("5m", 300_000)
    rdv.INTERVAL_MS.setdefault("1h", 3_600_000)
    return rdv.fetch_klines(symbol, interval, start, end)


@dataclass
class Prepared:
    bars: pd.DataFrame
    readings: list[Optional[Reading]]  # one per bar (None during warm-up)


def prepare(m5: pd.DataFrame, h1: pd.DataFrame, warmup: int = WARMUP) -> Prepared:
    close = m5["close"]
    fast, slow = close.rolling(FAST).mean(), close.rolling(SLOW).mean()
    mid, sd = close.rolling(BB_PERIOD).mean(), close.rolling(BB_PERIOD).std()
    hc = h1["close"]
    hf, hs = hc.rolling(FAST).mean(), hc.rolling(SLOW).mean()
    hdir = np.where((hf > hs) & (hc > hs), "BUY", np.where((hf < hs) & (hc < hs), "SELL", ""))
    h_close_times = (h1.index + pd.Timedelta(hours=1)).values
    readings: list[Optional[Reading]] = []
    for i in range(len(m5)):
        if i < warmup:
            readings.append(None)
            continue
        window = m5.iloc[max(0, i - WINDOW + 1): i + 1]
        try:
            regime = detect_regime(window).regime
        except Exception:  # noqa: BLE001
            regime = None
        bar_close = m5.index[i] + pd.Timedelta(minutes=5)
        j = int(np.searchsorted(h_close_times, bar_close.to_datetime64(), side="right")) - 1  # last closed hour
        htf = (hdir[j] or None) if j >= SLOW else None
        readings.append(Reading(regime, float(close.iloc[i]), float(fast.iloc[i]), float(slow.iloc[i]),
                                float(mid.iloc[i] - BB_STD * sd.iloc[i]), float(mid.iloc[i] + BB_STD * sd.iloc[i]),
                                htf))
    return Prepared(m5, readings)


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


@dataclass
class Result:
    variant: str
    trades: list[dict] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    end: str = "fin del periodo"
    skipped_minimum: int = 0

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
                "max_caida_pct": round(dd, 2), "sin_minimo": self.skipped_minimum, "final": self.end, "por": by}


def _exit(pos: Pos, price: float, why: str, t: pd.Timestamp, sym: str) -> tuple[float, dict]:
    gross = (price - pos.entry) * pos.qty if pos.side == "BUY" else (pos.entry - price) * pos.qty
    fee_out = price * pos.qty * FEE
    pnl = gross - fee_out - pos.fee_in - pos.funding
    return gross - fee_out - pos.funding, {"symbol": sym, "side": pos.side, "kind": pos.kind, "entry": pos.entry,
                                            "exit": price, "why": why, "at": t.isoformat(), "pnl": pnl,
                                            "fees": fee_out + pos.fee_in, "funding": pos.funding}


def simulate(prepared: dict[str, Prepared], variant: str, capital: float) -> Result:
    res = Result(variant)
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
                pos.funding += pos.qty * close * FUNDING_PER_8H * BAR_HOURS / 8
                long = pos.side == "BUY"
                hit_sl = bar["low"] <= pos.sl if long else bar["high"] >= pos.sl
                hit_tp = bar["high"] >= pos.tp if long else bar["low"] <= pos.tp
                signal = decide(reading, variant) if reading is not None else None
                if hit_sl or hit_tp:
                    cash_delta, trade = _exit(pos, pos.sl if hit_sl else pos.tp, "stop" if hit_sl else "meta", t, sym)
                elif signal is not None and signal != pos.side:
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
            side = decide(reading, variant) if reading is not None else None
            if side is None:
                continue
            close = float(p.bars["close"].iloc[i])
            window = p.bars.iloc[max(0, i - WINDOW + 1): i + 1]
            try:
                plan = plan_exits(window, Decimal(str(close)), side=side)
            except ValueError:
                continue
            sl, tp = float(plan.stop), float(plan.target)
            dist = abs(close - sl)
            if dist <= 0:
                continue
            qty = min(equity * RISK / dist, LEVERAGE * equity * MAX_POSITION / close)
            if qty * close < MIN_NOTIONAL.get(sym, DEFAULT_MIN_NOTIONAL):
                res.skipped_minimum += 1
                continue
            fee_in = qty * close * FEE
            cash -= fee_in
            positions[sym] = Pos(side, qty, close, sl, tp, dist, plan.kind, fee_in)
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
             f"Capital {meta['capital']} USDT · {len(meta['simbolos'])} monedas · velas de 5 minutos · riesgo 1% por "
             "operación, posición máx. 40%, 3 posiciones, 1x · stop y meta del mercado (3-15%), stop que sigue la "
             "ganancia desde +1R · límite de pérdida 45%, meta 58% · comisión 0,05% por lado y financiación "
             "aproximada.", "",
             "| Variante | Operaciones | Acierto | Neto USDT | Neto % | Máx. caída | Comisiones | Compras (neto) | "
             "Ventas en corto (neto) | Final |", "|---|---|---|---|---|---|---|---|---|---|"]
    for s in summaries:
        lines.append(f"| {s['variante']} | {s['operaciones']} | {s['acierto_pct']}% | {s['neto_usdt']:+.2f} | "
                     f"{s['neto_pct']:+.2f}% | {s['max_caida_pct']}% | {s['comisiones_usdt']:.2f} | "
                     f"{s['por']['BUY']['operaciones']} ({s['por']['BUY']['neto']:+.2f}) | "
                     f"{s['por']['SELL']['operaciones']} ({s['por']['SELL']['neto']:+.2f}) | {s['final']} |")
    valid = [s for s in summaries if s["operaciones"] >= 30]
    best = max(valid, key=lambda s: s["neto_usdt"]) if valid else None
    lines += ["", "## Veredicto", ""]
    if best is None:
        lines.append("Ninguna variante llegó a 30 operaciones: la muestra es corta para decidir.")
    elif best["neto_usdt"] <= 0:
        lines.append(f"Ninguna variante ganó en este periodo. La que menos perdió fue **{best['variante']}** "
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
        end: Optional[datetime] = None, warmup: int = WARMUP) -> list[dict]:
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
        prepared[sym] = prepare(m5, h1, warmup)
    summaries = [simulate(prepared, v, capital).summary(capital) for v in VARIANTS]
    meta = {"desde": start.date().isoformat(), "hasta": end.date().isoformat(), "capital": capital,
            "simbolos": list(prepared)}
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
