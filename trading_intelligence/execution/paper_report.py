"""
Owner-facing report of a PaperLoop state file (`loop.json`).

Renders what the loop decided and why, simulated fills, closed trades and the
equity curve as Markdown (the GitHub Actions run summary), and lists anything
that needs attention. Read-only: it never touches the runner, the feed or any
account.

    python -m trading_intelligence.execution.paper_report --state-dir paper_runs/live

Exit code 1 when the state is missing or something needs attention, so an
automated run turns red.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

_ACTION_TEXT = {
    "NO_SIGNAL": "estrategia activa, sin señal",
    "ENTRY_SUBMITTED": "orden de COMPRA enviada (se llena en la apertura siguiente)",
    "ENTRY_PENDING": "compra pendiente de llenarse",
    "ENTRIES_BLOCKED": "entradas bloqueadas por el motor de riesgo",
    "HOLDING": "posición abierta, se mantiene (STOP activo)",
    "EXIT_PENDING": "venta pendiente de llenarse",
    "EXIT_SUBMITTED": "orden de VENTA enviada",
    "STALE_BAR_IGNORED": "vela repetida o antigua, ignorada",
    "NO_DATA": "sin datos para este símbolo",
}
_PREFIX_TEXT = {
    "NO_TRADE": "no opera",
    "RISK_REJECTED": "rechazada por riesgo",
    "ORDER_NOT_ACCEPTED": "orden no aceptada",
}


def explain(action: str) -> str:
    if action in _ACTION_TEXT:
        return _ACTION_TEXT[action]
    prefix, _, detail = action.partition(":")
    if prefix in _PREFIX_TEXT:
        return f"{_PREFIX_TEXT[prefix]}: {detail}" if detail else _PREFIX_TEXT[prefix]
    return action


def problems_in(data: dict) -> list[str]:
    st = data.get("status", {})
    problems = []
    if st.get("last_fetch_error"):
        problems.append(f"error al leer datos: {st['last_fetch_error']}")
    if st.get("stale_symbols"):
        problems.append(f"datos atrasados: {', '.join(st['stale_symbols'])}")
    if st.get("last_gap_halt"):
        problems.append(f"hueco en los datos: {st['last_gap_halt']}")
    if st.get("kill_switch"):
        problems.append(f"kill switch activo: {st.get('kill_switch_reason')}")
    if st.get("books_disagree"):
        problems.append(f"libros no cuadran: {st['books_disagree'][0]}")
    return problems


def _dec(value: object) -> Optional[Decimal]:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _money(value: object) -> str:
    d = _dec(value)
    return f"{d:,.2f}" if d is not None else "—"


def _price(value: object) -> str:
    d = _dec(value)
    if d is None:
        return "—"
    return f"{d:,.2f}" if abs(d) >= 1 else f"{d:.6f}"


def _equity_lines(history: list[dict]) -> list[str]:
    values: list[tuple[object, Decimal]] = []
    for h in history:
        v = _dec(h.get("equity"))
        if v is not None:
            values.append((h.get("bar"), v))
    if not values:
        return []
    first, last = values[0][1], values[-1][1]
    peak = max(v for _, v in values)
    drawdown = (peak - last) / peak * 100 if peak > 0 else Decimal("0")
    change = (last - first) / first * 100 if first > 0 else Decimal("0")
    return [
        f"- capital desde `{values[0][0]}`: {_money(first)} → **{_money(last)}** "
        f"({change:+.2f}%) · máximo {_money(peak)} · caída desde el máximo {drawdown:.2f}% "
        f"· {len(values)} velas registradas",
    ]


def render(data: dict) -> str:
    st = data.get("status", {})
    problems = problems_in(data)
    journal: list[dict] = data.get("journal", [])
    trades: list[dict] = data.get("trades", [])
    out: list[str] = ["## PAPER loop: simulación (sin cuenta, sin órdenes reales)", ""]
    out.append("**Estado: ATENCIÓN**" if problems else "**Estado: OK**: todos los controles limpios.")
    out += [f"- {p}" for p in problems]
    out += [
        "",
        f"- datos: `{data.get('feed_origin')}` · {data.get('timeframe')} · "
        f"`{' '.join(data.get('symbols', []))}`",
        f"- última vela procesada: `{data.get('last_processed')}` · última ejecución `{st.get('last_tick')}`",
        f"- capital: **{_money(st.get('equity'))}** · efectivo {_money(st.get('cash'))} · "
        f"posiciones abiertas: {', '.join(st.get('open_positions', [])) or 'ninguna'} · "
        f"kill switch: {'SÍ' if st.get('kill_switch') else 'no'}",
    ]
    out += _equity_lines(data.get("equity_history", []))

    latest: dict[str, dict] = {}
    for entry in journal:
        latest[entry.get("symbol", "?")] = entry
    if latest:
        out += ["", "### Última decisión por símbolo", "",
                "| símbolo | vela | cierre | régimen | decisión |", "|---|---|---|---|---|"]
        for sym in sorted(latest):
            e = latest[sym]
            out.append(f"| {sym} | `{e.get('bar')}` | {_price(e.get('close'))} | {e.get('regime') or '—'} "
                       f"| {explain(e.get('action', ''))} |")

    fills = [(e, f) for e in journal for f in e.get("fills", []) if f.get("status") in ("FILLED", "PARTIALLY_FILLED")]
    out += ["", "### Operaciones simuladas recientes", ""]
    if fills:
        out += ["| vela | símbolo | lado | cantidad | precio | comisión |", "|---|---|---|---|---|---|"]
        for e, f in fills[-10:]:
            out.append(f"| `{e.get('bar')}` | {e.get('symbol')} | {f.get('side')} | {f.get('qty')} "
                       f"| {_price(f.get('price'))} | {_money(f.get('fee'))} |")
    else:
        out.append("Ninguna todavía.")

    out += ["", "### Trades cerrados", ""]
    if trades:
        pnls = [_dec(t.get("pnl")) or Decimal("0") for t in trades]
        wins = sum(1 for p in pnls if p > 0)
        out.append(f"{len(trades)} trades · ganadores {wins} · P&L total **{_money(sum(pnls))}**")
        out += ["", "| cerrado | símbolo | entrada | salida | P&L | motivo |", "|---|---|---|---|---|---|"]
        for t in trades[-10:]:
            out.append(f"| `{t.get('closed_at')}` | {t.get('symbol')} | {_price(t.get('entry_price'))} "
                       f"| {_price(t.get('exit_price'))} | {_money(t.get('pnl'))} | {t.get('exit_reason')} |")
    else:
        out.append("Ninguno todavía.")
    out.append("")
    return "\n".join(out)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Render a PaperLoop state file for the owner (read-only).")
    parser.add_argument("--state-dir", default="paper_runs/live")
    args = parser.parse_args(argv)
    path = Path(args.state_dir) / "loop.json"
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path.exists():
        text = ("## PAPER loop\n\n**Estado: ATENCIÓN**: no hay estado. O el loop falló (revisa el paso anterior), "
                "o se perdió el estado de la ejecución previa (caché de Actions). No se reinicia solo: para "
                "empezar de cero a propósito, lanza el workflow a mano con `bootstrap = true`.\n")
        code = 1
        data: dict = {}
    else:
        data = json.loads(path.read_text())
        text = render(data)
        code = 1 if problems_in(data) else 0
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(text)
    sys.stdout.write(text)
    if data:
        sys.stdout.write("\n" + json.dumps(data.get("status", {}), indent=2) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
