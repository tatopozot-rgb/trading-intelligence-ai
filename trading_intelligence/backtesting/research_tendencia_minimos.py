"""
Why does the mesa_r3 replay refuse so many entries for Binance's minimum notional in some windows (105 in the window
from 2025-10-12, 190 in the one from 2025-08-08, against 0-24 elsewhere)? Leader's task, 2026-10-13. Research only:
public data, no key, no orders.

Replays only those two 30-day windows exactly as research_tendencia.desk_window does (mesa_r3, 5-minute bars,
1000 USDT, the desk's sizing) and records every refused entry with its sizing: the notional allowed by the risk to the
stop, by the 50% position cap and by the room left under 1x, against the coin's minimum. Consecutive refusals of the
same coin and side are one "episode" (the same signal seen bar after bar). For each episode it looks ahead 24 h, as
the desk does for its vetoes: would the stop or the 3R target have been touched first?

    python -m trading_intelligence.backtesting.research_tendencia_minimos
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from trading_intelligence.backtesting import research_tendencia as rt
from trading_intelligence.backtesting import two_way_backtest as tw

WINDOWS = (("2025-08-08", "2025-09-07"), ("2025-10-12", "2025-11-11"))
OUT_DIR = Path("docs/research/tendencia")
LIMITS = ("by_risk", "by_position", "by_room")
LABEL = {"by_risk": "riesgo hasta el stop", "by_position": "tope de 50% por posición",
         "by_room": "capital ya usado (1x)"}


def binding(e: dict) -> str:
    """Which cap set the size of a refused entry."""
    return min(LIMITS, key=lambda k: e[k])


def episodes(events: list[dict]) -> list[dict]:
    """Group refusals of the same coin and side on consecutive 5-minute bars into one episode."""
    out: list[dict] = []
    last: dict[tuple[str, str], dict] = {}
    for e in sorted(events, key=lambda e: (e["symbol"], e["i"])):
        key = (e["symbol"], e["side"])
        ep = last.get(key)
        if ep is not None and e["i"] == ep["last_i"] + 1:
            ep["bars"] += 1
            ep["last_i"] = e["i"]
            continue
        ep = {**e, "bars": 1, "last_i": e["i"], "limit": binding(e)}
        out.append(ep)
        last[key] = ep
    return out


def summarize(events: list[dict], eps: list[dict], desk_trades: list[dict]) -> dict:
    wins = sum(1 for t in desk_trades if t["pnl"] > 0)
    outcome = Counter(ep.get("outcome", "sin resultado") for ep in eps)
    decided = outcome["evitó pérdida"] + outcome["dejó pasar ganancia"]
    return {
        "rechazos": len(events), "episodios": len(eps),
        "por_moneda": dict(Counter(e["symbol"] for e in events).most_common()),
        "episodios_por_moneda": dict(Counter(ep["symbol"] for ep in eps).most_common()),
        "limite": {LABEL[k]: v for k, v in Counter(binding(e) for e in events).items()},
        "posiciones_abiertas": dict(sorted(Counter(e["open"] for e in events).items())),
        "uso_capital_pct_mediana": round(float(pd.Series([e["used"] / e["equity"] * 100 for e in events]).median()), 1)
        if events else None,
        "stop_pct_mediana": round(float(pd.Series([e["dist_pct"] for e in events]).median()), 2) if events else None,
        "barras_por_episodio_mediana": float(pd.Series([ep["bars"] for ep in eps]).median()) if eps else None,
        "resultado_24h": dict(outcome),
        "acierto_episodios_pct": round(outcome["dejó pasar ganancia"] / decided * 100, 1) if decided else None,
        "mesa_operaciones": len(desk_trades),
        "mesa_acierto_pct": round(wins / len(desk_trades) * 100, 1) if desk_trades else None,
    }


def window_skips(ws: pd.Timestamp, we: pd.Timestamp, symbols: list[str], fetcher: tw.Fetcher = tw.fetch,
                 extras: rt.Extras = rt._public_extras) -> dict:
    start, end = ws.to_pydatetime(), we.to_pydatetime()
    warm = start - timedelta(minutes=5 * tw.WARMUP)
    prepared = {}
    for sym in symbols:
        try:
            m5 = fetcher(sym, "5m", warm, end)
            h1 = fetcher(sym, "1h", warm - timedelta(hours=tw.SLOW + 5), end)
        except Exception:  # noqa: BLE001 - one symbol's data must not stop the others
            continue
        top, fund = extras(sym, warm, end)
        prepared[sym] = tw.prepare(m5, h1, tw.WARMUP, top, fund)
    events: list[dict] = []
    res = tw.simulate(prepared, rt.DESK, rt.CAPITAL, on_skip=events.append)
    eps = episodes(events)
    for ep in eps:
        ep["outcome"] = tw._veto_outcome(prepared[ep["symbol"]], ep["i"], ep["side"], ep["stop"], ep["target"])
    summary = summarize(events, eps, res.trades)
    sample = [{k: (str(v) if k == "at" else (round(v, 4) if isinstance(v, float) else v))
               for k, v in ep.items() if k not in ("i", "last_i")} for ep in eps]
    return {"desde": ws.date().isoformat(), "hasta": we.date().isoformat(), **summary, "episodios_detalle": sample}


def _job(job: tuple) -> dict:
    ws, we, symbols = job
    return window_skips(ws, we, symbols)


def render(results: list[dict]) -> str:
    lines = ["# Rechazos por mínimo de Binance en la mesa (mesa_r3): qué son y si sesgan el resultado", "",
             "Se repiten solo las dos ventanas con picos de rechazos, con las mismas reglas que el informe de tendencia "
             "(mesa_r3, velas de 5 min, 1.000 USDT por ventana, tamaño de la mesa). Cada rechazo guarda cuánto permitía "
             "cada tope: el riesgo hasta el stop, el 50% por posición y el capital libre con 1x. Un \"episodio\" junta "
             "los rechazos de la misma moneda y sentido en velas seguidas (la misma señal vista vela tras vela). Para "
             "cada episodio se mira 24 h hacia adelante, como con los vetos: ¿tocaba antes el stop o la meta de 3R?", ""]
    for r in results:
        lines += [f"## {r['desde']} a {r['hasta']}", "",
                  f"- Rechazos: **{r['rechazos']}**, en **{r['episodios']} episodios** (mediana de "
                  f"{r['barras_por_episodio_mediana']} velas seguidas por episodio).",
                  f"- Por moneda (rechazos): {r['por_moneda']}; episodios: {r['episodios_por_moneda']}.",
                  f"- Tope que fijó el tamaño: {r['limite']}.",
                  f"- Posiciones abiertas en ese momento: {r['posiciones_abiertas']}; capital ya usado (mediana): "
                  f"{r['uso_capital_pct_mediana']}%; distancia al stop (mediana): {r['stop_pct_mediana']}%.",
                  f"- Qué habría pasado en 24 h (por episodio): {r['resultado_24h']}; acierto de los episodios con "
                  f"resultado: {r['acierto_episodios_pct']}% frente a {r['mesa_acierto_pct']}% de las "
                  f"{r['mesa_operaciones']} operaciones que la mesa sí hizo en la ventana.", ""]
    return "\n".join(lines) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Rechazos por mínimo de Binance en mesa_r3")
    parser.add_argument("--simbolos", nargs="+", default=list(tw.SYMBOLS))
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    jobs = [(pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC"), args.simbolos) for a, b in WINDOWS]
    with ProcessPoolExecutor(max_workers=len(jobs)) as pool:
        results = list(pool.map(_job, jobs))
    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / "minimos_mesa.json").write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    report = render(results)
    (args.salida / "minimos_mesa_datos.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
