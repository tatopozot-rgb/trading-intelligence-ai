"""
A nightly risk review of every bot by Claude, that only WARNS (use 1 of docs/inteligencia/CREDITOS_CLAUDE_API.md,
approved by the leader on 2026-10-21). Each night it reads the PC's live_runs/, builds a short digest of every bot
(status, open positions with their stop, the last 24 hours, silent bots), and asks Claude Haiku 5.5 whether something
looks wrong: a position without a stop, a bot paused or braked, a bot gone silent, a result that does not add up.
Only when Haiku sees an alarm (or a check below already found something) a second look goes to Claude Sonnet 5.5, and
only what Sonnet confirms reaches the owner's Telegram.

    python -m trading_intelligence.live.revision_riesgo revisar    # Task Scheduler, every night (23:30 Ecuador)
    python -m trading_intelligence.live.revision_riesgo ver        # print the digest here; no Claude, no Telegram

What it never does: open, enlarge, close or pause a trade, touch config/ or any bot's state. It writes only its own
memory, live_runs/revision_riesgo/ultima.json. The API key is read from the environment variable ANTHROPIC_API_KEY
(set by the owner in Windows) and is never written, logged or sent anywhere but the API. Without the key, without the
``anthropic`` package, with no credits or with the API down, it logs one line and exits 0: every bot works as before.
The digest carries percentages, never the accounts' balances.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from trading_intelligence.live import resumen_diario as R
from trading_intelligence.live import telegram_notify
from trading_intelligence.live.messages import coin

logger = logging.getLogger(__name__)

KEY_VAR = "ANTHROPIC_API_KEY"
FIRST = "claude-haiku-5-5"  # every night: cheap
SECOND = "claude-sonnet-5-5"  # only when the first look sees an alarm
MAX_TOKENS = 4000
WINDOW = timedelta(hours=24)
MAX_POSITIONS = 3  # live/two_way.py: 3 positions at most per engine
MAX_DIGEST_CHARS = 60_000  # ~15k tokens: the whole PC fits many times over; a broken file cannot run the bill up

VERDICT = {
    "type": "object",
    "properties": {
        "alarma": {"type": "boolean"},
        "hallazgos": {"type": "array", "items": {"type": "string"}},
        "resumen": {"type": "string"},
    },
    "required": ["alarma", "hallazgos", "resumen"],
    "additionalProperties": False,
}

SYSTEM = """Eres el revisor de riesgo nocturno de un sistema de bots de trading. Recibes un resumen de cada bot \
(estado, posiciones abiertas con su stop y su meta, lo que pasó en las últimas 24 horas) y una lista de hallazgos \
que unas comprobaciones fijas ya encontraron.

Busca cosas raras de verdad:
- una posición abierta sin stop;
- más de 3 posiciones abiertas en un mismo bot;
- un bot callado (dejó de escribir su estado) sin haber terminado a propósito;
- un bot en pausa, frenado o detenido por su límite de pérdida;
- un resultado que no cuadra (pérdidas que no corresponden a un stop, cifras imposibles);
- cualquier cosa del bot de DINERO REAL que no sea normal.

No es una alarma: un día con pérdidas pequeñas cerradas por su stop, un bot sin operaciones, un bot que llegó a su \
meta o se detuvo a propósito ("terminó: sí"). Ante la duda en un bot de práctica, no hay alarma; ante la duda en el \
de dinero real, sí.

Tú solo avisas: no propongas abrir, cerrar ni agrandar operaciones, ni cambiar límites. Escribe en español simple, \
con frases cortas, para el dueño, que no es programador. Cada hallazgo: el bot y lo que pasa, en una línea. \
"resumen": una frase. Responde solo con el JSON pedido."""

Client = Any  # anthropic.Anthropic, or a test double with .messages.create and .beta.messages.create


# --- what the review reads -------------------------------------------------------------------------------------

def _load(path: Path) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _positions(bot: R.Bot, state: dict) -> list[dict]:
    """The bot's open positions with their stop and target, as its own state file keeps them."""
    if bot.kind == "motor":
        return [{"simbolo": coin(s), "lado": str(v.get("side", "BUY")), "entrada": v.get("entry"),
                 "stop": v.get("stop"), "meta": v.get("target")}
                for s, v in state.get("known", {}).items() if isinstance(v, dict)]
    if bot.kind == "londres" and isinstance(state.get("open"), dict):
        o = state["open"]
        return [{"simbolo": bot.name.rsplit(" ", 1)[-1], "lado": str(o.get("lado", "BUY")),
                 "entrada": o.get("entrada", o.get("precio")), "stop": o.get("stop", o.get("sl")),
                 "meta": o.get("meta", o.get("tp"))}]
    return [{"simbolo": p, "lado": "", "entrada": None, "stop": None, "meta": None} for p in bot.open_now]


