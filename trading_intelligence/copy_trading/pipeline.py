"""
End-to-end copy-trading run: snapshot -> evaluate/select (as of the first event, no
look-ahead) -> follow every leader event and mark in time order (PAPER / SHADOW) ->
state file + owner report.

    python -m trading_intelligence.copy_trading.pipeline --demo --state-dir paper_runs/copy

`--demo` uses the synthetic universe in demo.py (labelled SYNTHETIC everywhere). Real
snapshots come from `--snapshot <file>` with an official source (sources.py).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional

from trading_intelligence.copy_trading.evaluator import (
    SelectionCriteria,
    SelectionDecision,
    TraderEvaluation,
    UniverseStats,
    evaluate,
    metrics_dict,
    select,
    selected_ids,
    universe_stats,
)
from trading_intelligence.copy_trading.follower import (
    CopyFollower,
    ExecutionModel,
    FailureAt,
    PriceAt,
    RegimeAt,
)
from trading_intelligence.copy_trading.models import LeaderEvent, TraderRecord
from trading_intelligence.copy_trading.risk import CopyRiskConfig, CopyRiskPolicy
from trading_intelligence.copy_trading.sources import Snapshot, load_snapshot
from trading_intelligence.persistence.audit_log import AuditLog
from trading_intelligence.risk.engine import RiskEngine
from trading_intelligence.risk.models import RiskConfig


@dataclass
class PipelineResult:
    snapshot: Snapshot
    as_of: datetime
    evaluations: list[TraderEvaluation]
    decisions: list[SelectionDecision]
    stats: UniverseStats
    follower: CopyFollower
    end: datetime


def record_as_of(record: TraderRecord, as_of: datetime) -> TraderRecord:
    """The record as it looked at `as_of`: drops the daily returns after it. App figures
    (reported ROI windows) cannot be rewound, so replaying events from before the
    capture with them would be look-ahead: refused."""
    drop = (record.captured_at.date() - as_of.date()).days
    if drop <= 0:
        return record
    if not record.daily_returns and record.reported is not None:
        raise ValueError(
            f"{record.trader_id}: reported app figures end at the capture time and cannot be used to "
            f"select traders as of {as_of.isoformat()} (look-ahead); evaluate at capture and follow forward"
        )
    return replace(record, daily_returns=record.daily_returns[:-drop] if drop < len(record.daily_returns) else ())


def run_pipeline(
    snapshot: Snapshot,
    price_at: PriceAt,
    state_dir: Path,
    *,
    starting_equity: Decimal,
    criteria: Optional[SelectionCriteria] = None,
    copy_config: Optional[CopyRiskConfig] = None,
    risk_config: Optional[RiskConfig] = None,
    execution: Optional[ExecutionModel] = None,
    regime_at: Optional[RegimeAt] = None,
    failure_at: Optional[FailureAt] = None,
    incumbents: frozenset[str] = frozenset(),
    mark_every: timedelta = timedelta(hours=1),
    mode: str = "PAPER",
) -> PipelineResult:
    criteria = criteria or SelectionCriteria()
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    engine = RiskEngine(risk_config or RiskConfig(), state_dir / "copy_risk.json", AuditLog(state_dir / "copy_audit"))
    follower = CopyFollower(
        CopyRiskPolicy(copy_config or CopyRiskConfig(), engine), execution or ExecutionModel(), price_at,
        starting_equity, mode=mode, regime_at=regime_at, failure_at=failure_at,
    )
    as_of = snapshot.events[0].ts if snapshot.events else snapshot.captured_at
    evaluations = [evaluate(record_as_of(r, as_of), criteria) for r in snapshot.traders]
    decisions = select(evaluations, criteria, incumbents)
    follower.apply_selection(as_of, decisions)

    end = snapshot.captured_at
    marks: list[datetime] = []
    t = as_of + mark_every
    while t <= end:
        marks.append(t)
        t += mark_every
    timeline: list[tuple[datetime, int, object]] = [(e.ts, 0, e) for e in snapshot.events]
    timeline += [(m, 1, None) for m in marks]
    for ts, kind, item in sorted(timeline, key=lambda x: (x[0], x[1])):
        if isinstance(item, LeaderEvent):
            follower.on_event(item)
        else:
            follower.on_mark(ts)
    result = PipelineResult(snapshot, as_of, evaluations, decisions, universe_stats(evaluations), follower, end)
    write_state(result, state_dir / "copy_state.json")
    return result


def _s(v: object) -> object:
    return str(v) if isinstance(v, Decimal) else v


def state_of(result: PipelineResult) -> dict:
    f = result.follower
    equity = f.equity(result.end)
    return {
        "mode": f.mode,
        "synthetic": result.snapshot.synthetic,
        "source": result.snapshot.source,
        "as_of": result.as_of.isoformat(),
        "end": result.end.isoformat(),
        "starting_equity": str(f.starting_equity),
        "equity": str(equity.quantize(Decimal("0.0001"))),
        "cash": str(f.cash.quantize(Decimal("0.0001"))),
        "kill_switch": f.policy.engine.state.kill_switch,
        "kill_switch_reason": f.policy.engine.state.kill_switch_reason,
        "universe": {k: _s(v) for k, v in vars(result.stats).items()},
        "traders": [
            {"trader_id": e.trader_id, "name": e.name, "active": e.active, "eligible": e.eligible,
             "failed": e.failed, "metrics": metrics_dict(e.metrics)}
            for e in result.evaluations
        ],
        "selection": [{"trader_id": d.trader_id, "decision": d.decision, "reasons": d.reasons, "score": str(d.score)}
                      for d in result.decisions],
        "followed": sorted(f.followed),
        "blocked": f.blocked,
        "positions": [
            {"trader": p.trader_id, "symbol": p.symbol, "side": p.side.value, "qty": str(p.qty),
             "avg_entry": str(p.avg_entry), "value": str((p.qty * f.price_at(p.symbol, result.end)).quantize(Decimal("0.01")))}
            for p in f.positions.values()
        ],
        "closed": [
            {"trader": c.trader_id, "symbol": c.symbol, "entry": str(c.entry), "exit": str(c.exit),
             "pnl": str(c.pnl.quantize(Decimal("0.0001"))), "reason": c.reason, "closed_at": c.closed_at,
             "our_return_pct": str(c.our_return_pct.quantize(Decimal("0.01"))),
             "leader_return_pct": str(c.leader_return_pct.quantize(Decimal("0.01"))) if c.leader_return_pct is not None else None}
            for c in f.closed
        ],
        "journal": f.journal,
    }


def write_state(result: PipelineResult, path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state_of(result), indent=2), encoding="utf-8")
    tmp.replace(path)


def render(state: dict) -> str:
    out = [f"## Copy trading — {state['mode']} ({'DATOS SINTÉTICOS de demostración' if state['synthetic'] else 'fuente: ' + state['source']})", ""]
    start, eq = Decimal(state["starting_equity"]), Decimal(state["equity"])
    out.append(f"- capital: {start:,.2f} → **{eq:,.2f}** ({(eq - start) / start * 100:+.2f}%) · efectivo {Decimal(state['cash']):,.2f} "
               f"· kill switch: {'SÍ — ' + state['kill_switch_reason'] if state['kill_switch'] else 'no'}")
    out.append(f"- seleccionados: {', '.join(state['followed']) or 'ninguno'} · bloqueados: "
               f"{', '.join(f'{k} ({v})' for k, v in state['blocked'].items()) or 'ninguno'}")
    u = state["universe"]
    out.append(f"- universo: {u['traders']} traders, {u['inactive']} ya no lideran"
               + (f" · ⚠ {u['survivorship_warning']}" if u.get("survivorship_warning") else ""))
    out += ["", "### Traders evaluados", "", "| trader | decisión | puntaje | retorno anual neto | encogido | máx. caída | consistencia | motivos |",
            "|---|---|---|---|---|---|---|---|"]
    sel = {s["trader_id"]: s for s in state["selection"]}
    for t in state["traders"]:
        m, s = t["metrics"], sel.get(t["trader_id"], {})
        out.append(f"| {t['name']} | {s.get('decision')} | {s.get('score')} | {Decimal(m['annual_net_return']) * 100:.1f}% "
                   f"| {Decimal(m['shrunk_annual_return']) * 100:.1f}% | {Decimal(m['max_drawdown']) * 100:.1f}% "
                   f"| {Decimal(m['consistency']) * 100:.0f}% | {', '.join(s.get('reasons', []))} |")
    out += ["", "### Decisiones de riesgo y ejecución (últimas 25)", "", "| hora | trader | símbolo | evento | acción | motivo | lado | cantidad | precio |",
            "|---|---|---|---|---|---|---|---|---|"]
    for j in state["journal"][-25:]:
        out.append(f"| `{j['ts'][5:16]}` | {j['trader']} | {j['symbol']} | {j['source']} | {j['action']} | {j['reason']} "
                   f"| {j.get('side', '')} | {j.get('qty', '')} | {j.get('price', '')} |")
    out += ["", "### Copias cerradas (nuestro resultado vs el del líder)", ""]
    if state["closed"]:
        out += ["| trader | símbolo | P&L | nuestro % | líder % | motivo |", "|---|---|---|---|---|---|"]
        for c in state["closed"]:
            out.append(f"| {c['trader']} | {c['symbol']} | {Decimal(c['pnl']):,.4f} | {c['our_return_pct']}% "
                       f"| {c['leader_return_pct'] + '%' if c['leader_return_pct'] is not None else 'sigue abierta'} | {c['reason']} |")
        if any(c["leader_return_pct"] is not None and c["reason"] != "LEADER_CLOSED" for c in state["closed"]):
            out.append("")
            out.append("Cuando salimos antes que el líder, «líder %» es su resultado al cerrar él (después).")
    else:
        out.append("Ninguna.")
    skips = [j for j in state["journal"] if j["reason"].startswith("BELOW_MIN_NOTIONAL")]
    if skips:
        out += ["", f"**{len(skips)} copia(s) no ejecutada(s) por debajo del mínimo de orden del exchange** "
                     "(con poco capital, las posiciones del líder escaladas a nuestro tamaño quedan bajo el mínimo)."]
    out.append("")
    return "\n".join(out)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Copy-trading PAPER/SHADOW run (no account, no orders).")
    parser.add_argument("--state-dir", default="paper_runs/copy")
    parser.add_argument("--demo", action="store_true", help="synthetic universe (labelled SYNTHETIC)")
    parser.add_argument("--snapshot", help="snapshot JSON from an official source")
    parser.add_argument("--equity", default="1000")
    args = parser.parse_args(argv)
    from trading_intelligence.copy_trading import demo

    state_dir = Path(args.state_dir)
    if args.demo:
        result = demo.run(state_dir, starting_equity=Decimal(args.equity))
    elif args.snapshot:
        # Real snapshots carry no price feed here: SHADOW on live prices is the next step
        # (needs the public feed per event time). Until then only the evaluation runs.
        snap = load_snapshot(Path(args.snapshot))
        evaluations = [evaluate(r, SelectionCriteria()) for r in snap.traders]
        decisions = select(evaluations, SelectionCriteria())
        print(json.dumps([{"trader": d.trader_id, "decision": d.decision, "reasons": d.reasons} for d in decisions], indent=2))
        print("selected:", sorted(selected_ids(decisions)))
        return 0
    else:
        parser.error("choose --demo or --snapshot")
    text = render(state_of(result))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
