"""
Learning across captures: does the selection actually pick traders who do well
AFTERWARDS? Each pair of consecutive snapshots (t, t+1) is an out-of-sample test of the
selection made at t, scored on what happened by t+1.

Forward return of a trader between t and t+1:
- daily series: compounded over the days between the captures (exact);
- app figures: the shortest reported ROI window at t+1 that covers the gap (an
  approximation: the window may start before t). Reports say which.
A trader present at t and missing at t+1 "disappeared"; that is counted, never
silently dropped (survivorship).

With few captures nothing here is statistically meaningful; the report says how many
periods back each number.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from trading_intelligence.copy_trading.evaluator import SelectionCriteria, evaluate, select, selected_ids
from trading_intelligence.copy_trading.models import TraderRecord
from trading_intelligence.copy_trading.sources import Snapshot


def forward_return(record: TraderRecord, gap_days: int) -> tuple[Optional[float], str]:
    if gap_days <= 0:
        return None, "no_gap"
    if record.daily_returns:
        if len(record.daily_returns) < gap_days:
            return None, "series_too_short"
        tail = record.daily_returns[-gap_days:]
        return math.prod(1 + float(r) for r in tail) - 1, "daily_series"
    if record.reported is not None:
        windows = sorted(d for d in record.reported.roi_pct_by_days if d >= gap_days)
        if windows:
            return float(record.reported.roi_pct_by_days[windows[0]]) / 100, f"reported_{windows[0]}d_window"
    return None, "unavailable"


@dataclass
class PeriodResult:
    start: str
    end: str
    gap_days: int
    selected: list[str]
    selected_forward: dict[str, Optional[float]]
    others_forward: dict[str, Optional[float]]
    disappeared: list[str]
    still_selected: list[str]
    basis: dict[str, str] = field(default_factory=dict)


@dataclass
class LearningSummary:
    periods: list[PeriodResult]
    selected_mean: Optional[float]
    others_mean: Optional[float]
    selected_hit_rate: Optional[float]
    selected_disappeared: int
    selected_total: int
    rank_stability: Optional[float]
    criterion_effect: dict[str, dict[str, Optional[float]]]

    @property
    def edge(self) -> Optional[float]:
        if self.selected_mean is None or self.others_mean is None:
            return None
        return self.selected_mean - self.others_mean


def _mean(xs: list[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def learn(snapshots: list[Snapshot], criteria: Optional[SelectionCriteria] = None) -> LearningSummary:
    criteria = criteria or SelectionCriteria()
    ordered = sorted(snapshots, key=lambda s: s.captured_at)
    periods: list[PeriodResult] = []
    sel_all: list[float] = []
    oth_all: list[float] = []
    disappeared_sel = 0
    total_sel = 0
    stability: list[float] = []
    outcomes: list[tuple[float, frozenset[str]]] = []  # (forward return, failed criteria) per trader-period
    for before, after in zip(ordered, ordered[1:]):
        gap = (after.captured_at.date() - before.captured_at.date()).days
        evals = [evaluate(r, criteria) for r in before.traders]
        chosen = selected_ids(select(evals, criteria))
        later = {r.trader_id: r for r in after.traders}
        later_chosen = selected_ids(select([evaluate(r, criteria) for r in after.traders], criteria))
        period = PeriodResult(before.captured_at.isoformat(), after.captured_at.isoformat(), gap, sorted(chosen),
                              {}, {}, [], sorted(chosen & later_chosen))
        for ev in evals:
            rec = later.get(ev.trader_id)
            if rec is None:
                period.disappeared.append(ev.trader_id)
                continue
            fwd, basis = forward_return(rec, gap)
            period.basis[ev.trader_id] = basis
            (period.selected_forward if ev.trader_id in chosen else period.others_forward)[ev.trader_id] = fwd
            if fwd is None:
                continue
            (sel_all if ev.trader_id in chosen else oth_all).append(fwd)
            outcomes.append((fwd, frozenset(ev.failed)))
        total_sel += len(chosen)
        disappeared_sel += len(chosen & set(period.disappeared))
        if chosen:
            stability.append(len(chosen & later_chosen) / len(chosen))
        periods.append(period)
    names = sorted(set().union(*(failed for _, failed in outcomes))) if outcomes else []
    effect = {
        name: {"failed_mean": _mean([f for f, failed in outcomes if name in failed]),
               "passed_mean": _mean([f for f, failed in outcomes if name not in failed])}
        for name in names
    }
    return LearningSummary(
        periods=periods,
        selected_mean=_mean(sel_all), others_mean=_mean(oth_all),
        selected_hit_rate=(sum(1 for x in sel_all if x > 0) / len(sel_all)) if sel_all else None,
        selected_disappeared=disappeared_sel, selected_total=total_sel,
        rank_stability=_mean(stability),
        criterion_effect=effect,
    )


def _pct(x: Optional[float]) -> str:
    return "—" if x is None else f"{x * 100:+.2f}%"


def _rate(x: Optional[float]) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


def render_learning(summary: LearningSummary) -> str:
    n = len(summary.periods)
    out = ["### Aprendizaje entre capturas", ""]
    if n == 0:
        out.append("Hace falta al menos **dos capturas** en fechas distintas para medir si la selección "
                   "acierta después. Con una sola no hay nada que aprender todavía.")
        return "\n".join(out) + "\n"
    out += [
        f"- períodos medidos: **{n}** (pocos períodos no prueban nada; la cifra madura con capturas semanales)",
        f"- resultado posterior medio de los **seleccionados**: {_pct(summary.selected_mean)} · del resto: "
        f"{_pct(summary.others_mean)} · ventaja de la selección: **{_pct(summary.edge)}**",
        f"- seleccionados con resultado positivo después: {_rate(summary.selected_hit_rate)}",
        f"- seleccionados que desaparecieron en la captura siguiente: {summary.selected_disappeared} de "
        f"{summary.selected_total}",
        f"- estabilidad (seleccionados que siguen seleccionados): {_rate(summary.rank_stability)}",
    ]
    effects = {k: v for k, v in summary.criterion_effect.items() if v["failed_mean"] is not None}
    if effects:
        out += ["", "| criterio | resultado posterior de quienes lo fallaron | de quienes lo pasaron |", "|---|---|---|"]
        for name, v in sorted(effects.items()):
            out.append(f"| {name} | {_pct(v['failed_mean'])} | {_pct(v['passed_mean'])} |")
    return "\n".join(out) + "\n"
