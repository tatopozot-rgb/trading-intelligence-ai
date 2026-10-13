"""
"BTC régimen": hold BTC long at 1x only while its daily close is above a simple moving average (research only:
public data, no key, no orders). Rules pre-registered on 2026-10-13 in docs/research/tendencia/PREREGISTRO.md
("Preregistro 2") before any test:
  btc_sma200:        long while the daily close is above its 200-day mean, otherwise cash.
  btc_sma50:         the same with the 50-day mean.
  btc_sma200_stop10: btc_sma200 plus a 10% trailing stop from the highest high since entry; after a stop it waits
                     for a fresh cross (a close below the mean, then one above) before buying again.
The signal of a daily close acts at the next hour's open. All the capital (no leverage), fees 0.05% and slippage
0.02% per side, the real funding of every 8 h accrued hourly. Each test year starts with 1000 USDT.
Both years are measured in one run against BTC buy-and-hold on the same dates and against mesa_r3, whose numbers
come from the reports already committed for those windows (tendencia_2026-10-12.json, preregistro_2025-10-12.json).

    python -m trading_intelligence.backtesting.research_tendencia_regimen
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import research_tendencia as rt
from trading_intelligence.backtesting import two_way_backtest as tw

SYMBOL = "BTCUSDT"
TRAIL = 0.10
VARIANTS: dict[str, dict] = {
    "btc_sma200": {"sma": 200, "stop": None},
    "btc_sma50": {"sma": 50, "stop": None},
    "btc_sma200_stop10": {"sma": 200, "stop": TRAIL},
}
YEARS = (("2024-10-12", "2025-10-12", "preregistro_2025-10-12.json"),
         ("2025-10-12", "2026-10-12", "tendencia_2026-10-12.json"))
WARMUP_DAYS = 230  # the 200-day mean needs 200 closed days before the first test day
OUT_DIR = Path("docs/research/tendencia")


@dataclass
class Run:
    equity: pd.Series  # daily, at the close
    trades: list[dict] = field(default_factory=list)


def regime_signal(times: pd.DatetimeIndex, close: pd.Series, sma: int) -> np.ndarray:
    """+1 / 0 wanted at each hour from the last closed day (NaN until the mean exists)."""
    daily = close.resample("1D").last().dropna()
    mean = daily.rolling(sma).mean()
    want = (daily > mean).astype(float).where(mean.notna())
    want.index = want.index + rt.DAY  # known once the day has closed
    return want.reindex(times, method="ffill").to_numpy()


def simulate(bars: pd.DataFrame, funding: np.ndarray, want: np.ndarray, start: int, end: int,
             stop: Optional[float] = None, capital: float = rt.CAPITAL) -> Run:
    o, h, low, c = (bars[k].to_numpy() for k in ("open", "high", "low", "close"))
    times = bars.index
    cash, qty, entry, fee_in, fund, peak = capital, 0.0, 0.0, 0.0, 0.0, 0.0
    entry_at: Optional[pd.Timestamp] = None
    armed = True  # False after a trailing stop until the regime turns off and on again
    eq = np.full(len(times), np.nan)
    run = Run(pd.Series(dtype=float))
    last = math.nan

    def sell(raw: float, why: str, t: pd.Timestamp) -> None:
        nonlocal cash, qty
        price = raw * (1 - rt.SLIP)
        fee_out = price * qty * rt.FEE
        cash += price * qty - fee_out - fund
        pnl = (price - entry) * qty - fee_in - fee_out - fund
        run.trades.append({"symbol": SYMBOL, "side": "BUY", "entry_at": str(entry_at), "exit_at": t.isoformat(),
                           "why": why, "pnl": pnl, "fees": fee_in + fee_out, "funding": fund,
                           "ret_pct": pnl / (qty * entry) * 100})
        qty = 0.0

    prev_want = math.nan
    for i in range(start, end):
        t = times[i]
        w = want[i]
        if not math.isnan(o[i]):
            changed = i == start or w != prev_want
            if changed and not math.isnan(w):
                if w == 0:
                    armed = True
                if qty > 0 and w == 0:
                    sell(o[i], "régimen", t)
                elif qty == 0 and w == 1 and armed:
                    price = o[i] * (1 + rt.SLIP)
                    qty = cash / (price * (1 + rt.FEE))
                    entry, fee_in, fund, peak, entry_at = price, qty * price * rt.FEE, 0.0, price, t
                    cash -= qty * price + fee_in
            prev_want = w
        if qty > 0 and not math.isnan(c[i]):
            fund += qty * c[i] * funding[i] / 8
            if stop is not None and low[i] <= peak * (1 - stop):
                sell(min(o[i], peak * (1 - stop)), "stop", t)
                armed = False
            else:
                peak = max(peak, h[i])
        if not math.isnan(c[i]):
            last = c[i]
        mark = entry if math.isnan(last) else last
        eq[i] = cash + qty * mark - fund if qty else cash
    if qty > 0:
        sell(last, "fin del periodo", times[end - 1])
        eq[end - 1] = cash
    run.equity = pd.Series(eq[start:end], index=times[start:end]).resample("1D").last().ffill()
    return run


def year_report(bars: pd.DataFrame, funding: np.ndarray, start: pd.Timestamp, end: pd.Timestamp,
                desk: Optional[dict], funding_points: Optional[int] = None) -> dict:
    times = bars.index
    lo, hi = int(times.searchsorted(start)), int(times.searchsorted(end))
    days = pd.date_range(start, end - rt.DAY, freq="1D", tz="UTC")
    close = bars["close"].dropna().resample("1D").last().ffill()
    hold_r = close.pct_change().reindex(days).fillna(0.0)
    hold = rt.summarize(hold_r, [])
    out: dict = {"desde": start.date().isoformat(), "hasta": end.date().isoformat(), "mesa": desk, "btc": hold,
                 "reglas": {}, "financiacion_real_puntos": funding_points,
                 "financiacion_esperada_puntos": len(days) * 3}
    for name, v in VARIANTS.items():
        want = regime_signal(times, bars["close"], v["sma"])
        run = simulate(bars, funding, want, lo, hi, v["stop"])
        r = rt.returns(run.equity.reindex(days).ffill().fillna(rt.CAPITAL))
        s = rt.summarize(r, run.trades)
        s["dias_comprado_pct"] = round(float(np.nanmean(want[lo:hi] == 1) * 100), 1)
        s["caida_vs_btc_pct"] = round(s["max_caida_pct"] - hold["max_caida_pct"], 2)
        s["captura_de_btc_pct"] = round(s["neto_pct"] / hold["neto_pct"] * 100, 1) if hold["neto_pct"] else None
        # amendment of 2026-10-13 (leader), for new regime tests only, shown for information: a quarter in cash
        # counts as "not negative"
        s["trimestres_no_negativos"] = sum(1 for q in s["trimestres"].values() if q["neto_pct"] >= 0)
        s["veredicto"] = rt.prereg_verdict(s, desk)
        out["reglas"][name] = s
        print(f"{out['desde']}..{out['hasta']} {name}: neto {s['neto_pct']:+.2f}%, caída {s['max_caida_pct']}%, "
              f"{s['operaciones']} ops — {s['veredicto']}")
    return out


def render(years: list[dict]) -> str:
    span = f"{years[0]['desde']} a {years[-1]['hasta']}" if years else ""
    lines = [f"# \"BTC régimen\": BTC comprado solo por encima de su media (preregistro 2, 2026-10-13) — {span}", "",
             "Reglas escritas antes de la prueba en `PREREGISTRO.md`. Solo BTC, solo largos, todo el capital sin "
             "apalancamiento; la señal del cierre diario se ejecuta en la apertura de la hora siguiente. Comisión 0,05% "
             "y deslizamiento 0,02% por lado, financiación real. Cada año empieza con 1.000 USDT. La mesa (mesa_r3) "
             "son los números ya publicados para las mismas ventanas (solo donde existen). Caída medida con el cierre diario. "
             "\"No negativos\" cuenta los trimestres con neto ≥ 0 (enmienda del líder del 2026-10-13 para pruebas nuevas "
             "de régimen; aquí solo informativo: el veredicto usa el criterio del preregistro).", ""]
    for y in years:
        hold, desk = y["btc"], y.get("mesa")
        lines += [f"## {y['desde']} a {y['hasta']}", "",
                  "| Estrategia | Operaciones | Neto % | Máx. caída | Neto/caída | Días comprado | Caída vs BTC | "
                  "Captura de BTC | Trimestres positivos | No negativos | Veredicto |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        if desk:
            lines.append(f"| mesa_r3 | {desk['operaciones']} | {desk['neto_pct']:+.2f}% | {desk['max_caida_pct']}% | "
                         f"{rt._fmt(desk['neto_caida'])} | — | — | — | {desk['trimestres_positivos']} de "
                         f"{len(desk['trimestres'])} | — | referencia |")
        lines.append(f"| BTC comprar y mantener | 1 | {hold['neto_pct']:+.2f}% | {hold['max_caida_pct']}% | "
                     f"{rt._fmt(hold['neto_caida'])} | 100% | 0 | 100% | {hold['trimestres_positivos']} de "
                     f"{len(hold['trimestres'])} | — | referencia |")
        for name, s in y["reglas"].items():
            lines.append(f"| {name} | {s['operaciones']} | {s['neto_pct']:+.2f}% | {s['max_caida_pct']}% | "
                         f"{rt._fmt(s['neto_caida'])} | {s['dias_comprado_pct']}% | {s['caida_vs_btc_pct']:+.2f} pts | "
                         f"{rt._fmt(s['captura_de_btc_pct'])}% | {s['trimestres_positivos']} de {len(s['trimestres'])} "
                         f"| {s.get('trimestres_no_negativos', '—')} | {s['veredicto']} |")
        rows = [("mesa_r3", desk), ("BTC", hold), *y["reglas"].items()]
        quarters = sorted({q for _, s in rows if s for q in s["trimestres"]})
        lines += ["", "| Por trimestre | " + " | ".join(quarters) + " |", "|---|" + "---|" * len(quarters)]
        for name, s in rows:
            if s:
                lines.append(f"| {name} | " + " | ".join(
                    "—" if q not in s["trimestres"] else f"{s['trimestres'][q]['neto_pct']:+.2f}%" for q in quarters)
                    + " |")
        fp = y.get("financiacion_real_puntos")
        if fp is not None:
            lines += ["", f"Financiación real del perpetuo: {fp} de {y['financiacion_esperada_puntos']} liquidaciones de 8 h "
                          "en el archivo de Binance; donde falta se usa 0,01% por 8 h."]
        lines.append("")
    both = {n: [y["reglas"][n]["veredicto"] for y in years] for n in VARIANTS}
    lines += ["## Veredicto", ""]
    for n, vs in both.items():
        ok = all(not v.startswith("NO") for v in vs)
        lines.append(f"- **{n}**: {'pasa los criterios 1-3 en todos los años' if ok else 'no pasa en todos los años'} "
                     f"({'; '.join(vs)}).")
    lines += ["", "Advertencias: una regla de régimen opera pocas veces, así que pocos años son pocos cambios de régimen; "
              "el precio Spot aproxima al perpetuo. Un resultado pasado no promete uno futuro."]
    return "\n".join(lines) + "\n"


def yearly(desde: str, hasta: str) -> list[tuple[str, str, str]]:
    """Consecutive one-year test periods from `desde` to `hasta` (no desk report for them)."""
    out, a, end = [], pd.Timestamp(desde), pd.Timestamp(hasta)
    while a < end:
        b = min(a + pd.DateOffset(years=1), end)
        out.append((a.date().isoformat(), b.date().isoformat(), ""))
        a = b
    return out


def desk_from(report: Path) -> Optional[dict]:
    try:
        return json.loads(report.read_text(encoding="utf-8")).get("mesa")
    except (OSError, ValueError):
        return None


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="BTC régimen (preregistro 2)")
    parser.add_argument("--desde", type=str, default=None, help="AAAA-MM-DD: años de prueba desde aquí (sin mesa)")
    parser.add_argument("--hasta", type=str, default=None, help="AAAA-MM-DD: fin del último año de prueba")
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    periods = list(YEARS)
    name = "btc_regimen"
    if args.desde and args.hasta:
        periods = yearly(args.desde, args.hasta)
        name = f"btc_regimen_{args.desde}_{args.hasta}"
    first = datetime.strptime(periods[0][0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    last = datetime.strptime(periods[-1][1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start = first - timedelta(days=WARMUP_DAYS)
    times = pd.date_range(start, last - timedelta(hours=1), freq="1h", tz="UTC")
    bars = tw.fetch(SYMBOL, "1h", start, last)[["open", "high", "low", "close"]].reindex(times)
    fund = tw.fetch_funding(SYMBOL, start, last)
    m = rt.build_market({SYMBOL: bars}, {SYMBOL: fund}, times)
    print(f"{SYMBOL}: {int(bars['close'].notna().sum())} velas de 1 h, financiación {len(fund)} puntos")
    years = []
    for a, b, f in periods:
        ta, tb = pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")
        points = int(((fund.index >= ta) & (fund.index < tb)).sum()) if not fund.empty else 0
        years.append(year_report(m.bars[SYMBOL], m.funding[SYMBOL], ta, tb, desk_from(args.salida / f) if f else None,
                                 points))
    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / f"{name}.json").write_text(json.dumps({"años": years}, indent=1, default=str), encoding="utf-8")
    report = render(years)
    (args.salida / f"{name}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
