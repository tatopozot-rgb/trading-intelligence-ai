"""
Forward PAPER of the two-way time-series momentum strategy (docs/PREREG_TWO_WAY.md,
CHECKPOINT section 65). Research only: public data, no account, no key, no orders.

Every weekly run REPLAYS the registered code (`two_way_momentum.simulate_fold` at 1x)
from the PAPER start Monday to the current Monday on public data. The PAPER therefore
runs exactly the validated code, and no state can drift between runs. The repo holds
only the experiment's identity (start date and frozen symbol list), its status and the
reports.

Registered stop rules, checked on every run (once STOPPED, always STOPPED):
  * drawdown of the PAPER equity <= -20%;
  * costs + funding of any week more than 2x the model's. In PAPER, fees and slippage are
    the model's by construction (there are no real fills), so this compares the week
    replayed with REAL funding rates against the same week under the model's 0.01%/8h
    assumption. Only the adverse direction stops the experiment; cheaper is reported.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from trading_intelligence.backtesting import two_way_momentum as tw

DEFAULT_DIR = Path("docs/paper_two_way")
LIVE_LIMITS = Path("config/live_limits.json")
STOP_DRAWDOWN_PCT = -20.0
STOP_COST_RATIO = 2.0
LEVERAGE = 1

Fetcher = Callable[[str, str, str], pd.DataFrame]
FundingFetcher = Callable[[str, str, str], tuple[pd.Series, str]]


def monday_of(now: datetime) -> pd.Timestamp:
    day = pd.Timestamp(now).tz_convert("UTC").floor("1D")
    return day - pd.Timedelta(days=day.weekday())


def next_monday(now: datetime) -> pd.Timestamp:
    day = pd.Timestamp(now).tz_convert("UTC").floor("1D")
    return day + pd.Timedelta(days=(7 - day.weekday()) % 7)


def new_state(now: datetime, symbols: list[str]) -> dict:
    return {"experiment": "two_way_tsmom_1x", "prereg": "docs/PREREG_TWO_WAY.md", "checkpoint": 65,
            "start": str(next_monday(now).date()), "symbols": symbols, "status": "PENDING",
            "stopped_reason": None, "stopped_at": None, "created": now.isoformat()}


def load_market(symbols: list[str], start: pd.Timestamp, monday: pd.Timestamp,
                fetch: Fetcher, fetch_funding: FundingFetcher) -> tuple[pd.DataFrame, pd.DataFrame, dict, dict]:
    data_start = (start - pd.Timedelta(days=tw.MIN_CLOSES + tw.LOOKBACK_DAYS + 14)).date().isoformat()
    end = (monday + pd.Timedelta(days=1)).date().isoformat()  # includes the current Monday's open
    frames, funding, sources = {}, {}, {}
    for s in symbols:
        frames[s] = fetch(s, data_start, end)
        rates, sources[s] = fetch_funding(s, data_start, end)
        funding[s] = tw.daily_funding(rates, pd.date_range(frames[s].index[0], monday, freq="1D"))
    full = pd.date_range(min(f.index[0] for f in frames.values()), monday, freq="1D")
    closes = pd.DataFrame({s: f["close"] for s, f in frames.items()}).reindex(full)
    opens = pd.DataFrame({s: f["open"] for s, f in frames.items()}).reindex(full)
    closes.loc[monday] = math.nan  # the current day is still open: never use its price as a close
    return closes, opens, funding, sources


def evaluate(state: dict, now: datetime, fetch: Fetcher, fetch_funding: FundingFetcher) -> dict:
    start = pd.Timestamp(state["start"], tz="UTC")
    monday = monday_of(now)
    report: dict = {"generated": now.isoformat(), "start": state["start"], "symbols": state["symbols"],
                    "current_monday": str(monday.date())}
    if monday < start:
        report.update(status="PENDING", weeks=[], equity=tw.INITIAL_EQUITY, positions={})
        return report
    closes, opens, funding, sources = load_market(state["symbols"], start, monday, fetch, fetch_funding)
    weeks = [start + pd.Timedelta(days=7 * k) for k in range((monday - start).days // 7)]
    real = tw.simulate_fold(closes, opens, funding, weeks, LEVERAGE) if weeks else None
    model_funding = {s: pd.Series(math.nan, index=closes.index) for s in closes}
    model = tw.simulate_fold(closes, opens, model_funding, weeks, LEVERAGE) if weeks else None
    equity = tw.INITIAL_EQUITY * (1 + real.total_return) if real else tw.INITIAL_EQUITY
    rows = []
    for i, w in enumerate(real.weeks if real else []):
        m = model.weeks[i] if model and i < len(model.weeks) else None
        rows.append({"week": str(w.start.date()), "return": w.ret, "pnl": w.pnl, "long_pnl": w.long_pnl,
                     "short_pnl": w.short_pnl, "equity_start": w.equity_start, "costs": w.costs,
                     "funding": w.funding, "model_costs_funding": (m.costs + m.funding) if m else None})
    positions = tw.targets(closes, opens, monday, equity, LEVERAGE) if not (real and real.ruined) else {}
    report.update(status=state["status"] if state["status"] == "STOPPED" else "RUNNING",
                  weeks=rows, equity=equity, max_dd_pct=real.max_dd_pct if real else 0.0,
                  positions={s: v for s, v in positions.items()}, funding_sources=sources,
                  real_funding_until={s: str(f.last_valid_index().date()) if f.notna().any() else None
                                      for s, f in funding.items()})
    return report


def apply_stop_rules(state: dict, report: dict) -> dict:
    if state["status"] == "STOPPED":
        return state
    reason = None
    if report.get("max_dd_pct", 0.0) <= STOP_DRAWDOWN_PCT:
        reason = f"caída máxima {report['max_dd_pct']:.1f}% ≤ {STOP_DRAWDOWN_PCT:.0f}%"
    for w in report.get("weeks", []):
        real_cost, model_cost = w["costs"] + w["funding"], w["model_costs_funding"]
        if model_cost and model_cost > 0 and real_cost > STOP_COST_RATIO * model_cost:
            reason = reason or (f"semana {w['week']}: costos+funding {real_cost:,.2f} > "
                                f"{STOP_COST_RATIO:.0f}× el modelo ({model_cost:,.2f})")
    if reason:
        state = {**state, "status": "STOPPED", "stopped_reason": reason, "stopped_at": report["generated"]}
        report["status"] = "STOPPED"
    elif report["status"] == "RUNNING":
        state = {**state, "status": "RUNNING"}
    return state


def render_es(state: dict, report: dict) -> str:
    status = {"PENDING": "PENDIENTE", "RUNNING": "EN CURSO", "STOPPED": "DETENIDO"}[report["status"]]
    lines = ["# PAPER semanal: momentum en dos sentidos (largo y corto), 1x",
             "",
             "Simulación con datos públicos de Binance: **sin cuenta, sin claves, sin órdenes reales**. "
             "Estrategia registrada en `docs/PREREG_TWO_WAY.md` (resultado: CHECKPOINT §65).",
             "",
             f"- **Estado: {status}**" + (f" — {state['stopped_reason']}" if state.get("stopped_reason") else ""),
             f"- Inicio: {state['start']} · semana actual: {report['current_monday']} · "
             f"generado {report['generated'][:16]}Z",
             f"- Capital simulado: 10,000.00 → **{report['equity']:,.2f}** "
             f"({report['equity'] / tw.INITIAL_EQUITY - 1:+.2%}) · caída máxima "
             f"{report.get('max_dd_pct', 0.0):.1f}% (se detiene en {STOP_DRAWDOWN_PCT:.0f}%)"]
    if report["status"] == "PENDING":
        lines += ["", f"El experimento empieza el lunes {state['start']} a las 00:00 UTC. Todavía no hay posiciones."]
        return "\n".join(lines) + "\n"
    weeks = report["weeks"]
    if weeks:
        last = weeks[-1]
        total_long = sum(w["long_pnl"] for w in weeks)
        total_short = sum(w["short_pnl"] for w in weeks)
        lines += ["", "## Última semana", "",
                  f"- Semana del {last['week']}: **{last['return']:+.2%}** ({last['pnl']:+,.2f})",
                  f"- Pierna **larga**: {last['long_pnl']:+,.2f} · pierna **corta**: {last['short_pnl']:+,.2f}",
                  f"- Costos {last['costs']:,.2f} · funding {last['funding']:+,.2f}",
                  "", "## Acumulado por pierna", "",
                  f"- Larga: **{total_long:+,.2f}** · Corta: **{total_short:+,.2f}**",
                  "", "## Historia", "", "| Semana | Retorno | Larga | Corta | Capital al inicio |",
                  "|---|---|---|---|---|"]
        for w in weeks:
            lines.append(f"| {w['week']} | {w['return']:+.2%} | {w['long_pnl']:+,.2f} | "
                         f"{w['short_pnl']:+,.2f} | {w['equity_start']:,.2f} |")
    else:
        lines += ["", "Primera semana: todavía no hay semanas cerradas."]
    if report["status"] != "STOPPED":
        lines += ["", f"## Posiciones para la semana del {report['current_monday']}", "",
                  "| Símbolo | Dirección | Nocional |", "|---|---|---|"]
        for s, v in sorted(report["positions"].items()):
            side = "LARGO" if v > 0 else "CORTO" if v < 0 else "FUERA"
            lines.append(f"| {s} | {side} | {abs(v):,.2f} |")
    real_until = {s: d for s, d in report.get("real_funding_until", {}).items() if d}
    lines += ["", "Funding: tasas reales publicadas por Binance hasta "
              + (min(real_until.values()) if real_until else "—")
              + "; después, el supuesto del modelo (0.01% cada 8h, cobrado a ambos lados). "
              "Costos: 0.05% por lado + 5 bps (modelo; en PAPER no hay ejecuciones reales)."]
    return "\n".join(lines) + "\n"


def run(state_dir: Path, now: datetime, fetch: Fetcher = tw.fetch_daily,
        fetch_funding: FundingFetcher = tw.fetch_funding, live_limits: Path = LIVE_LIMITS) -> dict:
    state_path = state_dir / "state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text())
    else:
        allowed = json.loads(live_limits.read_text())["allowed_symbols"]
        state = new_state(now, list(dict.fromkeys([*allowed, *tw.EXTRA_SYMBOLS])))
    if state["status"] == "STOPPED":
        report = {"generated": now.isoformat(), "start": state["start"], "symbols": state["symbols"],
                  "current_monday": str(monday_of(now).date()), "status": "STOPPED", "weeks": [],
                  "equity": math.nan, "positions": {}}
        previous = state_dir / "latest.json"
        if previous.exists():
            report = {**json.loads(previous.read_text()), "generated": now.isoformat(), "status": "STOPPED"}
    else:
        report = evaluate(state, now, fetch, fetch_funding)
        state = apply_stop_rules(state, report)
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=1, ensure_ascii=False) + "\n")
    (state_dir / "latest.json").write_text(json.dumps(report, indent=1, default=str, ensure_ascii=False) + "\n")
    (state_dir / "report.md").write_text(render_es(state, report))
    if report.get("weeks"):
        history = state_dir / "history"
        history.mkdir(exist_ok=True)
        (history / f"{report['current_monday']}.json").write_text(
            json.dumps(report, indent=1, default=str, ensure_ascii=False) + "\n")
    return report


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Forward PAPER, two-way momentum (research only)")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args(argv)
    report = run(args.state_dir, datetime.now(timezone.utc))
    print((args.state_dir / "report.md").read_text())
    return 0 if report["status"] in ("PENDING", "RUNNING", "STOPPED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
