"""
"Claude decide": a forward experiment on XM DEMO only. Owner, 2026-10-22: the cost does not matter, he wants bots
that analyse more with Claude. Leader, same day: try it only on virtual money, because a backtest of "Claude decides"
is contaminated (Claude has read the history it would be tested on: docs/inteligencia/IA_QUE_OPERA.md), so it can only
be judged forward. How it is judged, and the monthly spend cap, are preregistered in
docs/research/claude_decide/PREREGISTRO.md before the first order.

    python -m trading_intelligence.live.xm_claude            # one pass (Task Scheduler, every 5 minutes)
    python -m trading_intelligence.live.xm_claude resumen    # where it stands

What Claude decides and what it does not:
- Claude reads the market (1h, 4h and daily candles with a few indicators, spread, its own open position and its last
  trades) once per closed hour per symbol and answers COMPRAR, VENDER, ESPERAR, CERRAR or MANTENER, with a stop, a
  target, a confidence and its reason. Each answer is logged in decisiones.jsonl, whatever happens next.
- The code decides how much and whether it is allowed (Claude never sizes a trade and cannot skip a rule):
  every entry carries a stop and a target; stop 0.2-5% from the price; target 1.5-6 times the stop distance (small
  loss, large gain); fixed risk of 1% of a nominal 1,000 USD, never raised after a loss (no martingale); size at most
  5x the nominal; 2 open positions at most; 2 entries per symbol per day; no new entries after -2R in the day; the
  experiment stops itself at -15% of the nominal or -10R. Then XmDemoTrader: DEMO re-checked before each order,
  pre-entry check (spread, margin, market open), MT5's order_check, own MAGIC, journal before sending.
- Spend: the API costs are counted per call from the usage the API returns; at the monthly cap no more calls are made
  (open positions keep their stop and target resting on XM's server). The key is only the environment variable
  ANTHROPIC_API_KEY on the PC, never in the repository. No key, no credits or the cap reached: no calls, no trades.
- MAGIC: agent_magic("Claude decide"), apart from every other agent on the shared DEMO account.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

import pandas as pd

from trading_intelligence.live.telegram_notify import console, from_env, make_notify
from trading_intelligence.live.xm_auto import agent_magic
from trading_intelligence.live.xm_demo import XM_MAX_STOP_PCT, XM_MIN_STOP_PCT, XmDemoTrader
from trading_intelligence.live.xm_mt5 import EntryCaps, XmError

AGENT = "Claude decide"
SYMBOLS = ("GOLD", "BTCUSD")  # the same markets as the London bots, so the two are compared on the same days
NOMINAL = Decimal("1000")
RISK_PCT = Decimal("1")
MAX_LEVERAGE = Decimal("5")
MIN_RR, MAX_RR = Decimal("1.5"), Decimal("6")
MAX_OPEN = 2
MAX_ENTRIES_PER_DAY = 2  # per symbol
DAY_LOSS_R = Decimal("-2")
HALT_LOSS_PCT, HALT_R = Decimal("15"), Decimal("-10")
DECIDE_EVERY_MIN = 60
BUDGET_USD = Decimal("40")
CALL_RESERVE_USD = Decimal("0.25")  # most one call can cost (8,000 output tokens on Opus): checked before calling
MODEL, EFFORT = "claude-opus-5-5", "medium"
MAX_TOKENS = 8000
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# USD per million tokens: input, output, cache write, cache read (Anthropic's list prices, 2026-10)
PRICES = {"claude-opus-5-5": (4.0, 20.0, 5.0, 0.20), "claude-sonnet-5-5": (2.0, 10.0, 2.5, 0.20),
          "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.01), "claude-opus-4-8": (5.0, 25.0, 6.25, 0.50)}
PRICE_UNKNOWN = (5.0, 25.0, 6.25, 0.50)  # a fallback model not listed is charged at the dearest Opus price
DEFAULT_DIR = Path("live_runs/xm_claude")
TAG = "🧪 XM DEMO · Claude decide (experimento)"
ENTRY, EXIT = ("COMPRAR", "VENDER"), ("CERRAR", "MANTENER")
ACTIONS = ("COMPRAR", "VENDER", "ESPERAR", "CERRAR", "MANTENER")

SYSTEM = """Eres el analista de un bot de práctica en una cuenta DEMO de XM (dinero virtual). Cada hora recibes los \
datos de un mercado y decides una sola cosa para ese mercado.