def checks(bot: R.Bot, positions: Sequence[dict]) -> list[str]:
    """What needs no judgment: these always reach the second look."""
    found = []
    if bot.silent:
        found.append(f"{bot.name}: no escribe su estado desde hace rato (¿caído o PC apagada?).")
    if bot.kind != "nucleo":  # the core BTC bot holds spot BTC with an exit rule, not a stop order
        for p in positions:
            if not p.get("stop"):
                found.append(f"{bot.name}: la posición en {p['simbolo']} no tiene stop anotado.")
    if len(positions) > MAX_POSITIONS:
        found.append(f"{bot.name}: tiene {len(positions)} posiciones abiertas (el máximo es {MAX_POSITIONS}).")
    if bot.status and not bot.ended:
        found.append(f"{bot.name}: {bot.status}.")
    return found


def digest(root: Path, now: Optional[datetime] = None) -> tuple[str, list[str]]:
    """A short plain-text picture of every running bot, and the fixed checks' findings."""
    now = now or datetime.now(timezone.utc)
    lines: list[str] = []
    found: list[str] = []
    for bot in R.find_bots(root, now - WINDOW, now):
        positions = _positions(bot, _load(bot.path))
        found += checks(bot, positions)
        mins = int((now - bot.seen).total_seconds() // 60) if bot.seen else None
        lines.append(f"## {bot.name}")
        lines.append(f"tipo: {bot.kind} · dinero real: {'SÍ' if bot.real else 'no'} · estado: {bot.status or 'normal'}"
                     f" · terminó: {'sí' if bot.ended else 'no'} · callado: {'SÍ' if bot.silent else 'no'}"
                     f" · último estado hace {mins if mins is not None else '?'} min")
        lines.append(f"posiciones abiertas ({len(positions)}): " + ("; ".join(
            f"{p['simbolo']} {p['lado']} entrada {p['entrada'] or '?'} stop {p['stop'] or 'NINGUNO'} "
            f"meta {p['meta'] or '?'}" for p in positions) or "ninguna"))
        if bot.opened:
            lines.append("abrió en 24 h: " + ", ".join(f"{coin(s)} {v}" for s, v in bot.opened))
        if bot.closed:
            lines.append("cerró en 24 h: " + ", ".join(
                f"{coin(s)} {'gana' if r > 0 else 'pierde' if r < 0 else 'empate'}" for s, r, _ in bot.closed))
        if bot.pct is not None:
            lines.append(f"resultado de las 24 h: {bot.pct:+.2f}% de la cuenta")
        if bot.since_start is not None:
            lines.append(f"desde que empezó: {bot.since_start:+.2f}%")
        lines.append("")
    text = "\n".join(lines) or "No hay ningún bot funcionando en live_runs."
    return text[:MAX_DIGEST_CHARS], found


# --- Claude -------------------------------------------------------------------------------------------------

def make_client(env: Optional[Mapping[str, str]] = None) -> Optional[Client]:
    """The API client, or None without a key or without the ``anthropic`` package (then nothing changes)."""
    key = str((os.environ if env is None else env).get(KEY_VAR, "")).strip()
    if not key:
        return None
    try:
        import anthropic
    except ImportError:
        logger.warning("falta el paquete anthropic (pip install -r requirements-paper.txt): no hay revisión")
        return None
    return anthropic.Anthropic(api_key=key, timeout=120.0, max_retries=2)


def _ask(client: Client, model: str, prompt: str, effort: str) -> Optional[dict]:
    """One look; None if the call failed, Claude declined or the answer is not the verdict asked for."""
    kw: dict[str, Any] = dict(model=model, max_tokens=MAX_TOKENS, system=SYSTEM,
                              messages=[{"role": "user", "content": prompt}],
                              output_config={"effort": effort, "format": {"type": "json_schema", "schema": VERDICT}})
    try:
        if model == SECOND:  # a refusal is re-run on another model inside the same call
            response = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kw)
        else:
            response = client.messages.create(**kw)
    except Exception as error:  # noqa: BLE001 - no credits, network, API down: the bots carry on as before
        logger.warning("la revisión con %s falló (%s)", model, type(error).__name__)
        return None
    if getattr(response, "stop_reason", None) in ("refusal", "max_tokens"):
        logger.warning("la revisión con %s no terminó (%s)", model, response.stop_reason)
        return None
    try:
        text = next(b.text for b in response.content if getattr(b, "type", "") == "text")
        verdict = json.loads(text)
    except (StopIteration, ValueError, TypeError):
        logger.warning("la revisión con %s no devolvió el formato pedido", model)
        return None
    if not isinstance(verdict, dict) or not isinstance(verdict.get("alarma"), bool):
        return None
    verdict["hallazgos"] = [str(h) for h in verdict.get("hallazgos", []) if str(h).strip()][:10]
    verdict["modelo"] = model
    return verdict


