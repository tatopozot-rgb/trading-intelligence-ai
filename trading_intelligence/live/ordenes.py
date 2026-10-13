"""
Owner's orders by Telegram on open positions. Owner, 2026-10-13: "debe reconocer cuando le diga pero detén en tal
ganancia o ponerle que detenga ya, ejemplo subió demasiado".

    CIERRA TRX            close the TRXUSDT position now, at market
    META TRX 5            close it when it gains 5% from its entry (checked by the bot every 30 s)
    META TRX PRECIO 0.36  close it when the price reaches 0.36

The market alarm is the only process that reads the owner's Telegram (getUpdates); it writes each order to a shared
file and every running bot applies the orders for the positions it holds, then confirms on Telegram after checking
the account twice. An order older than 15 minutes is ignored (a restart never applies a stale order). Only the
owner's chat reaches this file. Orders only close or set an exit: they never open a position or add risk.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

DEFAULT_ORDERS = Path("live_runs/ordenes.jsonl")
MAX_AGE = timedelta(minutes=15)
_SYMBOL = re.compile(r"^[A-Z0-9]{2,15}$")


@dataclass(frozen=True)
class Order:
    id: str
    at: datetime
    kind: str  # "CIERRA" or "META"
    symbol: str
    value: Optional[Decimal] = None  # META: % gain from the entry, or a price
    is_price: bool = False


def _symbol(word: str) -> Optional[str]:
    word = word.upper()
    if not _SYMBOL.match(word):
        return None
    return word if word.endswith("USDT") or word.endswith("USD") else word + "USDT"


def parse(text: str) -> Optional[tuple[str, str, Optional[Decimal], bool]]:
    """(kind, symbol, value, is_price) for a valid order, None otherwise."""
    words = text.strip().upper().replace(",", ".").replace("%", "").split()
    if len(words) == 2 and words[0] == "CIERRA":
        sym = _symbol(words[1])
        return ("CIERRA", sym, None, False) if sym else None
    if len(words) in (3, 4) and words[0] == "META":
        sym = _symbol(words[1])
        is_price = len(words) == 4 and words[2] == "PRECIO"
        if sym is None or (len(words) == 4 and not is_price):
            return None
        try:
            value = Decimal(words[-1])
        except InvalidOperation:
            return None
        if value <= 0 or (not is_price and value > 1000):
            return None
        return "META", sym, value, is_price
    return None


def enqueue(path: Path, kind: str, symbol: str, value: Optional[Decimal], is_price: bool, now: datetime) -> Order:
    order = Order(uuid.uuid4().hex[:8], now, kind, symbol, value, is_price)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": order.id, "at": now.isoformat(), "kind": kind, "symbol": symbol,
                            "value": None if value is None else str(value), "is_price": is_price}) + "\n")
    return order


def pending(path: Path, cursor: Path, now: datetime) -> list[Order]:
    """Orders written since this bot last looked (its own cursor file), skipping stale ones."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []  # no order written yet: this bot starts at the beginning of the future file
    try:
        seen = int(cursor.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        seen = len(lines)  # a bot that never looked starts from now: old orders are not replayed
    cursor.parent.mkdir(parents=True, exist_ok=True)
    cursor.write_text(str(len(lines)), encoding="ascii")
    out = []
    for line in lines[seen:]:
        try:
            d = json.loads(line)
            at = datetime.fromisoformat(d["at"])
            order = Order(str(d["id"]), at, str(d["kind"]), str(d["symbol"]),
                          None if d.get("value") is None else Decimal(str(d["value"])), bool(d.get("is_price")))
        except (ValueError, KeyError, TypeError, InvalidOperation):
            continue
        if now - at <= MAX_AGE:
            out.append(order)
    return out


def target_price(entry: Decimal, side: str, value: Decimal, is_price: bool) -> Decimal:
    if is_price:
        return value
    return entry * (1 + value / 100) if side == "BUY" else entry * (1 - value / 100)