Sin posición abierta respondes COMPRAR, VENDER o ESPERAR. Con posición abierta respondes MANTENER o CERRAR.
Para COMPRAR o VENDER das un stop y una meta en precio:
- el stop va al otro lado del precio, entre 0,2 % y 5 % de distancia, donde tu idea queda invalidada;
- la meta va a entre 1,5 y 6 veces la distancia del stop: pérdidas chicas y ganancias grandes;
- el código fija el tamaño (1 % de riesgo); tú no lo eliges. Si tu stop o tu meta no cumplen, la entrada se rechaza.
Para ESPERAR, MANTENER o CERRAR pon stop 0 y meta 0.

ESPERAR es una respuesta buena cuando no ves una ventaja clara: cada operación paga el spread. No persigas pérdidas \
ni subas el riesgo tras perder. Tu confianza va de 0 a 100. Tu razón: dos o tres frases en español simple, con el \
dato que la sostiene (tendencia, nivel, volatilidad), para que el dueño la lea en el registro."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "accion": {"type": "string", "enum": list(ACTIONS)},
        "stop": {"type": "number"},
        "meta": {"type": "number"},
        "confianza": {"type": "integer"},
        "razon": {"type": "string"},
    },
    "required": ["accion", "stop", "meta", "confianza", "razon"],
    "additionalProperties": False,
}
PROMPT_VERSION = hashlib.sha256((SYSTEM + json.dumps(SCHEMA, sort_keys=True)).encode()).hexdigest()[:10]

Candles = Callable[[str, str, int], pd.DataFrame]


@dataclass(frozen=True)
class Decision:
    accion: str
    stop: float
    meta: float
    confianza: int
    razon: str


@dataclass(frozen=True)
class Usage:
    model: str
    cost_usd: float
    input_tokens: int = 0
    output_tokens: int = 0


class Decider(Protocol):
    def decide(self, brief: str) -> tuple[Decision, Usage]: ...


WAIT_ON_ERROR = "ESPERAR"


