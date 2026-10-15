"""
One Telegram summary a day, at 22:00 Ecuador, of what every PRACTICE bot did. Owner, 2026-10-15: "los de la cuenta
de dinero ficticio las notificaciones mejor dame a las 10 detalle lo que paso ... palabras entendibles". The practice
bots no longer message each trade (live/two_way.py PRACTICE_TELEGRAM); they leave it in their state files and this
reads them: trades opened and closed, the result in money and in %, and one line of conclusion. Alarms (a limit, a
failure, a bot that stopped answering) still go at once.

    python -m trading_intelligence.live.resumen_diario enviar     # Task Scheduler, every day at 22:00 Ecuador
    python -m trading_intelligence.live.resumen_diario ver        # print it here, send nothing
    python -m trading_intelligence.live.resumen_diario vigilar    # Task Scheduler, every 10 minutes: a bot down?

It reads only the PC's live_runs/ (never committed): the real bot's amounts go to the owner's Telegram and nowhere
else. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from trading_intelligence.live import telegram_notify
from trading_intelligence.live.messages import coin, num

logger = logging.getLogger(__name__)

ECUADOR = timezone(timedelta(hours=-5))
RUNS = Path("live_runs")
MEMORY = Path("live_runs/resumen_diario")  # when the last summary went out, and which bots are reported down
LIVE_DAYS = 3  # a state file untouched for longer belongs to a bot that was retired
# how long each kind of bot may stay silent before it counts as down (it writes its state at every pass)
SILENT = {"motor": timedelta(minutes=20), "londres": timedelta(minutes=30), "nucleo": timedelta(hours=3)}
ENDED = ("STOPPED", "GOAL")  # an engine that ended its session on purpose is not down


@dataclass
class Bot:
    name: str
    path: Path
    kind: str  # motor (two-way engine), londres, nucleo
    real: bool
    currency: str = ""
    opened: list[tuple[str, str]] = field(default_factory=list)  # (symbol, side)
    closed: list[tuple[str, Decimal, bool]] = field(default_factory=list)  # (symbol, result, exact)
    pct: Optional[Decimal] = None  # the window's result, % of the account
    since_start: Optional[Decimal] = None  # % since the bot started (own account only)
    open_now: list[str] = field(default_factory=list)
    status: str = ""
    seen: Optional[datetime] = None  # last time it wrote its state
    ended: bool = False
    silent: bool = False  # it stopped writing its state: down, or the PC is off

    @property
    def result(self) -> Decimal:
        return sum((r for _, r, _ in self.closed), Decimal("0"))


def _d(value: Any) -> Optional[Decimal]:
    try:
        out = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return out if out.is_finite() else None


def _at(value: Any) -> Optional[datetime]:
    try:
        t = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _side(side: str) -> str:
    return "compra" if side == "BUY" else "venta"


def _money(value: Decimal, currency: str) -> str:
    sign = "+" if value > 0 else "-" if value < 0 else ""
    return f"{sign}{num(abs(value))}{' ' + currency if currency else ''}"


def _pct(value: Decimal) -> str:
    return ("+" if value > 0 else "-" if value < 0 else "") + num(abs(value), 1) + "%"


# --- reading each kind of bot ------------------------------------------------------------------------------

def _motor(path: Path, d: dict, since: datetime) -> Bot:
    real = "real" in [p.lower() for p in path.parent.parts] or "DINERO REAL" in str(d.get("name", ""))
    currency = str(d.get("currency") or ("USDT" if "futures_auto" in path.as_posix() else ""))  # older states
    bot = Bot(_motor_name(path, d, real), path, "motor", real, currency)
    for e in d.get("events", []):
        at = _at(e.get("at"))
        if at is None or at < since:
            continue
        kind = e.get("kind")
        if kind == "OPEN":
            sym, side = e.get("symbol"), e.get("side")
            if not sym:  # before 2026-10-15: "BUY 0.1 SOLUSDT @ ..."
                m = re.match(r"(BUY|SELL) \S+ (\S+) @", str(e.get("text", "")))
                side, sym = (m.group(1), m.group(2)) if m else ("BUY", "?")
            bot.opened.append((str(sym), str(side)))
        elif kind == "RESULT":
            pnl = _d(e.get("pnl"))
            if pnl is not None:
                bot.closed.append((str(e.get("symbol", "?")), pnl, bool(e.get("exact"))))
    book = _paper_closes(path.parent / "paper.json", since)
    if book is not None:  # a practice futures account keeps every close with its result: the full record
        bot.closed = book
    equity, capital = _d(d.get("equity")), _d(d.get("capital"))
    if equity and equity > 0 and bot.closed:
        bot.pct = bot.result / equity * 100
    if equity and capital and capital > 0 and "XM" not in bot.name:  # XM agents share one demo account
        bot.since_start = (equity / capital - 1) * 100
    bot.open_now = [f"{coin(s)} ({_side(str(v.get('side', 'BUY')))})" for s, v in d.get("known", {}).items()
                    if isinstance(v, dict)]
    status = str(d.get("status", ""))
    bot.ended = status in ENDED
    bot.status = {"STOPPED": "detenido: llegó a su límite de pérdida", "GOAL": "cumplió la meta del mes",
                  "WAITING_OWNER": "en pausa: espera tu 'continuar' (cerca del límite de pérdida)",
                  "PAUSED_API": "en pausa por fallos de conexión"}.get(status, "")
    if d.get("halted"):
        bot.status = "frenado hasta mañana por la pérdida del día"
    return bot


def _motor_name(path: Path, d: dict, real: bool) -> str:
    """A clear name. Practice futures accounts are told apart by their leverage, from the folder
    (live_runs/futures_auto/shadow is 1x, live_runs/futures_auto_3x/shadow is 3x); the header already says the
    practice money is fictitious."""
    folder = path.parent.parent.name if path.parent.name in ("shadow", "real") else path.parent.name
    if not real and folder.startswith("futures_auto"):
        lev = re.search(r"(\d+)x", folder) or re.search(r"(\d+)x", str(d.get("name", "")))
        return f"🧪 Futuros práctica {lev.group(1) if lev else 1}x"
    name = str(d.get("name") or "")
    if not name and folder.startswith("xm_auto"):
        agent = folder.removeprefix("xm_auto").strip("_")
        name = f"🧪 XM DEMO · {agent.capitalize()}" if agent else "🧪 XM DEMO"
    if not name and real:
        name = "💰 Binance Futuros · DINERO REAL"
    return re.sub(r"\s*\(dinero (ficticio|virtual)\)", "", name or folder)


def _paper_closes(path: Path, since: datetime) -> Optional[list[tuple[str, Decimal, bool]]]:
    """The closes of a practice futures account since ``since``, from its own book; None without a book."""
    if not path.exists():
        return None
    try:
        book = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    out = []
    for row in book.get("closed", []) if isinstance(book, dict) else []:
        at, pnl = _at(row.get("at")), _d(row.get("pnl"))
        if at is not None and at >= since and pnl is not None:
            out.append((str(row.get("symbol", "?")), pnl, True))
    return out


def _londres(path: Path, d: dict, since: datetime) -> Bot:
    bot = Bot("🧪 XM DEMO · Londres oro", path, "londres", False, str(d.get("moneda", "")))
    for t in d.get("trades", []):
        at = _at(t.get("t"))
        if at is None or at < since:
            continue
        if t.get("accion") == "entrada":
            bot.opened.append(("Oro", str(t.get("lado", "BUY"))))
        elif t.get("accion") == "cierre" and _d(t.get("pnl")) is not None:
            bot.closed.append(("Oro", _d(t["pnl"]) or Decimal("0"), not t.get("estimado")))
    if d.get("open"):
        bot.open_now = [f"Oro ({_side(str(d['open'].get('lado', 'BUY')))})"]
    return bot


def _nucleo(path: Path, d: dict, since: datetime) -> Bot:
    means = path.stem.split("_")[1:]
    label = "+".join(means) if means else "50"
    real = path.stem.startswith("real")
    bot = Bot(f"{'💰' if real else '🧭'} Núcleo BTC {label}{' · DINERO REAL' if real else ''}", path, "nucleo", real,
              "USDT")
    for t in d.get("trades", []):
        at = _at(t.get("time"))
        if at is None or at < since:
            continue
        if t.get("side") == "BUY":
            bot.opened.append(("BTC", "BUY"))
        elif t.get("side") == "SELL" and _d(t.get("pnl")) is not None:
            bot.closed.append(("BTC", _d(t["pnl"]) or Decimal("0"), True))
    start, equity = _d(d.get("start_capital")), _d(d.get("equity"))
    if equity is None and start is not None:
        equity = (_d(d.get("cash")) or Decimal("0")) + (_d(d.get("qty")) or Decimal("0")) * (_d(d.get("entry")) or Decimal("0"))
    if equity and equity > 0 and bot.closed:
        bot.pct = bot.result / equity * 100
    if equity is not None and start and start > 0:
        bot.since_start = (equity / start - 1) * 100
    if (_d(d.get("qty")) or Decimal("0")) > 0:
        bot.open_now = ["BTC (compra)"]
    bot.ended = bool(d.get("halted"))
    return bot


def _live(path: Path, root: Path, now: datetime) -> Optional[datetime]:
    """When a running bot last wrote this file; None for an archive, a test folder or a retired bot."""
    parts = [x.lower() for x in path.relative_to(root).parts]
    if any("archivo" in x or "prueba" in x or x == "resumen_diario" for x in parts):
        return None
    try:
        written = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None
    return written if now - written < timedelta(days=LIVE_DAYS) else None


def find_bots(root: Path, since: datetime, now: Optional[datetime] = None) -> list[Bot]:
    now = now or datetime.now(timezone.utc)
    bots: list[Bot] = []
    for path in sorted(root.rglob("*.json")) if root.exists() else []:
        if path.name.endswith("orders.json"):
            continue
        seen = _live(path, root, now)
        if seen is None:
            continue
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        if path.name == "state.json" and "known" in d and "events" in d:
            bot = _motor(path, d, since)
        elif path.name == "state.json" and "trades" in d and "done" in d:
            bot = _londres(path, d, since)
        elif "start_capital" in d and "trades" in d and "qty" in d:
            bot = _nucleo(path, d, since)
        else:
            continue
        bot.seen = seen
        bot.silent = not bot.ended and now - seen > SILENT[bot.kind]
        bots.append(bot)
    return bots


# --- the message -------------------------------------------------------------------------------------------

def _block(bot: Bot) -> list[str]:
    lines = [bot.name]
    if bot.opened:
        lines.append(f"• Abrió {len(bot.opened)}: " + ", ".join(f"{coin(s)} {_side(v)}" for s, v in bot.opened))
    if bot.closed:
        parts = [f"{coin(s)} {'✅' if r > 0 else '❌' if r < 0 else '➖'} {_money(r, bot.currency)}{'' if ok else ' aprox.'}"
                 for s, r, ok in bot.closed]
        lines.append(f"• Cerró {len(bot.closed)}: " + ", ".join(parts))
    if not bot.opened and not bot.closed:
        lines.append("• Sin operaciones: ninguna señal pasó todas las reglas.")
    if bot.closed:
        share = f" ({_pct(bot.pct)} de la cuenta)" if bot.pct is not None else ""
        lines.append(f"• Resultado del día: {_money(bot.result, bot.currency)}{share}")
    if bot.since_start is not None:
        lines.append(f"• Desde que empezó: {_pct(bot.since_start)}")
    if bot.open_now:
        lines.append("• Sigue abierta: " + ", ".join(bot.open_now))
    if bot.status:
        lines.append(f"• Estado: {bot.status}")
    if bot.silent and bot.seen is not None:
        lines.append(f"• ⚠️ No da señales de vida desde las {bot.seen.astimezone(ECUADOR):%H:%M} (hora de Ecuador).")
    return lines


def conclusion(bots: Sequence[Bot]) -> str:
    traded = [b for b in bots if b.closed]
    wins = sum(1 for b in bots for _, r, _ in b.closed if r > 0)
    losses = sum(1 for b in bots for _, r, _ in b.closed if r < 0)
    opened = sum(len(b.opened) for b in bots)
    down = [b.name for b in bots if b.silent]
    tail = f" ⚠️ Revisar: {', '.join(down)} no responde." if down else ""
    if not traded:
        if opened:
            return f"📌 Conclusión: abrieron {opened} operaciones y todavía no cerró ninguna; el resultado llega cuando cierren.{tail}"
        return ("📌 Conclusión: día tranquilo, ningún bot de práctica operó. Es normal cuando el mercado no da "
                f"señales claras: no forzar entradas también es parte del plan.{tail}")
    ranked = sorted(traded, key=lambda b: b.pct if b.pct is not None else b.result)
    best, worst = ranked[-1], ranked[0]
    score = f"{wins + losses} cerradas: {wins} ganadas y {losses} perdidas"
    if wins > losses:
        head = f"📌 Conclusión: buen día en práctica 👍 ({score})."
    elif losses > wins:
        head = f"📌 Conclusión: día en rojo en práctica ({score}). Es dinero ficticio: sirve para medir, no se toca nada real."
    else:
        head = f"📌 Conclusión: día parejo en práctica ({score})."
    detail = []
    if best.result > 0:
        detail.append(f"El mejor fue {best.name} ({_money(best.result, best.currency)})")
    if worst.result < 0 and worst is not best:
        detail.append(f"el que más perdió fue {worst.name} ({_money(worst.result, worst.currency)})")
    text = "; ".join(detail)
    return head + (" " + text[:1].upper() + text[1:] + "." if text else "") + tail  # each sentence starts upper


def render(bots: Sequence[Bot], now: datetime) -> str:
    practice = [b for b in bots if not b.real]
    real = [b for b in bots if b.real]
    local = now.astimezone(ECUADOR)
    out = ["🌙 Resumen del día · bots de práctica (dinero ficticio)", f"{local:%d-%m-%Y}, {local:%H:%M} hora de Ecuador", ""]
    if not practice:
        out += ["No encontré bots de práctica funcionando en la PC.", ""]
    for bot in practice:
        out += _block(bot) + [""]
    if real:
        out.append("💰 Dinero real (cada operación ya te llegó al abrir y al cerrar):")
        for bot in real:
            result = f", resultado {_money(bot.result, bot.currency)}" if bot.closed else ""
            alive = " ⚠️ no da señales de vida" if bot.silent else ""
            held = f" Abiertas: {', '.join(bot.open_now)}." if bot.open_now else ""
            out.append(f"• {bot.name}: hoy abrió {len(bot.opened)} y cerró {len(bot.closed)}"
                       f"{result}.{held}{alive}")
        out.append("")
    out.append(conclusion(practice))
    return "\n".join(out)


# --- memory: the last summary, and which bots were reported down -------------------------------------------

def _load(path: Path) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(path)


def window_start(memory: Path, now: datetime) -> datetime:
    """Since the last summary that went out (between 1 and 48 hours back); 24 hours the first time."""
    last = _at(_load(memory / "ultimo.json").get("enviado"))
    if last is None:
        return now - timedelta(hours=24)
    return min(max(last, now - timedelta(hours=48)), now - timedelta(hours=1))


def daily(root: Path, memory: Path, send: Optional[Callable[[str], bool]], now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    text = render(find_bots(root, window_start(memory, now), now), now)
    if send is not None and send(text):
        _save(memory / "ultimo.json", {"enviado": now.isoformat()})
    return text


def watch(root: Path, memory: Path, send: Callable[[str], object], now: Optional[datetime] = None) -> list[str]:
    """A bot that stopped writing its state is told once, at once; and again when it is back."""
    now = now or datetime.now(timezone.utc)
    told = _load(memory / "vigilancia.json")
    sent: list[str] = []
    seen_paths = set()
    for bot in find_bots(root, now, now):
        key = str(bot.path)
        seen_paths.add(key)
        silent = bot.silent
        if silent and key not in told:
            last = bot.seen.astimezone(ECUADOR) if bot.seen else None
            msg = (f"🚨 {bot.name}: no da señales de vida desde las {last:%H:%M} (hora de Ecuador). Puede que se "
                   f"haya caído o que la PC esté apagada. Díselo a Claude local para que lo revise y lo reinicie. "
                   f"Si lo apagaste a propósito, ignora este aviso." if last else f"🚨 {bot.name}: no da señales de vida.")
            send(msg)
            sent.append(msg)
            told[key] = now.isoformat()
        elif not silent and key in told:
            msg = f"✅ {bot.name}: volvió a funcionar."
            send(msg)
            sent.append(msg)
            told.pop(key)
    for key in [k for k in told if k not in seen_paths]:  # retired for good: forget it
        told.pop(key)
    _save(memory / "vigilancia.json", told)
    return sent


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Resumen diario de los bots de práctica y vigilancia de bots caídos")
    parser.add_argument("cmd", choices=("enviar", "ver", "vigilar"))
    parser.add_argument("--runs", type=Path, default=RUNS, help="carpeta live_runs de la PC")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    memory = args.runs / "resumen_diario"
    if args.cmd == "ver":
        telegram_notify.console(daily(args.runs, memory, None))
        return 0
    notifier = telegram_notify.from_env()
    if notifier is None:
        print(f"faltan o no son válidas {telegram_notify.TOKEN_VAR} / {telegram_notify.CHAT_VAR}")
        return 1
    if args.cmd == "vigilar":
        for msg in watch(args.runs, memory, notifier.send):
            telegram_notify.console(msg)
        return 0
    text = daily(args.runs, memory, notifier.send)
    telegram_notify.console(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
