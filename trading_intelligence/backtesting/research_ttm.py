"""
John Carter's TTM Squeeze on BTC and ETH daily candles (leader, 2026-10-21), research only.

Preregistered in docs/research/ttm/PREREGISTRO.md before any run; rules from docs/inteligencia/BOTS_PUBLICOS.md
(2026-10-21). Bollinger 20/2 inside Keltner 20/1.5 ATR is the squeeze; the momentum is the 20-day linear-regression
value of close minus the mean of the Donchian midpoint and the SMA20. Long only: buy at the next open after the first
close out of a squeeze with a positive, rising momentum; sell at the next open after two closes in a row with a
falling momentum. Versions A and B run on research_macd.simulate (B: desk stop with 2% risk, regime b, no entries
on FOMC/CPI days). Public Binance data only: no account, no key, no orders. Nothing touches config/ or live/.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import research_ichimoku as ri
from trading_intelligence.backtesting import research_macd as rmc

LENGTH, BB_MULT, KC_MULT = 20, 2.0, 1.5
DECISIVE_N = 296
OUT_DIR = Path("docs/research/ttm")


def linreg_last(x: pd.Series, n: int) -> pd.Series:
    """Fitted value at the last point of the least-squares line over the last n values."""
    t = np.arange(n, dtype=float)
    tc = t - t.mean()

    def fit(w: np.ndarray) -> float:
        return float(w.mean() + (tc @ (w - w.mean())) / (tc @ tc) * tc[-1])

    return x.rolling(n).apply(fit, raw=True)


def squeeze(f: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """(squeeze on, momentum) per day."""
    h, lo, c = f["high"], f["low"], f["close"]
    sma = c.rolling(LENGTH).mean()
    sd = c.rolling(LENGTH).std(ddof=0)
    tr = pd.concat([h - lo, (h - c.shift()).abs(), (lo - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(LENGTH).mean()
    on = ((sma + BB_MULT * sd) < (sma + KC_MULT * atr)) & ((sma - BB_MULT * sd) > (sma - KC_MULT * atr))
    mid = (h.rolling(LENGTH).max() + lo.rolling(LENGTH).min()) / 2
    mom = linreg_last(c - (mid + sma) / 2, LENGTH)
    return on.to_numpy(bool) & atr.notna().to_numpy(), mom.to_numpy(float)


def signals(f: pd.DataFrame) -> rmc.Cross:
    on, mom = squeeze(f)
    prev_on = np.r_[False, on[:-1]]
    m1, m2 = np.r_[np.nan, mom[:-1]], np.r_[np.nan, np.nan, mom[:-2]]
    with np.errstate(invalid="ignore"):
        enter = prev_on & ~on & (mom > 0) & (mom > m1)
        leave = (mom < m1) & (m1 < m2)
    return rmc.Cross(enter, leave)


def prepare(frames: dict[str, pd.DataFrame], funding: dict[str, pd.Series]) -> rmc.Market:
    mk = rmc.prepare(frames, funding)
    mk.cross = {k: signals(f) for k, f in frames.items()}
    return mk


def render(years: list[dict], n: int) -> str:
    body = ri.render(years, n)
    head = ("# TTM Squeeze de John Carter en BTC y ETH diario\n\n"
            "Preregistro: `docs/research/ttm/PREREGISTRO.md`, escrito antes de correr. Bollinger 20/2 dentro de Keltner "
            "20/1,5 ATR, impulso por regresión lineal de 20 días; solo compras, órdenes en la apertura siguiente; 0,05% "
            "de comisión y 0,02% de deslizamiento por lado; financiación real; 1.000 USDT. B: stop de la mesa "
            "(`plan_exits`, 300 velas diarias) con 2% de riesgo, régimen b y sin entradas en días FOMC/IPC. Sharpe "
            f"deflactado con N = {n} decisorias.\n")
    return head + body[body.index("\n## Veredicto"):]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="TTM Squeeze en BTC y ETH diario (investigación)")
    parser.add_argument("--decisorias", type=int, default=DECISIVE_N)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    frames, funding = rmc.load()
    mk = prepare(frames, funding)
    years = [rmc.year(mk, a, b, args.decisorias) for a, b in rmc.YEARS]
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"ttm_{stamp}.json").write_text(json.dumps(years, indent=1, default=str), encoding="utf-8")
    report = render(years, args.decisorias)
    (args.salida / f"ttm_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