def parse_decision(text: str) -> Decision:
    """The first JSON object in the text, checked against SCHEMA; anything else raises ValueError."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        raise ValueError("la respuesta de Claude no trae JSON")
    raw = json.loads(match.group(0))
    if not isinstance(raw, dict) or set(SCHEMA["required"]) - set(raw):
        raise ValueError("la respuesta de Claude no trae todos los campos")
    accion = str(raw["accion"]).upper()
    if accion not in ACTIONS:
        raise ValueError(f"acción desconocida: {accion}")
    stop, meta = float(raw["stop"]), float(raw["meta"])
    if not (math.isfinite(stop) and math.isfinite(meta)):
        raise ValueError("stop o meta no son números")
    return Decision(accion, stop, meta, max(0, min(100, int(raw["confianza"]))), str(raw["razon"])[:1000])


def call_cost(model: str, input_tokens: int, output_tokens: int, cache_write: int = 0, cache_read: int = 0) -> float:
    p_in, p_out, p_cw, p_cr = PRICES.get(model, PRICE_UNKNOWN)
    return (input_tokens * p_in + output_tokens * p_out + cache_write * p_cw + cache_read * p_cr) / 1_000_000


class ApiDecider:
    """Claude through the Anthropic API (key from ANTHROPIC_API_KEY), with a JSON answer enforced by the schema."""

    def __init__(self, model: str = MODEL, effort: str = EFFORT, client: Optional[Any] = None) -> None:
        if client is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise XmError("falta la variable de entorno ANTHROPIC_API_KEY (la clave nunca va en el repositorio)")
            import anthropic

            client = anthropic.Anthropic()
        self.client, self.model, self.effort = client, model, effort

    def decide(self, brief: str) -> tuple[Decision, Usage]:
        response = self.client.beta.messages.create(
            model=self.model, max_tokens=MAX_TOKENS, betas=[FALLBACK_BETA], fallbacks="default",
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": brief}])
        u = response.usage
        served = str(getattr(response, "model", self.model))
        tokens_in, tokens_out = int(u.input_tokens or 0), int(u.output_tokens or 0)
        cost = call_cost(served, tokens_in, tokens_out, int(getattr(u, "cache_creation_input_tokens", 0) or 0),
                         int(getattr(u, "cache_read_input_tokens", 0) or 0))
        usage = Usage(served, cost, tokens_in, tokens_out)
        if response.stop_reason in ("refusal", "max_tokens"):
            return Decision(WAIT_ON_ERROR, 0, 0, 0, f"sin decisión (Claude terminó por {response.stop_reason})"), usage
        text = next((b.text for b in response.content if getattr(b, "type", "") == "text"), "")
        return parse_decision(text), usage


class _NoDecider:
    def decide(self, brief: str) -> tuple[Decision, Usage]:
        raise XmError("el resumen no pregunta a Claude")


def _indicators(frame: pd.DataFrame) -> dict[str, float]:
    close, high, low = frame["close"], frame["high"], frame["low"]
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    delta = close.diff()
    gain, loss = delta.clip(lower=0).rolling(14).mean(), (-delta.clip(upper=0)).rolling(14).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, float("nan")))
    out = {"ema20": float(close.ewm(span=20).mean().iloc[-1]), "ema50": float(close.ewm(span=50).mean().iloc[-1]),
           "atr14": float(tr.rolling(14).mean().iloc[-1]), "rsi14": float(rsi.iloc[-1])}
    return {k: round(v, 5) for k, v in out.items() if math.isfinite(v)}


def _rows(frame: pd.DataFrame, n: int) -> str:
    tail = frame.tail(n)
    return "\n".join(f"{t:%Y-%m-%d %H:%M},{r.open:.5g},{r.high:.5g},{r.low:.5g},{r.close:.5g}"
                     for t, r in tail.iterrows())


def market_brief(symbol: str, now: datetime, bid: float, ask: float, spread_pct: float,
                 frames: dict[str, pd.DataFrame], position: Optional[dict], history: list[dict]) -> str:
    """What Claude reads: the same layout every hour, so its answers are comparable."""
    lines = [f"Mercado: {symbol} (XM, CFD). Ahora: {now:%Y-%m-%d %H:%M} UTC. Bid {bid} · ask {ask} · spread "
             f"{spread_pct:.3f} % del precio."]
    for tf, n in (("1d", 30), ("4h", 30), ("1h", 48)):
        frame = frames[tf]
        lines.append(f"\nVelas {tf} (hora del servidor XM; fecha,apertura,máximo,mínimo,cierre), últimas {n}. "
                     f"Indicadores {tf}: {json.dumps(_indicators(frame))}")
        lines.append(_rows(frame, n))
    if position:
        lines.append(f"\nPosición abierta: {position['lado']} a {position['precio']} · stop {position['sl']} · "
                     f"meta {position['tp']} · desde {position['t']}. Responde MANTENER o CERRAR.")
    else:
        lines.append("\nSin posición abierta en este mercado. Responde COMPRAR, VENDER o ESPERAR.")
    if history:
        lines.append("Tus últimas operaciones cerradas aquí: " + "; ".join(
            f"{h['lado']} {h['motivo']} {h['r']}R" for h in history[-10:]))
    return "\n".join(lines)


def check_decision(d: Decision, price: float, has_position: bool) -> list[str]:
    """The code's rules on Claude's answer; empty = allowed. Sizing is never Claude's."""
    if has_position:
        return [] if d.accion in EXIT else [f"con posición abierta solo vale MANTENER o CERRAR, no {d.accion}"]
    if d.accion not in ENTRY + ("ESPERAR",):
        return [f"sin posición no vale {d.accion}"]
    if d.accion == "ESPERAR":
        return []
    sign = 1 if d.accion == "COMPRAR" else -1
    risk, reward = sign * (price - d.stop), sign * (d.meta - price)
    if risk <= 0 or reward <= 0:
        return [f"stop {d.stop} o meta {d.meta} del lado equivocado del precio {price}"]
    no = []
    stop_pct = Decimal(str(risk / price * 100))
    if not XM_MIN_STOP_PCT <= stop_pct <= XM_MAX_STOP_PCT:
        no.append(f"stop a {stop_pct:.2f} % del precio, fuera de {XM_MIN_STOP_PCT}-{XM_MAX_STOP_PCT} %")
    rr = Decimal(str(reward / risk))
    if not MIN_RR <= rr <= MAX_RR:
        no.append(f"meta a {rr:.2f} veces el stop, fuera de {MIN_RR}-{MAX_RR}")
    return no


