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
"Preregistro 3" (2026-10-13, --preregistro3) adds, on all six years 2020-26 and judged by the leader's amended bar
(every year net > 0 and >= 75% of quarters not negative):
  btc_sma50_200:       long while the daily close is above both its 50-day and its 200-day mean.
  btc_sma50_200_conf2: enters after two consecutive closes above both, leaves on the first close that is not.
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
    "btc_sma200": {"sma": (200,), "stop": None},
    "btc_sma50": {"sma": (50,), "stop": None},
    "btc_sma200_stop10": {"sma": (200,), "stop": TRAIL},
}
# Preregistro 3: the two new rules next to the two Preregistro 2 rules they combine (unchanged)
VARIANTS_3: dict[str, dict] = {
    "btc_sma50": {"sma": (50,), "stop": None},
    "btc_sma200": {"sma": (200,), "stop": None},
    "btc_sma50_200": {"sma": (50, 200), "stop": None, "bar": 3},
    "btc_sma50_200_conf2": {"sma": (50, 200), "stop": None, "confirm": 2, "bar": 3},
}
DESK_FILES = {"2025-10-12": "preregistro_2025-10-12.json", "2026-10-12": "tendencia_2026-10-12.json"}
YEARS = (("2024-10-12", "2025-10-12", "preregistro_2025-10-12.json"),
         ("2025-10-12", "2026-10-12", "tendencia_2026-10-12.json"))
WARMUP_DAYS = 230  # the 200-day mean needs 200 closed days before the first test day
OUT_DIR = Path("docs/research/tendencia")


@dataclass
class Run:
    equity: pd.Series  # daily, at the close
    trades: list[dict] = field(default_factory=list)


def regime_signal(times: pd.DatetimeIndex, close: pd.Series, sma: int | tuple[int, ...],
                  confirm: int = 1) -> np.ndarray:
    """+1 / 0 wanted at each hour from the last closed day (NaN until every mean exists).

    With several means the close must be above all of them. With confirm=n the rule enters only after n
    consecutive closes that qualify and leaves on the first close that does not."""
    daily = close.resample("1D").last().dropna()
    smas = (sma,) if isinstance(sma, int) else sma
    means = [daily.rolling(n).mean() for n in smas]
    ready = pd.concat([m.notna() for m in means], axis=1).all(axis=1)
    above = pd.concat([daily > m for m in means], axis=1).all(axis=1)
    state = above.astype(float)
    if confirm > 1:
        streak = above.astype(int).groupby((~above).cumsum()).cumsum()
        held, vals = False, []
        for ok, k in zip(above, streak):
            held = (held and bool(ok)) or k >= confirm
            vals.append(1.0 if held else 0.0)
        state = pd.Series(vals, index=daily.index)
    want = state.where(ready)
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


def regime_verdict(s: dict, desk: Optional[dict]) -> str:
    """Preregistro 3 (the leader's amended bar for new regime tests), one year."""
    need_q = max(1, math.ceil(len(s["trimestres"]) * 0.75))
    desk_ratio = desk.get("neto_caida") if desk else None
    checks = {"neto positivo": s["neto_pct"] > 0,
              f"{need_q}+ trimestres no negativos": s["trimestres_no_negativos"] >= need_q,
              "neto/caída mejor que la mesa": desk_ratio is None or (
                  s["neto_caida"] is not None and s["neto_caida"] > desk_ratio)}
    failed = [k for k, ok in checks.items() if not ok]
    if failed:
        return "NO se sostiene: falla " + ", ".join(failed)
    return f"cumple (muestra corta: {s['operaciones']} operaciones)"


def year_report(bars: pd.DataFrame, funding: np.ndarray, start: pd.Timestamp, end: pd.Timestamp,
                desk: Optional[dict], funding_points: Optional[int] = None,
                variants: Optional[dict[str, dict]] = None) -> dict:
    times = bars.index
    lo, hi = int(times.searchsorted(start)), int(times.searchsorted(end))
    days = pd.date_range(start, end - rt.DAY, freq="1D", tz="UTC")
    close = bars["close"].dropna().resample("1D").last().ffill()
    hold_r = close.pct_change().reindex(days).fillna(0.0)
    hold = rt.summarize(hold_r, [])
    out: dict = {"desde": start.date().isoformat(), "hasta": end.date().isoformat(), "mesa": desk, "btc": hold,
                 "reglas": {}, "financiacion_real_puntos": funding_points,
                 "financiacion_esperada_puntos": len(days) * 3}
    for name, v in (variants or VARIANTS).items():
        want = regime_signal(times, bars["close"], v["sma"], v.get("confirm", 1))
        run = simulate(bars, funding, want, lo, hi, v["stop"])
        r = rt.returns(run.equity.reindex(days).ffill().fillna(rt.CAPITAL))
        s = rt.summarize(r, run.trades)
        s["dias_comprado_pct"] = round(float(np.nanmean(want[lo:hi] == 1) * 100), 1)
        s["caida_vs_btc_pct"] = round(s["max_caida_pct"] - hold["max_caida_pct"], 2)
        s["captura_de_btc_pct"] = round(s["neto_pct"] / hold["neto_pct"] * 100, 1) if hold["neto_pct"] else None
        # amendment of 2026-10-13 (leader), for new regime tests only, shown for information: a quarter in cash
        # counts as "not negative"
        s["trimestres_no_negativos"] = sum(1 for q in s["trimestres"].values() if q["neto_pct"] >= 0)
        s["veredicto_preregistro2"] = rt.prereg_verdict(s, desk)
        s["criterio"] = v.get("bar", 2)
        s["veredicto"] = regime_verdict(s, desk) if s["criterio"] == 3 else s["veredicto_preregistro2"]
        out["reglas"][name] = s
        print(f"{out['desde']}..{out['hasta']} {name}: neto {s['neto_pct']:+.2f}%, caída {s['max_caida_pct']}%, "
              f"{s['operaciones']} ops — {s['veredicto']}")
    return out


