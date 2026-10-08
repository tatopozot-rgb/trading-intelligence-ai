"""Session report (inicio / medio / final) for the owner and for GPT Work's audit:
decisions and why, agents used and not used, money won or lost, coins, fees, events."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Mapping

from trading_intelligence.live.limits import OwnerLimits
from trading_intelligence.live.session import Session

STAGE = {"inicio": "INICIO", "medio": "MEDIO", "final": "FINAL"}


def render_report(stage: str, s: Session, prices: Mapping[str, Decimal], limits: OwnerLimits, *, real: bool,
                  profile: str, agents_used: list[str], all_agents: list[str], decisions: list[dict],
                  timeframe: str, symbols: list[str]) -> str:
    equity = s.equity(prices)
    pnl = equity - s.capital
    unrealized = pnl - s.realized_pnl
    coins = sorted({t["symbol"] for t in s.trades})
    sells = [t for t in s.trades if t["side"] == "SELL"]
    wins = sum(1 for t in sells if t["pnl"] is not None and Decimal(t["pnl"]) > 0)
    out = [
        f"# Reporte de trading — {STAGE[stage]}",
        "",
        f"- sesión `{s.session_id}` · modo **{'REAL' if real else 'SHADOW (simulado, sin órdenes)'}** · perfil "
        f"**{profile}** · temporalidad {timeframe} · estado **{s.status}**",
        f"- capital asignado: **{s.capital:.2f} USDT** · valor actual: **{equity:.2f}** · resultado: "
        f"**{pnl:+.2f} USDT** (realizado {s.realized_pnl:+.2f}, abierto {unrealized:+.2f}) · comisiones {s.fees:.2f}",
        f"- límite de pérdida: {limits.loss_limit_usd(s.capital):.2f} USDT ({limits.loss_limit_pct}%) · aviso a "
        f"{limits.warn_at_usd(s.capital):.2f} USDT · máximo por posición {limits.max_position_pct}% · "
        f"posiciones abiertas máx. {limits.max_open_positions}",
        f"- mercados vigilados: {' '.join(symbols)}",
        f"- monedas operadas: {', '.join(coins) or 'ninguna todavía'} · ventas {len(sells)} (ganadoras {wins})",
        "",
        "## Posiciones abiertas",
        "",
    ]
    if s.holdings:
        out += ["| moneda | cantidad | costo | valor | resultado |", "|---|---|---|---|---|"]
        for sym, h in sorted(s.holdings.items()):
            value = h.qty * prices[sym]
            out.append(f"| {sym} | {h.qty} | {h.cost:.2f} | {value:.2f} | {value - h.cost:+.2f} |")
    else:
        out.append("Ninguna.")
    out += ["", "## Operaciones", ""]
    if s.trades:
        out += ["| hora | lado | moneda | cantidad | USDT | comisión | resultado | motivo |", "|---|---|---|---|---|---|---|---|"]
        for t in s.trades[-40:]:
            result = "" if t["pnl"] is None else f"{Decimal(t['pnl']):+.2f}"
            out.append(f"| {t['at']} | {t['side']} | {t['symbol']} | {t['qty']} | {Decimal(t['usdt']):.2f} "
                       f"| {Decimal(t['fee_usdt']):.4f} | {result} | {t['reason']} |")
    else:
        out.append("Ninguna todavía.")
    out += ["", "## Cómo se tomaron las decisiones", ""]
    if decisions:
        counts = Counter(d.get("action", "?").split(":")[0] for d in decisions)
        out.append("Decisiones del motor por vela (todas las monedas): " +
                   ", ".join(f"{k} {v}" for k, v in counts.most_common()))
        latest: dict[str, dict] = {}
        for d in decisions:
            latest[d.get("symbol", "?")] = d
        out += ["", "| moneda | vela | régimen | decisión |", "|---|---|---|---|"]
        for sym in sorted(latest):
            d = latest[sym]
            out.append(f"| {sym} | {d.get('bar')} | {d.get('regime')} | {d.get('action')} |")
    else:
        out.append("Sin decisiones registradas todavía (o perfil copiar: decide la posición del líder).")
    out += ["", "## Agentes", "",
            "Usados: " + ", ".join(agents_used) + ".",
            "No usados en esta sesión: " + (", ".join(a for a in all_agents if a not in agents_used) or "ninguno") + ".",
            "Todas las órdenes salen del operador; el motor de riesgo y la guardia de pérdida pueden vetarlas.",
            "", "## Eventos", ""]
    out += [f"- {e['at']} **{e['kind']}**: {e['text']}" for e in s.events[-30:]] or ["Ninguno."]
    out.append("")
    return "\n".join(out)
