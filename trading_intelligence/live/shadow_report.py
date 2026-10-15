"""Daily report of the futures practice account (SHADOW, fictitious money).

The leader and GPT Work study it every day to learn how the desk trades: what wins, what loses, which
vetoes helped. It reads only the practice files the operator writes (``paper.json`` and ``state.json``)
and holds no balance of a real account, so it can go to GitHub.

    python -m trading_intelligence.live.shadow_report --dir live_runs/futures_auto/shadow --salida docs/shadow_futures
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

MIN_SAMPLE = 30  # trades before any conclusion counts
ECUADOR = timezone(timedelta(hours=-5))  # the owner's day; the report runs at 19:30 there, 00:30 UTC of the next day


def _local_day(at: Any) -> Optional[date]:
    """The Ecuador date of a trade's ISO timestamp (naive timestamps are UTC)."""
    try:
        t = datetime.fromisoformat(str(at))
    except ValueError:
        return None
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(ECUADOR).date()


def _f(x: Any) -> float:
    return float(x) if x not in (None, "") else 0.0


def stats(trades: list[dict]) -> dict:
    pnl = [_f(t["pnl"]) for t in trades]
    rs = [_f(t["r"]) for t in trades if t.get("r") not in (None, "")]
    wins, losses = [p for p in pnl if p > 0], [p for p in pnl if p <= 0]
    return {"operaciones": len(pnl), "ganadas": len(wins),
            "acierto_pct": round(len(wins) / len(pnl) * 100, 1) if pnl else 0.0,
            "neto_usdt": round(sum(pnl), 4),
            "esperanza_r": round(sum(rs) / len(rs), 2) if rs else None,
            "factor_beneficio": round(sum(wins) / -sum(losses), 2) if losses and sum(losses) < 0 else None}


def _group(trades: list[dict], key: str) -> dict:
    out: dict[str, list[dict]] = {}
    for t in trades:
        out.setdefault(str(t.get(key)), []).append(t)
    return {k: stats(v) for k, v in sorted(out.items())}


def build(run_dir: Path, day: date, capital: Optional[float] = None) -> dict:
    book = json.loads((run_dir / "paper.json").read_text(encoding="utf-8"))
    state_path = run_dir / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    start = capital if capital is not None else _f(state.get("capital")) or None
    closed = book.get("closed", [])
    curve, peak, dd, equity = [], start or 0.0, 0.0, start or 0.0
    for t in closed:  # drawdown on closed trades
        equity += _f(t["pnl"])
        curve.append(equity)
        peak = max(peak, equity)
        if peak > 0:
            dd = max(dd, (peak - equity) / peak * 100)
    today = [t for t in closed if _local_day(t.get("at", "")) == day]
    total = stats(closed)
    return {"dia": day.isoformat(), "capital_inicial": start, "cuenta": "práctica (dinero ficticio)",
            "estado": state.get("status"), "hoy": stats(today), "acumulado": total,
            "neto_pct": round(total["neto_usdt"] / start * 100, 2) if start else None,
            "caida_max_pct": round(dd, 2), "por_moneda": _group(closed, "symbol"), "por_lado": _group(closed, "side"),
            "por_salida": _group(closed, "why"), "vetos": state.get("veto_score", {}),
            "abiertas": [{"symbol": s, "side": p["side"], "entry": p["entry"], "sl": p["sl"], "tp": p["tp"]}
                         for s, p in book.get("positions", {}).items()],
            "operaciones_hoy": today}


def render(r: dict) -> str:
    a, h = r["acumulado"], r["hoy"]
    lines = [f"# Práctica de futuros (dinero ficticio) — {r['dia']}", "",
             f"Cuenta de práctica con precios reales de Binance; capital inicial {r['capital_inicial']} USDT. "
             f"Estado: {r['estado']}.", "",
             "| | Operaciones | Acierto | Neto USDT | Esperanza (R) | Factor de beneficio |", "|---|---|---|---|---|---|",
             f"| Hoy | {h['operaciones']} | {h['acierto_pct']}% | {h['neto_usdt']:+.2f} | {h['esperanza_r']} | "
             f"{h['factor_beneficio']} |",
             f"| Acumulado | {a['operaciones']} | {a['acierto_pct']}% | {a['neto_usdt']:+.2f} ({r['neto_pct']}%) | "
             f"{a['esperanza_r']} | {a['factor_beneficio']} |", "",
             f"Caída máxima (operaciones cerradas): {r['caida_max_pct']}%.", ""]
    for title, key in (("Por moneda", "por_moneda"), ("Por lado", "por_lado"), ("Por salida", "por_salida")):
        lines += [f"## {title}", "", "| | Operaciones | Acierto | Neto USDT | Esperanza (R) |", "|---|---|---|---|---|"]
        lines += [f"| {k} | {v['operaciones']} | {v['acierto_pct']}% | {v['neto_usdt']:+.2f} | {v['esperanza_r']} |"
                  for k, v in r[key].items()] or ["| — | 0 | | | |"]
        lines.append("")
    v = r["vetos"]
    lines += [f"Vetos del Escéptico: {v.get('evitó pérdida', 0)} evitaron una pérdida, "
              f"{v.get('dejó pasar ganancia', 0)} dejaron pasar una ganancia, {v.get('sin resultado', 0)} sin resultado.", "",
              f"Posiciones abiertas: {len(r['abiertas'])}.", ""]
    if a["operaciones"] < MIN_SAMPLE:
        lines.append(f"Muestra corta ({a['operaciones']} de {MIN_SAMPLE} operaciones): todavía no se saca ninguna "
                     "conclusión ni se cambia ninguna regla.")
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Reporte diario de la práctica de futuros")
    parser.add_argument("--dir", type=Path, default=Path("live_runs/futures_auto/shadow"))
    parser.add_argument("--salida", type=Path, default=Path("docs/shadow_futures"))
    parser.add_argument("--dia", help="YYYY-MM-DD (día de Ecuador); por defecto, hoy en Ecuador")
    parser.add_argument("--capital", type=float)
    args = parser.parse_args(argv)
    day = date.fromisoformat(args.dia) if args.dia else datetime.now(ECUADOR).date()
    report = build(args.dir, day, args.capital)
    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / f"{day.isoformat()}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False),
                                                       encoding="utf-8")
    text = render(report)
    (args.salida / f"{day.isoformat()}.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