class ClaudeBot:
    def __init__(self, trader: XmDemoTrader, folder: Path, decider: Decider, notify: Callable[[str], None],
                 alarm: Optional[Callable[[str], None]] = None, symbols: tuple[str, ...] = SYMBOLS,
                 nominal: Decimal = NOMINAL, budget: Decimal = BUDGET_USD, every_min: int = DECIDE_EVERY_MIN,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 candles: Optional[Candles] = None) -> None:
        if nominal <= 0 or budget < 0 or every_min <= 0:
            raise ValueError("capital nominal, tope y cadencia tienen que ser positivos")
        self.trader, self.folder, self.decider, self.notify = trader, Path(folder), decider, notify
        self.alarm = alarm or notify
        self.symbols, self.nominal, self.budget, self.every_min, self.clock = symbols, nominal, budget, every_min, clock
        self.candles = candles or trader.reader.candles
        self.state_path, self.log_path = self.folder / "state.json", self.folder / "decisiones.jsonl"
        self.state: dict[str, Any] = (json.loads(self.state_path.read_text(encoding="utf-8")) if self.state_path.exists()
                                      else {"trades": [], "open": {}, "last": {}, "gasto": {}, "halted": ""})
        self.state.update({"agente": AGENT, "capital_nominal": str(nominal), "version_prompt": PROMPT_VERSION})

    # --- bookkeeping -------------------------------------------------------------------------------------------
    def _save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, indent=1), encoding="utf-8")

    def _log(self, row: dict) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def spent(self, month: str) -> Decimal:
        return Decimal(str(self.state["gasto"].get(month, 0)))

    def _closes(self) -> list[dict]:
        return [t for t in self.state["trades"] if t.get("accion") == "cierre"]

    def total_r(self) -> Decimal:
        return sum((Decimal(t["r"]) for t in self._closes()), Decimal("0"))

    def day_r(self, day: str) -> Decimal:
        return sum((Decimal(t["r"]) for t in self._closes() if t["t"][:10] == day), Decimal("0"))

    def _mid(self, symbol: str) -> Optional[Decimal]:
        try:
            sheet = self.trader.reader.sheet(symbol)
            return (Decimal(str(sheet.bid)) + Decimal(str(sheet.ask))) / 2
        except (XmError, ValueError, ArithmeticError):
            return None

    def _closed(self, symbol: str, now: datetime, how: str, exit_price: Optional[Decimal]) -> Decimal:
        """Records the result in R (estimated: the DEMO account is shared, so its equity does not tell this bot's
        result). A close on XM's server is put at the stop or the target, whichever is nearer the price now."""
        o = self.state["open"].pop(symbol)
        entry, sl, tp, risk = (Decimal(o[k]) for k in ("precio", "sl", "tp", "riesgo"))
        sign = 1 if o["lado"] == "BUY" else -1
        if exit_price is None:
            near = self._mid(symbol) or entry
            exit_price = tp if abs(tp - near) < abs(sl - near) else sl
            how = "meta" if exit_price == tp else "stop"
        r = (sign * (exit_price - entry) / abs(entry - sl)).quantize(Decimal("0.01")) if entry != sl else Decimal("0")
        pnl = (r * risk).quantize(Decimal("0.01"))
        self.state["trades"].append({"t": now.isoformat(), "accion": "cierre", "simbolo": symbol, "motivo": how,
                                     "lado": o["lado"], "salida": str(exit_price), "r": str(r), "pnl": str(pnl),
                                     "estimado": True})
        self.notify(f"{TAG}: {symbol} cerrada por {how}: {r:+}R ({pnl:+} USD aprox.).")
        return r

    def _halt_check(self) -> None:
        if self.state["halted"]:
            return
        total = self.total_r()
        money = sum((Decimal(t["pnl"]) for t in self._closes()), Decimal("0"))
        if total <= HALT_R or money <= -self.nominal * HALT_LOSS_PCT / 100:
            self.state["halted"] = f"tope de pérdida del experimento: {total}R, {money} USD"
            self.alarm(f"🛑 {TAG}: me detengo solo ({self.state['halted']}). Sin entradas nuevas.")

    # --- one pass ----------------------------------------------------------------------------------------------
    def step(self) -> str:
        now = self.clock()
        notes: list[str] = []
        try:
            live = self.trader.positions()
            for symbol in list(self.state["open"]):
                if symbol not in live:
                    self._closed(symbol, now, "servidor", None)
            self._halt_check()
            bucket = pd.Timestamp(now).floor(f"{self.every_min}min").isoformat()
            for symbol in self.symbols:
                if self.state["last"].get(symbol) == bucket:
                    continue
                notes.append(f"{symbol}: {self._decide(symbol, now, bucket, symbol in live)}")
        finally:
            self._save()
        return " · ".join(notes) or "nada que decidir en esta pasada"

    def _decide(self, symbol: str, now: datetime, bucket: str, has_position: bool) -> str:
        month, day = f"{now:%Y-%m}", f"{now:%Y-%m-%d}"
        if not has_position:
            if self.state["halted"]:
                return "experimento detenido"
            if len(self.state["open"]) >= MAX_OPEN:
                return f"ya hay {MAX_OPEN} posiciones abiertas"
            entries = [t for t in self.state["trades"] if t.get("accion") == "entrada" and t["simbolo"] == symbol
                       and t["t"][:10] == day]
            if len(entries) >= MAX_ENTRIES_PER_DAY:
                return f"ya entré {MAX_ENTRIES_PER_DAY} veces hoy"
            if self.day_r(day) <= DAY_LOSS_R:
                return f"el día va {self.day_r(day)}R: sin entradas nuevas hasta mañana"
        try:
            sheet = self.trader.reader.sheet(symbol)
        except (XmError, ValueError) as error:
            return f"sin cotización: {error}"
        if not sheet.market_open:
            return "mercado cerrado"  # no call, no cost
        if self.spent(month) + CALL_RESERVE_USD > self.budget:
            if not self.state.get("tope_avisado") == month:
                self.state["tope_avisado"] = month
                self.alarm(f"💸 {TAG}: llegué al tope de {self.budget} USD de este mes. No pregunto más a Claude hasta "
                           f"el mes que viene; las posiciones abiertas siguen con su stop y meta en XM.")
            return "tope de gasto del mes"
        frames = {tf: self.candles(symbol, tf, n) for tf, n in (("1d", 60), ("4h", 60), ("1h", 72))}
        history = [{"lado": t["lado"], "motivo": t["motivo"], "r": t["r"]} for t in self._closes() if t["simbolo"] == symbol]
        brief = market_brief(symbol, now, float(sheet.bid), float(sheet.ask), float(sheet.spread_pct), frames,
                             self.state["open"].get(symbol), history)
        self.state["last"][symbol] = bucket
        row: dict[str, Any] = {"t": now.isoformat(), "simbolo": symbol, "version_prompt": PROMPT_VERSION,
                               "bid": str(sheet.bid), "ask": str(sheet.ask), "con_posicion": has_position}
        try:
            decision, usage = self.decider.decide(brief)
        except Exception as error:  # noqa: BLE001 - any failure of the call: log it and wait for the next hour
            row.update({"error": str(error)[:300], "accion": WAIT_ON_ERROR})
            self._log(row)
            return f"Claude no respondió ({type(error).__name__}): espero"
        self.state["gasto"][month] = float(self.spent(month) + Decimal(str(usage.cost_usd)))
        price = float(sheet.ask if decision.accion == "COMPRAR" else sheet.bid)
        refused = check_decision(decision, price, has_position)
        row.update({**asdict(decision), **{f"uso_{k}": v for k, v in asdict(usage).items()}, "rechazos": refused})
        result = self._act(symbol, decision, sheet, now) if not refused else "rechazada: " + "; ".join(refused)
        row["resultado"] = result
        self._log(row)
        return result

    def _act(self, symbol: str, d: Decision, sheet: Any, now: datetime) -> str:
        if d.accion in ("ESPERAR", "MANTENER"):
            return d.accion.lower()
        if d.accion == "CERRAR":
            pos = self.trader.positions().get(symbol)
            if pos is None:
                return "ya estaba cerrada"
            self.trader.close(symbol, int(getattr(pos, "ticket")))
            if symbol in self.state["open"]:
                self._closed(symbol, now, "Claude cerró", self._mid(symbol))
            return "cerré por decisión de Claude"
        side = "BUY" if d.accion == "COMPRAR" else "SELL"
        price = float(sheet.ask if side == "BUY" else sheet.bid)
        sl_pct = Decimal(str(abs(price - d.stop) / price * 100)).quantize(Decimal("0.0001"))
        tp_pct = Decimal(str(abs(d.meta - price) / price * 100)).quantize(Decimal("0.0001"))
        try:
            risk_pct, caps = self._sizing()
            plan = self.trader.plan(symbol, side, sl_pct, tp_pct, risk_pct=risk_pct, caps=caps)
            opened = self.trader.open(plan)
        except (XmError, ValueError) as error:
            self.alarm(f"⚠️ {TAG}: {symbol} no entro: {error}")
            return f"no entré: {error}"
        self.state["trades"].append({"t": now.isoformat(), "accion": "entrada", "simbolo": symbol, "lado": side,
                                     "lotes": str(plan.lots), "precio": str(plan.price), "sl": str(plan.sl),
                                     "tp": str(plan.tp), "confianza": d.confianza, "orden": str(opened.get("order"))})
        self.state["open"][symbol] = {"t": now.isoformat(), "lado": side, "precio": str(plan.price), "sl": str(plan.sl),
                                      "tp": str(plan.tp), "riesgo": str(plan.risk_money)}
        msg = (f"{TAG}: {symbol} {'COMPRO' if side == 'BUY' else 'VENDO'} {plan.lots} lotes a {plan.price} · stop "
               f"{plan.sl} · meta {plan.tp} · riesgo {plan.risk_money}. Razón de Claude: {d.razon}")
        self.notify(msg)
        return msg

    def _sizing(self) -> tuple[Decimal, EntryCaps]:
        """XmDemoTrader takes risk and caps of the account's equity: rescaled so the money at risk is RISK_PCT of
        the nominal capital and the size at most MAX_LEVERAGE times it (the DEMO account is shared)."""
        equity = self.trader._demo_account().equity
        if equity <= 0:
            raise XmError("equity cero en la cuenta DEMO")
        scale = self.nominal / equity
        return RISK_PCT * scale, replace(EntryCaps(), max_effective_leverage=MAX_LEVERAGE * scale)

    def summary(self) -> str:
        closes = self._closes()
        wins = sum(1 for t in closes if Decimal(t["r"]) > 0)
        month = f"{self.clock():%Y-%m}"
        halted = f" Detenido: {self.state['halted']}." if self.state["halted"] else ""
        return (f"{TAG}: {len(closes)} operaciones cerradas ({wins} ganadas), {self.total_r():+}R en total, "
                f"{len(self.state['open'])} abiertas. Gasto en Claude este mes: {self.spent(month):.2f} de "
                f"{self.budget} USD.{halted}")


