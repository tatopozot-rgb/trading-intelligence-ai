"""
Core strategy candidate, forward PAPER only: "BTC régimen" (btc_sma50). Leader, 2026-10-13, from the
pre-registered test in docs/research/tendencia/PREREGISTRO.md (Preregistro 2): hold BTC long at 1x only while
the daily close is above its 50-day simple mean, otherwise sit in cash. It was the only rule found that ended
positive in both measured years (2024-25 +53% with a 21% drawdown while BTC made +77% with 28%; 2025-26 +14%
with 18% while BTC lost 24% with 49%), but on few trades, so it is measured live, with fictitious money, before
anything else.

    python -m trading_intelligence.live.core_btc            # one pass (Task Scheduler, every hour)
    python -m trading_intelligence.live.core_btc resumen    # where the paper account stands

Rules (frozen as pre-registered): the signal uses CLOSED daily bars only (UTC); a change is acted on at the next
pass after the daily close, at the current price; all the capital, no leverage; fee 0.05% and slippage 0.02% per
side; funding approximated at 0.01% per 8 h while long. Public Binance prices only: no key, no orders.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional, Protocol, Sequence

import pandas as pd

from trading_intelligence.live import telegram_notify

logger = logging.getLogger(__name__)

SYMBOL, SMA_DAYS = "BTCUSDT", 50
FEE, SLIPPAGE, FUNDING_PER_DAY = 0.0005, 0.0002, 0.0003
DEFAULT_STATE = Path("live_runs/core_btc/paper.json")


class Feed(Protocol):
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame: ...


def closed_daily(daily: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """Daily bars whose day has ended (the bar still forming is dropped)."""
    index = pd.DatetimeIndex(daily.index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    return daily[index + timedelta(days=1) <= pd.Timestamp(now)]


def wants_long(closed: pd.DataFrame) -> Optional[bool]:
    closes = closed["close"].astype(float)
    if len(closes) < SMA_DAYS:
        return None
    return bool(closes.iloc[-1] > closes.tail(SMA_DAYS).mean())


class CoreBTC:
    def __init__(self, feed: Feed, state_path: Path = DEFAULT_STATE, capital: float = 30.0,
                 notify: Callable[[str], None] = telegram_notify.console,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self.feed, self.state_path, self.notify, self.clock = feed, Path(state_path), notify, clock
        self.state = self._load(capital)

    def _load(self, capital: float) -> dict:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
        return {"start_capital": capital, "cash": capital, "qty": 0.0, "entry": None, "day": None,
                "funding_day": None, "trades": []}

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=1), encoding="utf-8")
        tmp.replace(self.state_path)

    def equity(self, price: float) -> float:
        return float(self.state["cash"]) + float(self.state["qty"]) * price

    def step(self) -> Optional[str]:
        now = self.clock()
        closed = closed_daily(self.feed.get_ohlcv(SYMBOL, "1d", SMA_DAYS + 10), now)
        if closed.empty:
            return None
        day = str(pd.Timestamp(closed.index[-1]).date())
        price = float(self.feed.get_ohlcv(SYMBOL, "1h", 2)["close"].iloc[-1])
        s = self.state
        if s["qty"] > 0 and s.get("funding_day") != day:  # one day of funding per closed day held
            s["cash"] = float(s["cash"]) - float(s["qty"]) * price * FUNDING_PER_DAY
            s["funding_day"] = day
        if s.get("day") == day:
            self._save()
            return None
        s["day"] = day
        want = wants_long(closed)
        msg = None
        if want and s["qty"] == 0:
            fill = price * (1 + SLIPPAGE)
            qty = float(s["cash"]) / (fill * (1 + FEE))
            s["cash"], s["qty"], s["entry"] = 0.0, qty, fill
            s["trades"].append({"time": now.isoformat(), "side": "BUY", "price": fill, "qty": qty})
            msg = (f"🧭 Núcleo BTC (práctica, dinero ficticio): BTC cerró sobre su media de {SMA_DAYS} días → COMPRO "
                   f"{qty:.6f} BTC a {fill:,.0f}. Saldo {self.equity(price):.2f} USDT.")
        elif want is False and s["qty"] > 0:
            fill = price * (1 - SLIPPAGE)
            cash = float(s["qty"]) * fill * (1 - FEE)
            pnl = cash - float(s["qty"]) * float(s["entry"])
            s["trades"].append({"time": now.isoformat(), "side": "SELL", "price": fill, "qty": s["qty"], "pnl": pnl})
            s["cash"], s["qty"], s["entry"] = float(s["cash"]) + cash, 0.0, None
            msg = (f"🧭 Núcleo BTC (práctica, dinero ficticio): BTC cerró bajo su media de {SMA_DAYS} días → VENDO a "
                   f"{fill:,.0f} y quedo en efectivo ({pnl:+.2f} USDT en la operación). Saldo {self.equity(price):.2f} USDT.")
        self._save()
        if msg:
            self.notify(msg)
        return msg

    def summary(self) -> str:
        price = float(self.feed.get_ohlcv(SYMBOL, "1h", 2)["close"].iloc[-1])
        s = self.state
        eq = self.equity(price)
        pos = f"comprado {s['qty']:.6f} BTC desde {s['entry']:,.0f}" if s["qty"] > 0 else "en efectivo"
        return (f"🧭 Núcleo BTC (práctica): {pos}. Saldo {eq:.2f} USDT ({(eq / s['start_capital'] - 1) * 100:+.1f}% desde "
                f"{s['start_capital']}), {len(s['trades'])} operaciones.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Núcleo BTC (BTC sobre su media de 50 días): práctica, sin dinero real")
    parser.add_argument("cmd", nargs="?", choices=("revisar", "resumen"), default="revisar")
    parser.add_argument("--capital", type=float, default=30.0)
    parser.add_argument("--estado", type=Path, default=DEFAULT_STATE)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from trading_intelligence.data.binance_public_feed import BinancePublicKlines

    notify = telegram_notify.make_notify(telegram_notify.console, telegram_notify.from_env())
    core = CoreBTC(BinancePublicKlines(), args.estado, args.capital, notify)
    if args.cmd == "resumen":
        notify(core.summary())
        return 0
    core.step()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
