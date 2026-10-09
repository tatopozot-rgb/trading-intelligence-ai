"""
Messages for the owner (console and Telegram) in plain Spanish. Owner, 2026-10-09: "mensajes
más amigables y fáciles de entender para alguien que no es programador": complete sentences
instead of codes, the result in money, and what he has to do, if anything.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Mapping, Optional

NOTHING_TO_DO = "No tienes que hacer nada."


def coin(symbol: str) -> str:
    return symbol[:-4] if symbol.endswith("USDT") else symbol


def num(value: Decimal, decimals: int = 2) -> str:
    """Spanish style: 61.230,50."""
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def usdt(value: Decimal) -> str:
    return f"{num(value)} USDT"


def price(value: Decimal) -> str:
    return num(value, 2 if value >= 10 else 4)


def _result(pnl: Decimal) -> str:
    if pnl > 0:
        return f"ganaste {usdt(pnl)} ✅"
    if pnl < 0:
        return f"perdiste {usdt(-pnl)}"
    return "quedaste igual"


def reason(code: str) -> str:
    """Why the operator acted, from its internal reason code."""
    head = code.split(":")[0]
    tail = code.split(":")[-1] if ":" in code else ""
    if head == "STOP_HIT":
        return "el precio tocó el stop loss (la protección contra pérdidas)"
    if head in ("EXCHANGE_STOP", "EXCHANGE_STOP_ALREADY_EXECUTED"):
        return "se activó el stop de protección que estaba puesto en Binance"
    if head == "LOSS_LIMIT":
        return "se alcanzó tu límite de pérdida de la sesión"
    if head == "TIEMPO_CUMPLIDO":
        return "terminó el tiempo que pediste para la sesión"
    if head == "META_ALCANZADA":
        return "se alcanzó tu meta de ganancia"
    if head == "OWNER_STOP":
        return "lo pediste tú"
    if head == "copiar":
        return "el trader que copias cambió su posición"
    if head in ("tendencia", "tendencia_rango", "momentum"):
        if tail == "CLOSE":
            return "la estrategia dio señal de salida"
        if tail == "REDUCE":
            return "la estrategia redujo el tamaño de la posición"
        return "la estrategia vio una señal de compra"
    return code


def buy(symbol: str, spent: Decimal, at: Optional[Decimal], why: str, real: bool) -> str:
    where = "" if real else " (simulado, sin dinero real)"
    at_text = f" a {price(at)}" if at else ""
    return (f"🟢 Compré {coin(symbol)} por {usdt(spent)}{at_text}{where}. Motivo: {reason(why)}. "
            f"El stop de protección queda vigilado cada minuto. {NOTHING_TO_DO}")


def sell(symbol: str, received: Decimal, pnl: Optional[Decimal], why: str, real: bool) -> str:
    where = "" if real else " (simulado, sin dinero real)"
    result = f" En esta operación {_result(pnl)}." if pnl is not None else ""
    return f"🔴 Vendí {coin(symbol)} y recibí {usdt(received)}{where}.{result} Motivo: {reason(why)}. {NOTHING_TO_DO}"


def guard(symbol: str, stop: Decimal) -> str:
    return (f"🛡️ Dejé un stop de protección en Binance para {coin(symbol)} en {price(stop)}: si el precio cae "
            f"ahí, se vende solo, aunque tu PC esté apagado. {NOTHING_TO_DO}")


def summary(capital: Decimal, equity: Decimal, loss_limit: Decimal,
            positions: Mapping[str, Optional[Decimal]], real: bool) -> str:
    """positions: symbol -> % change since entry (None when unknown)."""
    change = equity - capital
    trend = (f"vas ganando {usdt(change)}" if change > 0 else
             f"vas perdiendo {usdt(-change)}" if change < 0 else "vas igual")
    if positions:
        held = ", ".join(f"{coin(s)} ({'+' if (p or 0) >= 0 else ''}{num(p or Decimal('0'), 1)}%)"
                         for s, p in sorted(positions.items()))
        held = f"Tienes abiertas: {held}."
    else:
        held = "No tienes posiciones abiertas: todo está en USDT, esperando una buena señal."
    where = "" if real else " (simulada)"
    return (f"📊 Resumen de tu sesión{where}: empezaste con {usdt(capital)} y ahora tienes {usdt(equity)} "
            f"({trend}). {held} Tu límite de pérdida es {usdt(loss_limit)}. {NOTHING_TO_DO}")


def started(capital: Decimal, loss_limit: Decimal, symbols: list[str], real: bool) -> str:
    where = "con dinero real" if real else "en simulación (sin dinero real)"
    return (f"▶️ Empecé a operar {where} con {usdt(capital)}. Vigilo {len(symbols)} monedas "
            f"({', '.join(coin(s) for s in symbols[:6])}{'…' if len(symbols) > 6 else ''}) y solo compro cuando la "
            f"estrategia ve una buena señal. Tu límite de pérdida es {usdt(loss_limit)}. Te aviso por aquí de "
            f"cada compra y venta. {NOTHING_TO_DO}")


def warning(loss: Decimal, limit: Decimal) -> str:
    return (f"⚠️ Vas perdiendo {usdt(loss)} y tu límite es {usdt(limit)}. Pausé las compras nuevas; las "
            "posiciones abiertas siguen protegidas por sus stops. Si quieres seguir, dile a Claude local: "
            "\"continúa\". Si no, no hagas nada.")


def stopped(loss: Decimal, limit: Decimal) -> str:
    return (f"🛑 Se alcanzó tu límite de pérdida ({usdt(limit)}; la pérdida es {usdt(loss)}). Vendí lo de la "
            "sesión y paré el trading, como acordamos. Para volver a operar hay que empezar una sesión nueva.")


def finished(why: str, capital: Decimal, equity: Decimal) -> str:
    change = equity - capital
    result = ("ganaste " + usdt(change) + " ✅" if change > 0 else
              "perdiste " + usdt(-change) if change < 0 else "quedaste igual")
    return f"🏁 Sesión terminada: {reason(why)}. Empezaste con {usdt(capital)} y terminaste con {usdt(equity)}: {result}."


def error(detail: str) -> str:
    return (f"⚠️ Hubo un problema al hablar con Binance ({detail}). El sistema lo reintenta solo en la "
            "próxima vuelta y no repite órdenes dudosas. Si este aviso se repite, díselo a Claude local.")
