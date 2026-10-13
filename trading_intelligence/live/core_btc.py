"""
Core strategy candidate, forward PAPER only: "BTC régimen" (btc_sma50). Leader, 2026-10-13, from the
pre-registered test in docs/research/tendencia/PREREGISTRO.md (Preregistro 2): hold BTC long at 1x only while
the daily close is above its 50-day simple mean, otherwise sit in cash. It was the only rule found that ended
positive in both measured years (2024-25 +53% with a 21% drawdown while BTC made +77% with 28%; 2025-26 +14%
with 18% while BTC lost 24% with 49%), but on few trades, so it is measured live, with fictitious money, before
anything else. Variant `--medias 50,200` (Preregistro 3, PR #49): long only above BOTH means; it failed the bar
(-4.8% in 2021-22) but had the smallest drawdowns, so it runs forward next to it, with no more history re-tests.

    python -m trading_intelligence.live.core_btc            # one pass (Task Scheduler, every hour)
    python -m trading_intelligence.live.core_btc resumen    # where the paper account stands
    python -m trading_intelligence.live.core_btc --medias 50,200 --estado live_runs/core_btc/paper_50_200.json

Rules (frozen as pre-registered): the signal uses CLOSED daily bars only (UTC); a change is acted on at the next
pass after the daily close, at the current price; all the capital, no leverage; fee 0.05% and slippage 0.02% per
side; funding approximated at 0.01% per 8 h while long. Public Binance prices only: no key, no orders.

REAL mode (`--real --capital N`), leader 2026-10-13, for the owner's "mañana conecto las claves ... a darle": the
same signal on Binance SPOT through live/binance_live.py, inside the limits the owner already approved in
config/live_limits.json (spot, no leverage, BTCUSDT allowed, one position at most max_position_pct of the session
capital, the session stops and sells at loss_limit_pct). A STOP_LOSS sell rests on Binance 15% under the entry, so
a crash is cut even with the owner's PC off. Only started by Claude local after the owner's written phrase.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional, Protocol, Sequence

import pandas as pd

from trading_intelligence.live import telegram_notify

logger = logging.getLogger(__name__)

SYMBOL, SMA_DAYS = "BTCUSDT", 50
FEE, SLIPPAGE, FUNDING_PER_DAY = 0.0005, 0.0002, 0.0003
DEFAULT_STATE = Path("live_runs/core_btc/paper.json")
REAL_STATE = Path("live_runs/core_btc/real.json")  # its order journal: real_orders.json next to it
GUARD_STOP = Decimal("0.85")  # real mode: STOP_LOSS resting on Binance 15% under the entry


class Feed(Protocol):
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame: ...


def closed_daily(daily: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """Daily bars whose day has ended (the bar still forming is dropped)."""
    index = pd.DatetimeIndex(daily.index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    return daily[index + timedelta(days=1) <= pd.Timestamp(now)]


def wants_long(closed: pd.DataFrame, means: Sequence[int] = (SMA_DAYS,)) -> Optional[bool]:
    closes = closed["close"].astype(float)
    if len(closes) < max(means):
        return None
    return all(closes.iloc[-1] > closes.tail(n).mean() for n in means)


class CoreBTC:
    def __init__(self, feed: Feed, state_path: Path = DEFAULT_STATE, capital: float = 30.0,
                 notify: Callable[[str], None] = telegram_notify.console,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 means: Sequence[int] = (SMA_DAYS,), trader: Any = None, limits: Any = None) -> None:
        self.feed, self.state_path, self.notify, self.clock = feed, Path(state_path), notify, clock
        self.means = tuple(means)
        self.label = " y ".join(str(n) for n in self.means)
        self.trader, self.limits = trader, limits  # both set = REAL money (SpotTrader + OwnerLimits)
        self.tag = "DINERO REAL" if trader is not None else "práctica, dinero ficticio"
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
        closed = closed_daily(self.feed.get_ohlcv(SYMBOL, "1d", max(self.means) + 10), now)
        if closed.empty:
            return None
        day = str(pd.Timestamp(closed.index[-1]).date())
        price = float(self.feed.get_ohlcv(SYMBOL, "1h", 2)["close"].iloc[-1])
        s = self.state
        if self.trader is not None:  # real money: Binance Spot's own price
            return self._real_step(closed, day, float(self.trader.price(SYMBOL)), now)
        if s["qty"] > 0 and s.get("funding_day") != day:  # one day of funding per closed day held
            s["cash"] = float(s["cash"]) - float(s["qty"]) * price * FUNDING_PER_DAY
            s["funding_day"] = day
        if s.get("day") == day:
            self._save()
            return None
        s["day"] = day
        want = wants_long(closed, self.means)
        msg = None
        if want and s["qty"] == 0:
            fill = price * (1 + SLIPPAGE)
            qty = float(s["cash"]) / (fill * (1 + FEE))
            s["cash"], s["qty"], s["entry"] = 0.0, qty, fill
            s["trades"].append({"time": now.isoformat(), "side": "BUY", "price": fill, "qty": qty})
            msg = (f"🧭 Núcleo BTC ({self.tag}): BTC cerró sobre su media de {self.label} días → COMPRO "
                   f"{qty:.6f} BTC a {fill:,.0f}. Saldo {self.equity(price):.2f} USDT.")
        elif want is False and s["qty"] > 0:
            fill = price * (1 - SLIPPAGE)
            cash = float(s["qty"]) * fill * (1 - FEE)
            pnl = cash - float(s["qty"]) * float(s["entry"])
            s["trades"].append({"time": now.isoformat(), "side": "SELL", "price": fill, "qty": s["qty"], "pnl": pnl})
            s["cash"], s["qty"], s["entry"] = float(s["cash"]) + cash, 0.0, None
            msg = (f"🧭 Núcleo BTC ({self.tag}): BTC cerró bajo su media de {self.label} días → VENDO a "
                   f"{fill:,.0f} y quedo en efectivo ({pnl:+.2f} USDT en la operación). Saldo {self.equity(price):.2f} USDT.")
        self._save()
        if msg:
            self.notify(msg)
        return msg

    # --- REAL money ---------------------------------------------------------------------------------------

    def _fee_price(self, symbol: str) -> Decimal:
        return self.trader.price(symbol)

    def _record_sell(self, fill: Any, now: datetime, why: str) -> str:
        s = self.state
        sold = min(float(fill.executed_qty), float(s["qty"]))
        pnl = float(fill.quote_qty) - sold * float(s["entry"] or 0)
        s["cash"] = float(s["cash"]) + float(fill.quote_qty)
        s["qty"] = max(0.0, float(s["qty"]) - sold)
        s["trades"].append({"time": now.isoformat(), "side": "SELL", "price": float(fill.avg_price), "qty": sold,
                            "pnl": pnl, "why": why})
        if s["qty"] * float(fill.avg_price) < 1:  # what is left is dust, not a position
            s["qty"], s["entry"], s["stop_id"] = 0.0, None, None
        return f"VENDO {sold:.6f} BTC a {float(fill.avg_price):,.0f} ({pnl:+.2f} USDT)"

    def _real_step(self, closed: pd.DataFrame, day: str, price: float, now: datetime) -> Optional[str]:
        from trading_intelligence.live.binance_live import LiveError

        s, t = self.state, self.trader
        msgs: list[str] = []
        try:
            if t.unresolved():
                for fill in t.reconcile(self._fee_price):  # an order whose answer was lost: apply what Binance says
                    if fill.symbol == SYMBOL and fill.side == "BUY" and float(fill.executed_qty) > 0 and s["qty"] == 0:
                        s["cash"] = float(s["cash"]) - float(fill.quote_qty)
                        s["qty"], s["entry"] = float(fill.executed_qty), float(fill.avg_price)
                    elif fill.symbol == SYMBOL and fill.side == "SELL":
                        msgs.append(self._record_sell(fill, now, "reconciliada"))
                if t.unresolved():
                    self._save()
                    return None  # never send a new order while one is unclear
            if s["qty"] > 0 and s.get("stop_id"):
                st = t.stop_status(SYMBOL, s["stop_id"], self._fee_price)
                if st.fill is not None and float(st.fill.executed_qty) > 0:
                    msgs.append("el stop de protección en Binance " + self._record_sell(st.fill, now, "stop"))
                if st.status in ("FILLED", "CANCELED", "EXPIRED", "REJECTED", "NOT_FOUND"):
                    s["stop_id"] = None
            if s.get("halted"):
                return self._finish(msgs)
            capital = Decimal(str(s["start_capital"]))
            loss = float(capital) - self.equity(price)
            if loss >= float(self.limits.loss_limit_usd(capital)):
                s["halted"] = True
                msgs.append(f"⛔ llegó al límite de pérdida aprobado ({self.limits.loss_limit_pct}%): vendo y me detengo")
                if s["qty"] > 0:
                    msgs.append(self._real_sell(now, "límite de pérdida"))
                return self._finish(msgs)
            if loss >= float(self.limits.warn_at_usd(capital)) and not s.get("warned"):
                s["warned"] = True
                msgs.append(f"⚠️ pérdida {loss:.2f} USDT: a {self.limits.warn_before_usd} USD del límite aprobado")
            if s["qty"] > 0 and not s.get("stop_id"):
                self._place_guard(msgs)
            if s.get("day") == day:
                return self._finish(msgs)
            s["day"] = day
            want = wants_long(closed, self.means)
            if want and s["qty"] == 0:
                msgs.append(self._real_buy(price, now))
            elif want is False and s["qty"] > 0:
                msgs.append(f"BTC cerró bajo su media de {self.label} días → " + self._real_sell(now, "señal"))
        except LiveError as error:  # Binance refused or the answer is unclear: reported, never resent
            logger.warning("core BTC real: %s", error)
            msgs.append(f"⚠️ Binance: {error}. No reenvío nada; reviso en la próxima pasada.")
        return self._finish(msgs)

    def _finish(self, msgs: list[str]) -> Optional[str]:
        self._save()
        msgs = [m for m in msgs if m]
        if not msgs:
            return None
        msg = f"🧭 Núcleo BTC {self.label} ({self.tag}): " + " | ".join(msgs)
        self.notify(msg)
        return msg

    def _real_buy(self, price: float, now: datetime) -> str:
        s, t = self.state, self.trader
        rules = t.rules(SYMBOL)
        capital = Decimal(str(s["start_capital"]))
        budget = min(Decimal(str(s["cash"])), capital * self.limits.max_position_pct / 100, t.free_balance("USDT"))
        qty = rules.floor_qty(budget / (Decimal(str(price)) * Decimal("1.003")))  # room for fee and a moving price
        if qty <= 0 or qty < rules.min_qty or qty * Decimal(str(price)) < rules.min_notional:
            return f"BTC cerró sobre su media, pero {budget:.2f} USDT no alcanza el mínimo de Binance: no compro"
        fill = t.market_order(SYMBOL, "BUY", qty, self._fee_price)
        if float(fill.executed_qty) <= 0:
            return "Binance no ejecutó la compra"
        s["cash"] = float(s["cash"]) - float(fill.quote_qty)
        s["qty"], s["entry"] = float(fill.executed_qty), float(fill.avg_price)
        s["trades"].append({"time": now.isoformat(), "side": "BUY", "price": s["entry"], "qty": s["qty"]})
        msgs = [f"BTC cerró sobre su media de {self.label} días → COMPRO {s['qty']:.6f} BTC a {s['entry']:,.0f} "
                f"({float(fill.quote_qty):.2f} USDT)"]
        self._place_guard(msgs)
        return " | ".join(msgs)

    def _place_guard(self, msgs: list[str]) -> None:
        from trading_intelligence.live.binance_live import LiveError

        s, t = self.state, self.trader
        rules = t.rules(SYMBOL)
        if not rules.stop_loss:
            return
        qty = rules.floor_qty(min(Decimal(str(s["qty"])), t.free_balance("BTC")))
        stop = rules.floor_price(Decimal(str(s["entry"])) * GUARD_STOP)
        if qty <= 0 or qty * stop < rules.min_notional:
            return
        try:
            s["stop_id"] = t.place_stop(SYMBOL, qty, stop)
            msgs.append(f"stop de protección en Binance a {float(stop):,.0f}")
        except LiveError as error:
            msgs.append(f"⚠️ no pude poner el stop de protección ({error})")

    def _real_sell(self, now: datetime, why: str) -> str:
        s, t = self.state, self.trader
        if s.get("stop_id"):  # the resting stop holds the BTC: cancel it first (it may already have sold)
            st = t.cancel_stop(SYMBOL, s["stop_id"], self._fee_price)
            s["stop_id"] = None
            if st.fill is not None and float(st.fill.executed_qty) > 0:
                done = "el stop de protección " + self._record_sell(st.fill, now, "stop")
                if s["qty"] == 0:
                    return done
        rules = t.rules(SYMBOL)
        qty = rules.floor_qty(min(Decimal(str(s["qty"])), t.free_balance("BTC")))
        if qty <= 0 or qty < rules.min_qty or qty * t.price(SYMBOL) < rules.min_notional:
            s["qty"], s["entry"] = 0.0, None
            return "lo que queda es menor al mínimo de Binance: queda como polvo"
        return self._record_sell(t.market_order(SYMBOL, "SELL", qty, self._fee_price), now, why)

    def summary(self) -> str:
        price = float(self.feed.get_ohlcv(SYMBOL, "1h", 2)["close"].iloc[-1])
        s = self.state
        eq = self.equity(price)
        pos = f"comprado {s['qty']:.6f} BTC desde {s['entry']:,.0f}" if s["qty"] > 0 else "en efectivo"
        return (f"🧭 Núcleo BTC {self.label} ({self.tag}): {pos}. Saldo {eq:.2f} USDT ({(eq / s['start_capital'] - 1) * 100:+.1f}% desde "
                f"{s['start_capital']}), {len(s['trades'])} operaciones.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Núcleo BTC (BTC sobre su media de 50 días): práctica, sin dinero real")
    parser.add_argument("cmd", nargs="?", choices=("revisar", "resumen"), default="revisar")
    parser.add_argument("--capital", type=float, default=None, help="USDT de esta sesión (obligatorio con --real)")
    parser.add_argument("--estado", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--medias", default=str(SMA_DAYS), help="e.g. 50 or 50,200 (long only above all of them)")
    parser.add_argument("--real", action="store_true", help="DINERO REAL en Binance Spot (solo con la frase del dueño)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from trading_intelligence.data.binance_public_feed import BinancePublicKlines

    notify = telegram_notify.make_notify(telegram_notify.console, telegram_notify.from_env())
    means = tuple(int(n) for n in args.medias.split(","))
    trader = limits = None
    state = args.estado
    if args.real and args.capital is None:
        raise SystemExit("con --real hay que decir el capital: --capital N")
    capital = 30.0 if args.capital is None else args.capital
    if args.real:
        from trading_intelligence.live.binance_live import Credentials, SpotTrader
        from trading_intelligence.live.limits import load_limits

        limits = load_limits()  # refuses unless the owner approved spot, 1x, no withdrawals
        if SYMBOL not in limits.allowed_symbols:
            raise SystemExit("BTCUSDT no está en los símbolos aprobados por el dueño")
        if state == DEFAULT_STATE:
            state = REAL_STATE if means == (SMA_DAYS,) else REAL_STATE.with_name(f"real_{'_'.join(map(str, means))}.json")
        trader = SpotTrader(Credentials.from_env(), state.with_name(state.stem + "_orders.json"))
        if not trader.verify_key():
            raise SystemExit("la clave de Binance debe tener restricción de IP: no opero")
    core = CoreBTC(BinancePublicKlines(), state, capital, notify, means=means, trader=trader, limits=limits)
    if args.cmd == "resumen":
        notify(core.summary())
        return 0
    core.step()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
