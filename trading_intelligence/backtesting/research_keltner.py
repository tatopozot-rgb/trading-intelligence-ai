"""
Keltner channel breakout (Linda Raschke's version) on BTC and ETH daily candles (leader, 2026-10-24), research only.

Preregistered in docs/research/keltner/PREREGISTRO.md before any run; rules from docs/inteligencia/BOTS_PUBLICOS.md
(2026-10-24). EMA 20, Wilder ATR 10, multiplier 2, never tuned. Long only: buy at the next open after a close above
the upper band; sell at the next open after a close below the EMA. Same three decisive rows, simulator and report
as research_sar; in B the intraday stop is the closer of the desk stop and the previous close's EMA (it only rises).
Public Binance data only: no account, no key, no orders. Nothing touches config/ or live/.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import research_macd as rmc
from trading_intelligence.backtesting import research_sar as rs

EMA_N, ATR_N, MULT = 20, 10, 2.0
DECISIVE_N = 304
OUT_DIR = Path("docs/research/keltner")
ROWS = rs.ROWS  # A both coins, B both coins, B on BTC alone


def channel(f: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """(EMA 20, upper band) per day."""
    h, lo, c = f["high"], f["low"], f["close"]
    ema = c.ewm(span=EMA_N, adjust=False).mean()
    tr = pd.concat([h - lo, (h - c.shift()).abs(), (lo - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / ATR_N, adjust=False).mean()
    return ema.to_numpy(float), (ema + MULT * atr).to_numpy(float)


def signals(f: pd.DataFrame) -> rmc.Cross:
    ema, upper = channel(f)
    c = f["close"].to_numpy(float)
    return rmc.Cross(c > upper, c < ema)


def trail_levels(f: pd.DataFrame) -> np.ndarray:
    """The previous close's EMA, known at the day's open."""
    ema, _ = channel(f)
    return np.r_[np.nan, ema[:-1]]


def prepare(frames: dict[str, pd.DataFrame], funding: dict[str, pd.Series]) -> tuple[rmc.Market, dict]:
    mk = rmc.prepare(frames, funding)
    mk.cross = {k: signals(f) for k, f in frames.items()}
    return mk, {k: trail_levels(f) for k, f in frames.items()}


def render(years: list[dict], n: int) -> str:
    body = rs.render(years, n)
    head = ("# Ruptura del canal de Keltner (Raschke) en BTC y ETH diario\n\n"
            "Preregistro: `docs/research/keltner/PREREGISTRO.md`, escrito antes de correr. EMA 20, ATR de Wilder 10 y "
            "multiplicador 2 fijos; compra tras un cierre sobre la banda de arriba, vende tras un cierre bajo la EMA; "
            "solo compras, órdenes en la apertura siguiente; 0,05% de comisión y 0,02% de deslizamiento por lado; "
            "financiación real; 1.000 USDT. B: stop dentro del día en el más cercano entre el de la mesa (`plan_exits`, "
            "300 velas diarias) y la EMA del cierre anterior, 2% de riesgo, régimen b y sin entradas en días FOMC/IPC. "
            f"Sharpe deflactado con N = {n} decisorias.\n")
    return head + body[body.index("\n## Veredicto"):]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Ruptura del canal de Keltner en BTC y ETH diario (investigación)")
    parser.add_argument("--decisorias", type=int, default=DECISIVE_N)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    frames, funding = rmc.load()
    mk, trails = prepare(frames, funding)
    years = [rs.year(mk, trails, a, b, args.decisorias) for a, b in rmc.YEARS]
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"keltner_{stamp}.json").write_text(json.dumps(years, indent=1, default=str), encoding="utf-8")
    report = render(years, args.decisorias)
    (args.salida / f"keltner_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