def main(argv: Optional[list[str]] = None, mt5: Optional[object] = None) -> int:
    parser = argparse.ArgumentParser(description="XM DEMO: Claude decide entradas y salidas (experimento, sin dinero real)")
    parser.add_argument("cmd", nargs="?", choices=("revisar", "resumen"), default="revisar")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--simbolos", nargs="+", default=list(SYMBOLS), help="nombres exactos en MT5")
    parser.add_argument("--capital-nominal", type=Decimal, default=NOMINAL)
    parser.add_argument("--tope-usd", type=Decimal, default=BUDGET_USD, help="gasto máximo en la API por mes")
    parser.add_argument("--cada-min", type=int, default=DECIDE_EVERY_MIN, help="minutos entre preguntas por símbolo")
    parser.add_argument("--modelo", default=MODEL)
    parser.add_argument("--terminal", default=None, help="terminal64.exe de otra instalación de MT5")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    trader = XmDemoTrader(args.dir / "orders.json", mt5, magic=agent_magic(AGENT), terminal=args.terminal)
    telegram = make_notify(console, from_env())
    notify = telegram if args.cmd == "resumen" else console  # its trades go in the 22:00 summary
    try:
        trader.connect()
        # the summary asks nothing of Claude: no key needed for it
        decider: Decider = ApiDecider(args.modelo) if args.cmd == "revisar" else _NoDecider()
        bot = ClaudeBot(trader, args.dir, decider, notify, alarm=telegram, symbols=tuple(args.simbolos),
                        nominal=args.capital_nominal, budget=args.tope_usd, every_min=args.cada_min)
        if args.cmd == "resumen":
            notify(bot.summary())
        else:
            print(bot.step())
    except (XmError, ValueError) as error:
        print(f"XM DEMO Claude decide: {error}")
        return 1
    finally:
        try:
            trader.reader.close()
        except Exception:  # noqa: BLE001 - closing a terminal that never opened
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