def review(text: str, found: Sequence[str], client: Client) -> Optional[dict]:
    """Haiku first; Sonnet only for an alarm or a fixed check's finding. None when no look could be done."""
    fixed = "\n".join(f"- {f}" for f in found) or "- ninguno"
    prompt = f"Hallazgos de las comprobaciones fijas:\n{fixed}\n\nResumen de los bots:\n\n{text}"
    first = _ask(client, FIRST, prompt, "low")
    if not found and (first is None or not first["alarma"]):
        return first
    first_said = (f"\n\nUna primera revisión dijo: {json.dumps(first, ensure_ascii=False)}\nConfírmalo o corrígelo."
                  if first else "")
    second = _ask(client, SECOND, prompt + first_said, "medium")
    if second is not None:
        return second
    if first is not None and first["alarma"]:  # the second look failed: warn with the first one rather than nothing
        first["sin_confirmar"] = True
        return first
    # neither look could be done, but the fixed checks need no judgment
    return {"alarma": True, "hallazgos": list(found)[:10], "resumen": "Las comprobaciones fijas encontraron esto.",
            "modelo": "", "sin_confirmar": True}


def message(verdict: dict) -> str:
    lines = ["🔎 Revisión nocturna de riesgo (Claude)", ""]
    if str(verdict.get("resumen", "")).strip():
        lines.append(str(verdict["resumen"]).strip())
    lines += [f"• {h}" for h in verdict.get("hallazgos", [])]
    if verdict.get("sin_confirmar"):
        lines.append("(No se pudo confirmar con una segunda revisión.)")
    lines += ["", "Es solo un aviso: los bots siguen igual. Si algo te preocupa, díselo a Claude local."]
    return "\n".join(lines)


def run(root: Path, client: Optional[Client], send: Optional[Callable[[str], bool]],
        now: Optional[datetime] = None) -> Optional[dict]:
    """The nightly pass. Sends only an alarm; keeps the verdict in live_runs/revision_riesgo/ultima.json."""
    now = now or datetime.now(timezone.utc)
    if client is None:
        logger.info("sin %s: no hay revisión con Claude esta noche (los bots siguen igual)", KEY_VAR)
        return None
    text, found = digest(root, now)
    verdict = review(text, found, client)
    if verdict is None:
        return None
    verdict["enviado"] = bool(verdict["alarma"] and send is not None and send(message(verdict)))
    R._save(root / "revision_riesgo" / "ultima.json", {"at": now.isoformat(), **verdict})
    return verdict


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Revisión nocturna de riesgo con Claude: solo avisa")
    parser.add_argument("cmd", choices=("revisar", "ver"))
    parser.add_argument("--runs", type=Path, default=R.RUNS, help="carpeta live_runs de la PC")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.cmd == "ver":
        text, found = digest(args.runs)
        telegram_notify.console(text + "\nComprobaciones fijas:\n" + ("\n".join(found) or "ninguna"))
        return 0
    notifier = telegram_notify.from_env()
    verdict = run(args.runs, make_client(), notifier.send if notifier else None)
    if verdict is not None:
        telegram_notify.console(message(verdict) if verdict["alarma"] else f"sin alarma: {verdict.get('resumen', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
