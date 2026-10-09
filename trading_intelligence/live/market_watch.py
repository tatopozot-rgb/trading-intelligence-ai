"""
Market watcher: tells the owner by Telegram (and on the console) when a watched coin moves
hard or changes regime. It only WATCHES: it never sends an order, needs no key and reads
only Binance's public klines.

    python -m trading_intelligence.live.market_watch            # one pass (Task Scheduler, every 15 min)
    python -m trading_intelligence.live.market_watch --continuo # same, in a loop every 5 min
    python -m trading_intelligence.live.market_watch resumen    # table of every coin now

Alerts:
- a move of at least 2.5% in ~1h, 4% in ~4h or 7% in ~24h, up or down. The same move is not
  repeated for 4 hours unless it doubles (or triples...) the threshold;
- a regime change on the last CLOSED 4h bar into TREND_UP, TREND_DOWN, BREAKOUT_UP or
  BREAKOUT_DOWN (the detector the engine uses). The first pass only records the regimes.

Watched: the owner's approved symbols plus PAXGUSDT (gold, watch only: it is not tradable
here unless the owner adds it to config/live_limits.json).
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional, Protocol, Sequence

import pandas as pd

from trading_intelligence.live import telegram_notify
from trading_intelligence.regime.detector import Regime, detect_regime

logger = logging.getLogger(__name__)

WATCH_ONLY = ("PAXGUSDT",)
DEFAULT_STATE = Path("live_runs/market_watch.json")
COOLDOWN = timedelta(hours=4)
LOOP_SECONDS = 300
FOUR_HOURS = timedelta(hours=4)
# (label, 15-minute bars back, threshold %)
WINDOWS = (("1h", 4, 2.5), ("4h", 16, 4.0), ("24h", 96, 7.0))
ALERT_REGIMES = {Regime.TREND_UP, Regime.TREND_DOWN, Regime.BREAKOUT_UP, Regime.BREAKOUT_DOWN}
REGIME_WORDS = {
    "TREND_UP": "tendencia alcista", "TREND_DOWN": "tendencia bajista", "RANGE": "rango (lateral)",
    "BREAKOUT_UP": "ruptura al alza", "BREAKOUT_DOWN": "ruptura a la baja", "NO_EDGE": "sin dirección clara",
}


class Feed(Protocol):
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame: ...


@dataclass(frozen=True)
class Move:
    symbol: str
    window: str
    pct: float
    price: float
    threshold: float

    @property
    def level(self) -> int:
        return int(abs(self.pct) // self.threshold)

    @property
    def direction(self) -> str:
        return "up" if self.pct > 0 else "down"


def moves(symbol: str, bars_15m: pd.DataFrame) -> list[Move]:
    """Changes from ~1h, ~4h and ~24h ago to the latest price (the open 15m bar's close)."""
    closes = bars_15m["close"].tolist()
    out = []
    for label, back, threshold in WINDOWS:
        if len(closes) > back and closes[-1 - back] > 0:
            pct = (closes[-1] / closes[-1 - back] - 1) * 100
            out.append(Move(symbol, label, pct, closes[-1], threshold))
    return out


def closed_regime(bars_4h: pd.DataFrame, now: datetime) -> tuple[Optional[str], Optional[str]]:
    """(regime, bar open time) of the last CLOSED 4h bar; the bar still forming is dropped."""
    index = pd.DatetimeIndex(bars_4h.index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    closed = bars_4h[index + FOUR_HOURS <= pd.Timestamp(now)]
    if closed.empty:
        return None, None
    return detect_regime(closed).regime.value, closed.index[-1].isoformat()


def _fmt_price(price: float) -> str:
    return f"{price:,.4f}" if price < 10 else f"{price:,.2f}"


class MarketWatch:
    def __init__(self, feed: Feed, symbols: Sequence[str], state_path: Path,
                 notify: Callable[[str], None] = print,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self.feed, self.symbols, self.state_path = feed, list(symbols), Path(state_path)
        self.notify, self.clock = notify, clock
        self.state = self._load()

    def _load(self) -> dict:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {"alerts": dict(data.get("alerts", {})), "regimes": dict(data.get("regimes", {}))}
        except (OSError, ValueError):
            pass
        return {"alerts": {}, "regimes": {}}

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.state_path)

    def _should_alert(self, move: Move, now: datetime) -> bool:
        if move.level < 1:
            return False
        key = f"{move.symbol}:{move.window}:{move.direction}"
        last = self.state["alerts"].get(key)
        if last is not None:
            at = datetime.fromisoformat(last["at"])
            if now - at < COOLDOWN and move.level <= int(last["level"]):
                return False  # same move, already told
        self.state["alerts"][key] = {"at": now.isoformat(), "level": move.level}
        return True

    def check(self) -> list[str]:
        """One pass over every symbol. Returns the alerts sent."""
        now = self.clock()
        sent: list[str] = []
        failures = 0
        for sym in self.symbols:
            try:
                bars_15m = self.feed.get_ohlcv(sym, "15m", limit=100)
                bars_4h = self.feed.get_ohlcv(sym, "4h", limit=200)
            except Exception as error:  # noqa: BLE001 - one coin's data must not stop the others
                failures += 1
                logger.warning("%s: no data (%s)", sym, type(error).__name__)
                continue
            regime, bar = closed_regime(bars_4h, now)
            regime_txt = REGIME_WORDS.get(regime or "", "sin datos")
            for move in moves(sym, bars_15m):
                if self._should_alert(move, now):
                    arrow = "📈" if move.direction == "up" else "📉"
                    strong = " FUERTE" if move.level >= 2 else ""
                    sent.append(f"{arrow}{strong} {sym} {move.pct:+.1f}% en {move.window} "
                                f"(precio {_fmt_price(move.price)}). Régimen 4h: {regime_txt}.")
            previous = self.state["regimes"].get(sym)
            if regime is not None and (previous is None or previous["bar"] != bar):  # once per closed bar
                if previous is not None and previous["regime"] != regime and Regime(regime) in ALERT_REGIMES:
                    sent.append(f"🔄 {sym} cambió a {regime_txt} en la vela de 4h "
                                f"(antes: {REGIME_WORDS.get(previous['regime'], previous['regime'])}).")
                self.state["regimes"][sym] = {"regime": regime, "bar": bar}
        if failures == len(self.symbols) and self.symbols:
            sent.append("⚠️ Vigilante: Binance no respondió para ninguna moneda en esta vuelta.")
        for message in sent:
            self.notify(f"[Vigilante] {message}")
        self._save()
        return sent

    def summary(self) -> str:
        now = self.clock()
        lines = [f"[Vigilante] Mercado {now:%Y-%m-%d %H:%M} UTC (1h / 4h / 24h, régimen 4h):"]
        for sym in self.symbols:
            try:
                ch = {m.window: m.pct for m in moves(sym, self.feed.get_ohlcv(sym, "15m", limit=100))}
                regime, _ = closed_regime(self.feed.get_ohlcv(sym, "4h", limit=200), now)
            except Exception as error:  # noqa: BLE001
                lines.append(f"{sym}: sin datos ({type(error).__name__})")
                continue
            cols = " / ".join(f"{ch[w]:+.1f}%" if w in ch else "—" for w, _, _ in WINDOWS)
            lines.append(f"{sym}: {cols} · {REGIME_WORDS.get(regime or '', 'sin datos')}")
        return "\n".join(lines)


def watched_symbols() -> list[str]:
    from trading_intelligence.live.limits import load_limits

    return sorted(set(load_limits().allowed_symbols) | set(WATCH_ONLY))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Market watcher: Telegram alerts on strong moves (never trades).")
    parser.add_argument("cmd", nargs="?", choices=("revisar", "resumen"), default="revisar")
    parser.add_argument("--continuo", action="store_true", help=f"repeat every {LOOP_SECONDS // 60} minutes")
    parser.add_argument("--estado", type=Path, default=DEFAULT_STATE)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from trading_intelligence.data.binance_public_feed import BinancePublicKlines

    notify = telegram_notify.make_notify(telegram_notify.console, telegram_notify.from_env())
    watch = MarketWatch(BinancePublicKlines(), watched_symbols(), args.estado, notify)
    if args.cmd == "resumen":
        notify(watch.summary())
        return 0
    while True:
        sent = watch.check()
        if not sent:
            print(f"{datetime.now(timezone.utc):%H:%M} UTC sin movimientos fuertes")
        if not args.continuo:
            return 0
        time.sleep(LOOP_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
