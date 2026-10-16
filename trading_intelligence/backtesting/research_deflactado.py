"""
Deflated Sharpe ratio (Bailey and López de Prado, 2014) of the gold London breakout, 2025-26, research only.

Method preregistered in docs/research/rsi2/PREREGISTRO.md (part 2) before any run. N is the number of tests in
docs/research/REGISTRO_PRUEBAS.md, passed with --pruebas (all) and --decisorias (decisive only). Daily returns are
the change of the marked capital between the last 1h close of each weekday. V, the variance of the Sharpe ratios
across tests, is 1/T (a test with no edge) and, as sensitivity, the measured variance of the 12 research_oro rows.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from scipy import stats as st

from trading_intelligence.backtesting import research_mesa as rm
from trading_intelligence.backtesting import research_oro as ro

EULER = 0.5772156649
YEAR = ro.YEARS[1]
TARGET = ("oro", "londres")
PASS_DSR = 0.95
OUT_DIR = Path("docs/research/deflactado")


def expected_max_sr(n: int, v: float) -> float:
    """SR0: the best Sharpe expected from n tests with no edge whose Sharpe ratios vary with variance v."""
    if n <= 1:
        return 0.0
    z = st.norm.ppf
    return float(np.sqrt(v) * ((1 - EULER) * z(1 - 1 / n) + EULER * z(1 - 1 / (n * np.e))))


def deflated_sharpe(sr: float, t: int, skew: float, kurt: float, n: int, v: float) -> float:
    """Probability that the true Sharpe is above SR0 (per-period sr, kurt not in excess)."""
    sr0 = expected_max_sr(n, v)
    den = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    return float(st.norm.cdf((sr - sr0) * np.sqrt(t - 1) / np.sqrt(den)))


def daily_returns(equity: list[float], index: pd.DatetimeIndex, capital: float = ro.CAPITAL) -> pd.Series:
    e = pd.Series(equity, index=index[-len(equity):]) if equity else pd.Series(dtype=float)
    last = e.groupby(e.index.floor("D")).last()
    return pd.concat([pd.Series([capital]), last.reset_index(drop=True)]).pct_change().dropna()


def moments(r: pd.Series) -> dict:
    sd = float(r.std(ddof=1))
    return {"T": int(len(r)), "sr_dia": float(r.mean() / sd) if sd > 0 else 0.0,
            "asimetria": float(st.skew(r)), "curtosis": float(st.kurtosis(r, fisher=False)),
            "sr_anual": float(r.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0, "neto_pct": float((1 + r).prod() * 100 - 100)}


def rows(data: dict[str, tuple[pd.DataFrame, pd.DataFrame]], events: list[pd.Timestamp]) -> dict[str, dict]:
    a, b = YEAR
    lo_t, hi_t = pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")
    out: dict[str, dict] = {}
    for asset, (hourly, daily) in data.items():
        h_year = hourly[(hourly.index >= lo_t) & (hourly.index < hi_t)]
        d_cut, h_cut = daily[daily.index < hi_t], hourly[hourly.index < hi_t]
        for mult, label in ((1.0, ""), (2.0, ", costes ×2")):
            costs = ro.Costs(asset, mult)
            d0, h0 = int(d_cut.index.searchsorted(lo_t)), int(h_cut.index.searchsorted(lo_t))
            books = {"londres": (ro.london(h_year, costs), h_year.index),
                     "tortugas": (ro.turtle(d_cut, costs, d0), d_cut.index[d0:]),
                     "noticia": (ro.news(h_cut, costs, h0, events), h_cut.index[h0:])}
            for key, (book, idx) in books.items():
                out[f"{asset} · {key}{label}"] = moments(daily_returns(book.equity, idx))
    return out


def evaluate(table: dict[str, dict], n_all: int, n_decisive: int) -> dict[str, Any]:
    m = table[f"{TARGET[0]} · {TARGET[1]}"]
    v_null = 1 / m["T"]
    v_emp = float(np.var([r["sr_dia"] for r in table.values()], ddof=1))
    cases = []
    for n, n_label in ((1, "sin deflactar"), (n_decisive, "solo decisorias"), (n_all, "todas las pruebas")):
        for v, v_label in ((v_null, "V = 1/T"), (v_emp, "V medida en research_oro")):
            if n == 1 and v_label != "V = 1/T":
                continue
            sr0 = expected_max_sr(n, v)
            d = deflated_sharpe(m["sr_dia"], m["T"], m["asimetria"], m["curtosis"], n, v)
            cases.append({"N": n, "que": n_label, "V": v_label, "sr0_anual": sr0 * np.sqrt(252), "dsr": d,
                          "pasa": d >= PASS_DSR})
    return {"londres_oro": m, "v_null": v_null, "v_emp": v_emp, "cases": cases}


def render(res: dict[str, Any], table: dict[str, dict]) -> str:
    m = res["londres_oro"]
    main_case = next(c for c in res["cases"] if c["que"] == "todas las pruebas" and c["V"] == "V = 1/T")
    L = ["# Sharpe deflactado de la ruptura de Londres en oro, 2025-10-13 → 2026-10-13", "",
         "Método preregistrado en `docs/research/rsi2/PREREGISTRO.md` (parte 2) antes de correr; número de pruebas de "
         "`docs/research/REGISTRO_PRUEBAS.md`. Bailey y López de Prado (2014).", "",
         "## Veredicto", "",
         f"- **{'Pasa' if main_case['pasa'] else 'No pasa'} el segundo listón:** con N = {main_case['N']} pruebas, el "
         f"Sharpe deflactado es {main_case['dsr']:.2f} (listón {PASS_DSR}).",
         f"- Sharpe anual de Londres en oro: {m['sr_anual']:.2f}, sobre {m['T']} días hábiles (neto {m['neto_pct']:+.1f}%, "
         f"asimetría {m['asimetria']:.2f}, curtosis {m['curtosis']:.1f}).", "",
         "## Casos", "", "| N | Qué cuenta | V | Mejor Sharpe anual esperado por suerte | Sharpe deflactado | Pasa |",
         "|---|---|---|---|---|---|"]
    for c in res["cases"]:
        L.append(f"| {c['N']} | {c['que']} | {c['V']} | {c['sr0_anual']:.2f} | {c['dsr']:.3f} | {'sí' if c['pasa'] else 'no'} |")
    L += ["", "## Las 12 filas de research_oro en 2025-26 (para V medida)", "",
          "| Fila | Días | Sharpe anual | Neto % | Asimetría | Curtosis |", "|---|---|---|---|---|---|"]
    for name, r in table.items():
        L.append(f"| {name} | {r['T']} | {r['sr_anual']:.2f} | {r['neto_pct']:+.1f}% | {r['asimetria']:.2f} | "
                 f"{r['curtosis']:.1f} |")
    L += ["", "Cómo leerlo: el Sharpe deflactado es la probabilidad de que el Sharpe real sea mayor que el mejor que "
          "saldría por pura suerte después de tantas pruebas. Con 0,95 o más se cree; por debajo, el resultado puede ser "
          "suerte. Las 12 filas de oro y BTC son pocas y muy distintas entre sí, así que la V medida es solo orientativa."]
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Sharpe deflactado de Londres en oro (investigación)")
    parser.add_argument("--pruebas", type=int, required=True, help="total de pruebas del registro único")
    parser.add_argument("--decisorias", type=int, required=True, help="solo las pruebas decisorias")
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    data = {asset: ro.load(sym, weekdays_only=asset == "oro") for asset, sym in ro.ASSETS.items()}
    table = rows(data, rm.macro_events())
    res = evaluate(table, args.pruebas, args.decisorias)
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"deflactado_{stamp}.json").write_text(json.dumps({"table": table, **res}, indent=1, default=str),
                                                          encoding="utf-8")
    report = render(res, table)
    (args.salida / f"deflactado_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
