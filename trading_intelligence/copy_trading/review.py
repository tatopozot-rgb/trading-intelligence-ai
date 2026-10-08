"""
Trader review for the owner: ranks every captured lead trader with auditable reasons,
says what to do with each trader currently copied (keep / stop now / let it wind
down), and measures across captures whether the selection works (learning.py).

    python -m trading_intelligence.copy_trading.review --snapshots docs/snapshots \
        --followed docs/snapshots/followed.json --out paper_runs/copy_review

- Only snapshots from official channels are read (sources.py); templates are skipped.
- `followed.json` is what the owner actually copies in the Binance app:
  {"followed": ["<trader_id>", ...]}. Missing file = nothing copied yet.
- Writes review.json and, under GitHub Actions, the run summary. Exit 1 when a
  copied trader must be stopped now, so the run turns red and gets noticed.

Advice only: copying, stopping and amounts are clicks the owner makes in the app.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
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
    universe_stats,
)
from trading_intelligence.copy_trading.learning import LearningSummary, learn, render_learning
from trading_intelligence.copy_trading.sources import Snapshot, UnverifiedSource, load_snapshot

REASON_TEXT = {
    "INACTIVE": "dejó de liderar",
    "MARKET_NOT_ALLOWED": "mercado no permitido (solo Spot por ahora)",
    "HISTORY_TOO_SHORT": "historial demasiado corto",
    "TOO_FEW_TRADES": "muy pocas operaciones",
    "DRAWDOWN_TOO_DEEP": "caída máxima demasiado profunda",
    "NOT_PROFITABLE_AFTER_SHRINKAGE": "no es rentable al descontar suerte y comisión",
    "INCONSISTENT": "resultados inconsistentes",
    "PROFIT_CONCENTRATED_IN_FEW_TRADES": "ganancia concentrada en pocas operaciones (o no se sabe)",
    "SYMBOL_CONCENTRATED": "concentrado en un solo activo (o no se sabe)",
    "ILLIQUID_SYMBOLS": "opera activos poco líquidos (o no se sabe)",
    "LEVERAGE_TOO_HIGH": "apalancamiento por encima del permitido",
    "MISSING_FROM_SNAPSHOT": "ya no aparece en la captura",
}

ACTION_TEXT = {
    "ADD": "candidato a copiar",
    "KEEP": "MANTENER",
    "REMOVE_INVALIDATED": "DEJAR DE COPIAR YA",
    "REMOVE_WIND_DOWN": "no añadir; dejar que cierre lo abierto y salir",
    "NOT_SELECTED": "apto, sin cupo",
    "REJECT": "no copiar",
}


@dataclass
class Review:
    latest: Snapshot
    evaluations: list[TraderEvaluation]
    decisions: list[SelectionDecision]
    stats: UniverseStats
    followed: list[str]
    learning: LearningSummary
    skipped: list[str]

    @property
    def stop_now(self) -> list[str]:
        return [d.trader_id for d in self.decisions
                if d.trader_id in self.followed and d.decision == "REMOVE_INVALIDATED"]


def load_snapshots(folder: Path) -> tuple[list[Snapshot], list[str]]:
    snaps, skipped = [], []
    for path in sorted(Path(folder).glob("*.json")):
        if path.name == "followed.json":
            continue
        try:
            snaps.append(load_snapshot(path))
        except UnverifiedSource as error:
            skipped.append(f"{path.name}: {error}")
        except (ValueError, KeyError) as error:
            skipped.append(f"{path.name}: invalid ({error})")
    return snaps, skipped


def run_review(snapshots: list[Snapshot], followed: list[str],
               criteria: Optional[SelectionCriteria] = None, skipped: Optional[list[str]] = None) -> Review:
    criteria = criteria or SelectionCriteria()
    latest = max(snapshots, key=lambda s: s.captured_at)
    evaluations = [evaluate(r, criteria) for r in latest.traders]
    decisions = select(evaluations, criteria, incumbents=frozenset(followed))
    return Review(latest, evaluations, decisions, universe_stats(evaluations), list(followed),
                  learn(snapshots, criteria), skipped or [])


def _reasons(reasons: list[str]) -> str:
    out = []
    for r in reasons:
        key = r.split(":")[0]
        if key in ("ELIGIBLE", "SLOT_FREE", "STILL_ELIGIBLE"):
            continue
        out.append(REASON_TEXT.get(key, r))
    return "; ".join(out) or "cumple todos los criterios"


def render(review: Review) -> str:
    snap = review.latest
    ev = {e.trader_id: e for e in review.evaluations}
    out = [f"## Revisión de traders — captura {snap.captured_at.isoformat()} ({snap.source})", ""]
    if review.stop_now:
        out.append(f"**ATENCIÓN: deja de copiar ya a {', '.join(review.stop_now)}** (motivos abajo).")
        out.append("")
    if review.stats.survivorship_warning:
        out.append(f"⚠ Sesgo de supervivencia: {review.stats.survivorship_warning}.")
    if any(e.metrics.basis == "reported_windows" for e in review.evaluations):
        out.append("ℹ Cifras tomadas de la app (ROI por ventanas, no serie diaria): la evaluación es más gruesa.")
    out += [f"- traders en la captura: {review.stats.traders} ({review.stats.inactive} ya no lideran)",
            f"- copiando ahora: {', '.join(review.followed) or 'ninguno'}", ""]

    if review.followed:
        out += ["### Traders que copias ahora", "", "| trader | qué hacer | por qué |", "|---|---|---|"]
        for d in review.decisions:
            if d.trader_id in review.followed:
                out.append(f"| {d.trader_id} | **{ACTION_TEXT.get(d.decision, d.decision)}** | {_reasons(d.reasons)} |")
        out.append("")

    out += ["### Ranking", "",
            "| # | trader | decisión | puntaje | anual neto | ajustado por suerte | caída máx. | consistencia | por qué |",
            "|---|---|---|---|---|---|---|---|---|"]
    ranked = sorted(review.decisions, key=lambda d: (d.decision not in ("ADD", "KEEP"), -d.score))
    for i, d in enumerate(ranked, start=1):
        m = ev[d.trader_id].metrics if d.trader_id in ev else None
        if m is None:
            out.append(f"| {i} | {d.trader_id} | {ACTION_TEXT.get(d.decision, d.decision)} | — | — | — | — | — | "
                       f"{_reasons(d.reasons)} |")
            continue
        out.append(f"| {i} | {ev[d.trader_id].name} | {ACTION_TEXT.get(d.decision, d.decision)} | {d.score} "
                   f"| {Decimal(m.annual_net_return) * 100:.1f}% | {Decimal(m.shrunk_annual_return) * 100:.1f}% "
                   f"| {Decimal(m.max_drawdown) * 100:.1f}% | {Decimal(m.consistency) * 100:.0f}% | {_reasons(d.reasons)} |")
    out += ["", render_learning(review.learning)]
    if review.skipped:
        out += ["Archivos ignorados:", *[f"- {s}" for s in review.skipped], ""]
    out.append("_Recomendación, no orden: copiar, dejar de copiar y montos los decide y ejecuta el dueño en la app._")
    return "\n".join(out) + "\n"


def to_json(review: Review) -> dict:
    return {
        "captured_at": review.latest.captured_at.isoformat(),
        "source": review.latest.source,
        "followed": review.followed,
        "stop_now": review.stop_now,
        "decisions": [{"trader_id": d.trader_id, "decision": d.decision, "action": ACTION_TEXT.get(d.decision),
                       "reasons": d.reasons, "score": str(d.score)} for d in review.decisions],
        "metrics": {e.trader_id: metrics_dict(e.metrics) for e in review.evaluations},
        "learning": {
            "periods": len(review.learning.periods),
            "selected_mean": review.learning.selected_mean, "others_mean": review.learning.others_mean,
            "edge": review.learning.edge, "selected_hit_rate": review.learning.selected_hit_rate,
            "rank_stability": review.learning.rank_stability,
        },
        "skipped": review.skipped,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Review captured lead traders (advice only).")
    parser.add_argument("--snapshots", type=Path, default=Path("docs/snapshots"))
    parser.add_argument("--followed", type=Path, default=Path("docs/snapshots/followed.json"))
    parser.add_argument("--out", type=Path, default=Path("paper_runs/copy_review"))
    args = parser.parse_args(argv)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    snaps, skipped = load_snapshots(args.snapshots) if args.snapshots.exists() else ([], [])
    if not snaps:
        text = ("## Revisión de traders\n\nTodavía no hay capturas oficiales en "
                f"`{args.snapshots}`. Plantilla: `docs/templates/copy_trading_capture.template.csv`.\n")
        if skipped:
            text += "\nArchivos ignorados:\n" + "".join(f"- {s}\n" for s in skipped)
        code = 0
    else:
        followed = json.loads(args.followed.read_text(encoding="utf-8")).get("followed", []) \
            if args.followed.exists() else []
        review = run_review(snaps, followed, skipped=skipped)
        text = render(review)
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "review.json").write_text(json.dumps(to_json(review), indent=2, ensure_ascii=False),
                                              encoding="utf-8")
        code = 1 if review.stop_now else 0
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(text)
    sys.stdout.write(text)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