def render(years: list[dict], prereg: int = 2) -> str:
    span = f"{years[0]['desde']} a {years[-1]['hasta']}" if years else ""
    title = ("BTC por encima de las dos medias (preregistro 3, 2026-10-13)" if prereg == 3
             else "BTC comprado solo por encima de su media (preregistro 2, 2026-10-13)")
    lines = [f"# \"BTC régimen\": {title} — {span}", "",
             "Reglas escritas antes de la prueba en `PREREGISTRO.md`. Solo BTC, solo largos, todo el capital sin "
             "apalancamiento; la señal del cierre diario se ejecuta en la apertura de la hora siguiente. Comisión 0,05% "
             "y deslizamiento 0,02% por lado, financiación real. Cada año empieza con 1.000 USDT. La mesa (mesa_r3) "
             "son los números ya publicados para las mismas ventanas (solo donde existen). Caída medida con el cierre diario. "
             "\"No negativos\" cuenta los trimestres con neto ≥ 0 (enmienda del líder del 2026-10-13 para pruebas nuevas "
             "de régimen). Las reglas del preregistro 3 se juzgan con esa enmienda; las del preregistro 2, con su criterio "
             "original (trimestres positivos).", ""]
    if prereg == 3:
        lines += ["**Advertencia de selección:** `btc_sma50_200` y `btc_sma50_200_conf2` son las variantes 4 y 5 de la "
                  "misma familia probadas sobre los mismos datos 2020-2026 que se miraron para elegir la idea. Aunque "
                  "pasen, siguen siendo muestra corta y necesitan práctica hacia adelante antes de contar como evidencia.",
                  ""]
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
    names = list(years[0]["reglas"]) if years else []
    if len(years) > 1:
        lines += ["## Crecimiento compuesto de todos los años", "",
                  "| Estrategia | Crecimiento de 1 | Peor año | Años positivos |", "|---|---|---|---|"]
        for label, nets in [("BTC comprar y mantener", [y["btc"]["neto_pct"] for y in years]),
                            *[(n, [y["reglas"][n]["neto_pct"] for y in years]) for n in names]]:
            growth = math.prod(1 + x / 100 for x in nets)
            lines.append(f"| {label} | ×{growth:.2f} | {min(nets):+.2f}% | {sum(1 for x in nets if x > 0)} de {len(nets)} |")
        lines.append("")
    lines += ["## Veredicto", ""]
    for n in names:
        vs = [y["reglas"][n]["veredicto"] for y in years]
        ok = all(not v.startswith("NO") for v in vs)
        bar = years[0]["reglas"][n].get("criterio", 2)
        lines.append(f"- **{n}** (criterio del preregistro {bar}): "
                     f"{'cumple en todos los años' if ok else 'no cumple en todos los años'} ({'; '.join(vs)}).")
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
    parser.add_argument("--preregistro3", action="store_true",
                        help="las reglas del preregistro 3 (las dos medias) junto a btc_sma50 y btc_sma200")
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    periods = list(YEARS)
    name = "btc_regimen3" if args.preregistro3 else "btc_regimen"
    variants = VARIANTS_3 if args.preregistro3 else VARIANTS
    if args.desde and args.hasta:
        periods = [(a, b, DESK_FILES.get(b, "")) for a, b, _ in yearly(args.desde, args.hasta)]
        name = f"{name}_{args.desde}_{args.hasta}"
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
                                 points, variants))
    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / f"{name}.json").write_text(json.dumps({"años": years}, indent=1, default=str), encoding="utf-8")
    report = render(years, 3 if args.preregistro3 else 2)
    (args.salida / f"{name}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
