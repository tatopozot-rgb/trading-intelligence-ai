"""
Binance USDⓈ-M Futures, both directions, on the shared two-way engine (live/two_way.py). Owner,
2026-10-10: "Ya active cuenta de futuros en binance ... opera como lo ordenado y como si fuese en
xm ... el sistema es el mismo, los 2 mercados son futuros ... no vuelvas a comprar criptos".

Two modes:
- SHADOW (default): Binance's public prices only, no key. Positions are simulated with their stop,
  target and the taker fee, so the engine is measured before money is at stake.
- REAL: only with config/futures_limits.json approved by the owner, a futures key verified, and
  the owner's phrase written to Claude local.

Safety rules, each enforced in code (same design as the Spot transport):
- Hosts fixed to fapi.binance.com (+ api.binance.com for the key check); no redirects.
- The key must have reading and Futures, IP restriction, withdrawals OFF; transfers, margin,
  options, portfolio margin or any unknown permission -> refused. Spot trading is tolerated.
- One-way position mode, ISOLATED margin, leverage set per symbol from the owner's limit.
- Every entry gets a STOP_MARKET and a TAKE_PROFIT_MARKET (closePosition, mark price) on Binance's
  Algo Order service (conditional orders moved there on 2025-12-09; /fapi/v1/order refuses them
  with -4120). If the stop cannot be placed, the position is closed at once: never left bare.
- Every market order is journaled BEFORE it is sent; an unclear answer is looked up by client id,
  never resent, and no new entry is made while one stays unresolved.
- Size from risk, as on Spot: qty = equity x 1% / stop distance, capped so one position's notional
  is at most leverage x 40% of equity; rounded DOWN; below Binance's minimum -> no trade.
- Never a withdrawal or a transfer: the owner moves USDT between his wallets himself.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

import pandas as pd

from trading_intelligence.live.binance_live import HttpResponse, Journal, LiveError, Restricted, Unreconciled
from trading_intelligence.live.telegram_notify import console, from_env, make_notify
from trading_intelligence.live.two_way import DEFAULT_WINDOWS, Plan, Position, TwoWayAuto, owner_continue
from trading_intelligence.strategy.two_way_signals import DEFAULT_VARIANT, VARIANTS, signal_for

logger = logging.getLogger(__name__)

FAPI_HOST, SPOT_HOST = "fapi.binance.com", "api.binance.com"
KEY_VAR, SECRET_VAR = "BINANCE_FUTURES_API_KEY", "BINANCE_FUTURES_SECRET_KEY"
# Owner, 2026-10-10: "usa la misma clave de ser necesario es la misma cuenta": without a futures-only key,
# the Spot key already on the PC is used (it then needs "Enable Futures" ticked in Binance).
SPOT_KEY_VAR, SPOT_SECRET_VAR = "BINANCE_TRADE_API_KEY", "BINANCE_TRADE_SECRET_KEY"
ALLOWED_TRUE_PERMISSIONS = frozenset({"enableReading", "enableFutures", "enableFixReadOnly",
                                      "enableSpotAndMarginTrading"})
RECV_WINDOW_MS, TIME_RESYNC_SECONDS, TIMEOUT = 5000, 600, 15.0
TIMESTAMP_REJECTED, NO_MARGIN_CHANGE, ORDER_NOT_FOUND = -1021, -4046, -2013
TAKER_FEE = Decimal("0.0005")  # 0.05% per side, Binance's base taker rate for USDⓈ-M
CRYPTO_MIN_STOP_PCT, CRYPTO_MAX_STOP_PCT = Decimal("3"), Decimal("15")  # owner, 2026-10-10: "desde 3 al 15"
INTERVALS = frozenset({"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "1d"})
DEFAULT_LIMITS = Path("config/futures_limits.json")
CLIENT_PREFIX = "TIF-"


class FuturesError(LiveError):
    pass


class UnsafeFuturesKey(FuturesError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def urllib_transport(method: str, url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.netloc not in (FAPI_HOST, SPOT_HOST):
        raise FuturesError("only https://fapi.binance.com and https://api.binance.com are allowed")
    opener = urllib.request.build_opener(_NoRedirect())
    req = urllib.request.Request(url, headers=dict(headers), method=method,
                                 data=b"" if method in ("POST", "DELETE") else None)
    try:
        with opener.open(req, timeout=timeout) as resp:
            return HttpResponse(resp.status, dict(resp.headers.items()), resp.read(5_000_001))
    except urllib.error.HTTPError as error:
        with error:
            return HttpResponse(error.code, dict(error.headers.items()), error.read(5_000_001))


class FuturesCredentials:
    __slots__ = ("_key", "_secret")

    def __init__(self, key: str, secret: str) -> None:
        for value in (key, secret):
            if type(value) is not str or not value.isalnum() or not 16 <= len(value) <= 256:
                raise FuturesError("credential with unexpected format")
        self._key, self._secret = key, secret

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "FuturesCredentials":
        env = os.environ if env is None else env
        key, secret = env.get(KEY_VAR), env.get(SECRET_VAR)
        if not key or not secret:
            key, secret = env.get(SPOT_KEY_VAR), env.get(SPOT_SECRET_VAR)
        if not key or not secret:
            raise FuturesError(f"no hay clave de Binance en este PC ({KEY_VAR} o {SPOT_KEY_VAR}): el dueño la "
                               "guarda él mismo")
        return cls(key, secret)

    def header(self) -> dict[str, str]:
        return {"X-MBX-APIKEY": self._key}

    def sign(self, query: str) -> str:
        return hmac.new(self._secret.encode(), query.encode(), hashlib.sha256).hexdigest()

    def __repr__(self) -> str:
        return "FuturesCredentials(<redacted>)"

    __str__ = __repr__

    def __reduce__(self):
        raise TypeError("credentials are not serializable")


def check_futures_key(data: object) -> None:
    if not isinstance(data, dict):
        raise UnsafeFuturesKey("no pude leer los permisos de la clave")
    if data.get("enableWithdrawals") is not False:
        raise UnsafeFuturesKey("la clave tiene RETIROS activados (o desconocidos): desactívalos en Binance")
    if data.get("enableReading") is not True or data.get("enableFutures") is not True:
        raise UnsafeFuturesKey("la clave necesita lectura y Futuros activados: en Binance, Gestión de API → "
                               "Editar restricciones → marcar 'Habilitar Futuros'")
    if data.get("ipRestrict") is not True:
        raise UnsafeFuturesKey("la clave debe estar restringida a la IP de este PC")
    for name, value in data.items():
        if isinstance(name, str) and name.startswith(("enable", "permits")):
            if not isinstance(value, bool):
                raise UnsafeFuturesKey("la clave tiene un permiso que no se pudo determinar")
            if value and name not in ALLOWED_TRUE_PERMISSIONS:
                label = name if name.isalpha() and len(name) <= 60 else "desconocido"
                raise UnsafeFuturesKey(f"la clave tiene un permiso no permitido: {label}")


@dataclass(frozen=True)
class FuturesRules:
    step: Decimal
    min_qty: Decimal
    min_notional: Decimal
    tick: Decimal

    def floor_qty(self, qty: Decimal) -> Decimal:
        return (qty / self.step).to_integral_value(rounding=ROUND_DOWN) * self.step if self.step > 0 else qty

    def round_price(self, price: Decimal, up: bool) -> Decimal:
        if self.tick <= 0:
            return price
        return (price / self.tick).to_integral_value(rounding=ROUND_UP if up else ROUND_DOWN) * self.tick


@dataclass(frozen=True)
class FuturesLimits:
    """The Spot program's percentages, for futures (owner, 2026-10-10: "usar los mismos porcentajes")."""
    approved: bool
    max_leverage: int
    risk_pct: Decimal  # of equity lost if the stop is hit (the Spot engine's 1%)
    max_position_pct: Decimal  # notional of one position / equity (Spot: 40)
    max_open: int
    loss_limit_pct: Decimal  # session loss limit (Spot session: 45, inside the owner's 20-50 band)
    loss_range: tuple[Decimal, Decimal]
    warn_before_usd: Decimal  # the owner is asked this many USD before the limit (Spot: 2)
    profit_target_pct: Optional[Decimal]  # session goal (Spot session: 58)
    symbols: tuple[str, ...]

    def for_session(self, loss_limit_pct: Optional[Decimal]) -> "FuturesLimits":
        """The owner may pick a session's loss limit by his word, inside his approved band."""
        if loss_limit_pct is None:
            return self
        if not self.loss_range[0] <= loss_limit_pct <= self.loss_range[1]:
            raise FuturesError(f"límite de pérdida {loss_limit_pct}% fuera de la banda aprobada "
                               f"{self.loss_range[0]}-{self.loss_range[1]}%")
        from dataclasses import replace
        return replace(self, loss_limit_pct=loss_limit_pct)


def load_futures_limits(path: Path = DEFAULT_LIMITS) -> FuturesLimits:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        lo, hi = (Decimal(str(x)) for x in d["loss_limit_owner_range_pct"])
        target = d.get("profit_target_pct")
        limits = FuturesLimits(d.get("approved_by_owner") is True, int(d["max_leverage"]),
                               Decimal(str(d["risk_per_trade_pct"])), Decimal(str(d["max_position_pct"])),
                               int(d["max_open_positions"]), Decimal(str(d["loss_limit_pct"])), (lo, hi),
                               Decimal(str(d["warn_before_usd"])),
                               Decimal(str(target)) if target is not None else None, tuple(d["allowed_symbols"]))
        if d.get("withdrawals") is not False or d.get("transfers") is not False:
            raise ValueError("withdrawals and transfers must be false")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise FuturesError(f"límites de futuros ilegibles en {path}: {error}") from None
    if not (1 <= limits.max_leverage <= 5 and 0 < limits.risk_pct <= 2 and 0 < limits.max_position_pct <= 100
            and limits.max_open >= 1 and lo <= limits.loss_limit_pct <= hi and limits.warn_before_usd >= 0
            and limits.symbols):
        raise FuturesError("límites de futuros fuera de rango (apalancamiento 1-5, riesgo 0-2%, posición 0-100%)")
    return limits


class FuturesMarket:
    """HTTP to Binance USDⓈ-M: public market data always; signed calls only with credentials."""

    def __init__(self, credentials: Optional[FuturesCredentials] = None, journal_path: Optional[Path] = None, *,
                 transport: Optional[Callable[[str, str, Mapping[str, str], float], HttpResponse]] = None,
                 clock: Callable[[], float] = time.time) -> None:
        if credentials is not None and type(credentials) is not FuturesCredentials:
            raise TypeError("FuturesCredentials required")
        self._cred, self._transport, self._clock = credentials, transport or urllib_transport, clock
        self.journal = Journal(journal_path) if journal_path is not None else None
        self._offset_ms: Optional[int] = None
        self._synced_at = 0.0
        self._cooldown_until = 0.0
        self._blocked = False
        self._rules: dict[str, FuturesRules] = {}
        self._prepared: set[str] = set()

    def __repr__(self) -> str:
        return f"FuturesMarket(host={FAPI_HOST}, signed={self._cred is not None})"

    # --- transport ---------------------------------------------------------------

    def _send(self, method: str, host: str, path: str, query: str,
              headers: Mapping[str, str]) -> Optional[HttpResponse]:
        if self._blocked:
            raise Restricted("Binance respondió 403/451: bloqueado hasta que el dueño lo revise")
        if self._clock() < self._cooldown_until:
            raise Restricted("Binance pidió esperar (límite de peticiones)")
        url = f"https://{host}{path}?{query}" if query else f"https://{host}{path}"
        try:
            resp = self._transport(method, url, headers, TIMEOUT)
        except Exception as error:  # noqa: BLE001 - the text may contain the signed URL
            logger.warning("network failure (%s) on %s %s", type(error).__name__, method, path)
            return None
        if resp.status in (418, 429):
            try:
                wait = float({k.lower(): v for k, v in resp.headers.items()}.get("retry-after", "60"))
            except ValueError:
                wait = 60.0
            self._cooldown_until = self._clock() + max(wait, 1.0)
        elif resp.status in (403, 451):
            self._blocked = True
        return resp

    @staticmethod
    def _json(resp: Optional[HttpResponse]) -> object:
        if resp is None:
            return None
        try:
            return json.loads(resp.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def _public(self, path: str, params: Mapping[str, str]) -> object:
        resp = self._send("GET", FAPI_HOST, path, urllib.parse.urlencode(params), {})
        data = self._json(resp)
        if resp is None or resp.status != 200 or data is None:
            raise FuturesError(f"lectura pública fallida en {path} (HTTP {None if resp is None else resp.status})")
        return data

    def _sync_time(self) -> None:
        sent = self._clock()
        data = self._public("/fapi/v1/time", {})
        received = self._clock()
        server = data.get("serverTime") if isinstance(data, dict) else None
        if not isinstance(server, int):
            raise FuturesError("no pude leer la hora de Binance")
        self._offset_ms = server - int((sent + received) / 2 * 1000)
        self._synced_at = received

    def _signed(self, method: str, path: str, params: Mapping[str, str],
                host: str = FAPI_HOST) -> tuple[Optional[HttpResponse], object]:
        if self._cred is None:
            raise FuturesError("sin clave: este modo solo lee precios públicos")
        if self._offset_ms is None or self._clock() - self._synced_at >= TIME_RESYNC_SECONDS:
            self._sync_time()
        assert self._offset_ms is not None
        query = urllib.parse.urlencode({**params, "recvWindow": str(RECV_WINDOW_MS),
                                        "timestamp": str(int(self._clock() * 1000) + self._offset_ms)})
        query = f"{query}&signature={self._cred.sign(query)}"
        resp = self._send(method, host, path, query, self._cred.header())
        data = self._json(resp)
        if isinstance(data, dict) and data.get("code") == TIMESTAMP_REJECTED:
            self._offset_ms = None
        return resp, data

    def _signed_ok(self, method: str, path: str, params: Mapping[str, str], host: str = FAPI_HOST,
                   accept_codes: tuple[int, ...] = ()) -> object:
        resp, data = self._signed(method, path, params, host)
        code = data.get("code") if isinstance(data, dict) else None
        if code in accept_codes:
            return data
        if resp is None or resp.status != 200 or data is None or (isinstance(code, int) and code < 0):
            raise FuturesError(f"Binance rechazó {method} {path} (HTTP {None if resp is None else resp.status}, "
                               f"código {code})")
        return data

    # --- public reads ----------------------------------------------------------------

    def candles(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        if timeframe not in INTERVALS:
            raise ValueError(f"temporalidad no soportada en futuros: {timeframe}")
        payload = self._public("/fapi/v1/klines", {"symbol": symbol, "interval": timeframe, "limit": str(min(count, 1500))})
        if not isinstance(payload, list) or not payload:
            raise FuturesError(f"{symbol}: Binance no devolvió velas {timeframe}")
        frame = pd.DataFrame([{"open_time": int(k[0]), "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
                               "close": float(k[4]), "volume": float(k[5])} for k in payload])
        frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
        return frame.set_index("open_time")

    def book(self, symbol: str) -> tuple[Decimal, Decimal]:
        data = self._public("/fapi/v1/ticker/bookTicker", {"symbol": symbol})
        try:
            bid, ask = Decimal(str(data["bidPrice"])), Decimal(str(data["askPrice"]))  # type: ignore[index]
        except (KeyError, TypeError, ArithmeticError):
            raise FuturesError(f"{symbol}: cotización ilegible") from None
        if not (bid.is_finite() and ask.is_finite()) or bid <= 0 or ask < bid:
            raise FuturesError(f"{symbol}: cotización imposible (bid {bid}, ask {ask})")
        return bid, ask

    def rules(self, symbol: str) -> FuturesRules:
        if symbol in self._rules:
            return self._rules[symbol]
        data = self._public("/fapi/v1/exchangeInfo", {})
        for info in data.get("symbols", []) if isinstance(data, dict) else []:
            if info.get("symbol") != symbol:
                continue
            if info.get("status") != "TRADING" or info.get("contractType") != "PERPETUAL" \
                    or info.get("quoteAsset") != "USDT":
                raise FuturesError(f"{symbol} no es un perpetuo USDT activo")
            f = {x.get("filterType"): x for x in info.get("filters", [])}
            lot = f.get("MARKET_LOT_SIZE") or f.get("LOT_SIZE") or {}
            if Decimal(str(lot.get("stepSize", "0"))) <= 0:
                lot = f.get("LOT_SIZE") or {}
            rules = FuturesRules(Decimal(str(lot.get("stepSize", "0"))), Decimal(str(lot.get("minQty", "0"))),
                                 Decimal(str((f.get("MIN_NOTIONAL") or {}).get("notional", "5"))),
                                 Decimal(str((f.get("PRICE_FILTER") or {}).get("tickSize", "0"))))
            self._rules[symbol] = rules
            return rules
        raise FuturesError(f"{symbol} no existe en Binance Futuros")

    # --- signed reads ------------------------------------------------------------------

    def verify(self) -> None:
        check_futures_key(self._signed_ok("GET", "/sapi/v1/account/apiRestrictions", {}, host=SPOT_HOST))
        dual = self._signed_ok("GET", "/fapi/v1/positionSide/dual", {})
        if not isinstance(dual, dict) or dual.get("dualSidePosition") is not False:
            raise FuturesError("la cuenta de futuros está en modo cobertura (Hedge): cámbiala a unidireccional "
                               "(One-way) en la app de Binance")

    def balance(self) -> Decimal:
        data = self._signed_ok("GET", "/fapi/v3/account", {})
        try:
            return Decimal(str(data["totalMarginBalance"]))  # type: ignore[index]
        except (KeyError, TypeError, ArithmeticError):
            raise FuturesError("saldo de futuros ilegible") from None

    def position_amounts(self) -> dict[str, tuple[Decimal, Decimal]]:
        data = self._signed_ok("GET", "/fapi/v3/positionRisk", {})
        out = {}
        for p in data if isinstance(data, list) else []:
            amt = Decimal(str(p.get("positionAmt", "0")))
            if amt != 0:
                out[str(p.get("symbol"))] = (amt, Decimal(str(p.get("entryPrice", "0"))))
        return out

    def open_algos(self) -> list[dict]:
        data = self._signed_ok("GET", "/fapi/v1/openAlgoOrders", {})
        rows = data.get("orders", data) if isinstance(data, dict) else data
        return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []

    # --- orders ---------------------------------------------------------------------

    def prepare(self, symbol: str, leverage: int) -> None:
        if symbol in self._prepared:
            return
        self._signed_ok("POST", "/fapi/v1/marginType", {"symbol": symbol, "marginType": "ISOLATED"},
                        accept_codes=(NO_MARGIN_CHANGE,))
        self._signed_ok("POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": str(leverage)})
        self._prepared.add(symbol)

    def unresolved(self) -> list[str]:
        if self.journal is None:
            return []
        return [cid for cid, r in self.journal.read().items() if r.get("state") in ("PENDING_SEND", "UNCERTAIN")]

    def _set(self, cid: str, **fields: object) -> None:
        assert self.journal is not None
        orders = self.journal.read()
        orders[cid] = {**orders.get(cid, {}), **fields}
        self.journal.write(orders)

    def reconcile(self) -> None:
        """Looks up every unclear market order by its client id; never resends."""
        for cid in self.unresolved():
            rec = self.journal.read()[cid]  # type: ignore[union-attr]
            resp, data = self._signed("GET", "/fapi/v1/order", {"symbol": rec["symbol"], "origClientOrderId": cid})
            if isinstance(data, dict) and data.get("code") == ORDER_NOT_FOUND:
                self._set(cid, state="NOT_FOUND")
            elif resp is not None and resp.status == 200 and isinstance(data, dict) and "status" in data:
                self._set(cid, state=str(data["status"]), executed=str(data.get("executedQty", "0")),
                          avg=str(data.get("avgPrice", "0")))

    def market(self, symbol: str, side: str, qty: Decimal, *, reduce_only: bool) -> dict:
        if self.journal is None:
            raise FuturesError("sin diario de órdenes")
        self.reconcile()
        if self.unresolved():
            raise Unreconciled("hay una orden sin conciliar: no envío nada hasta resolverla")
        cid = CLIENT_PREFIX + uuid.uuid4().hex[:20]
        self._set(cid, state="PENDING_SEND", symbol=symbol, side=side, qty=str(qty), reduce_only=reduce_only,
                  at=datetime.now(timezone.utc).isoformat())
        params = {"symbol": symbol, "side": side, "type": "MARKET", "quantity": str(qty),
                  "newClientOrderId": cid, "newOrderRespType": "RESULT"}
        if reduce_only:
            params["reduceOnly"] = "true"
        resp, data = self._signed("POST", "/fapi/v1/order", params)
        if resp is not None and resp.status == 200 and isinstance(data, dict) and data.get("status") == "FILLED":
            self._set(cid, state="FILLED", executed=str(data.get("executedQty")), avg=str(data.get("avgPrice")))
            return data
        if resp is not None and resp.status == 400 and isinstance(data, dict) and isinstance(data.get("code"), int):
            self._set(cid, state="REJECTED", code=data["code"])
            raise FuturesError(f"Binance rechazó la orden de {symbol} (código {data['code']})")
        self._set(cid, state="UNCERTAIN")
        self.reconcile()
        rec = self.journal.read()[cid]
        if rec.get("state") == "FILLED":
            return {"executedQty": rec.get("executed"), "avgPrice": rec.get("avg"), "status": "FILLED"}
        if rec.get("state") == "NOT_FOUND":
            raise FuturesError(f"la orden de {symbol} no llegó a Binance")
        raise Unreconciled(f"respuesta dudosa de Binance para {symbol}: la reviso antes de enviar nada más")

    def conditional(self, symbol: str, side: str, kind: str, trigger: Decimal) -> str:
        """A STOP_MARKET or TAKE_PROFIT_MARKET that closes the whole position, on the Algo service."""
        cid = CLIENT_PREFIX + uuid.uuid4().hex[:20]
        data = self._signed_ok("POST", "/fapi/v1/algoOrder", {
            "algoType": "CONDITIONAL", "symbol": symbol, "side": side, "type": kind, "triggerPrice": str(trigger),
            "closePosition": "true", "workingType": "MARK_PRICE", "clientAlgoId": cid})
        algo = data.get("algoId") if isinstance(data, dict) else None
        if algo is None:
            raise FuturesError(f"Binance no confirmó el {kind} de {symbol}")
        return str(algo)

    def cancel_algo(self, symbol: str, algo_id: str) -> None:
        self._signed_ok("DELETE", "/fapi/v1/algoOrder", {"symbol": symbol, "algoId": algo_id},
                        accept_codes=(ORDER_NOT_FOUND,))


def size_plan(market: FuturesMarket, symbol: str, side: str, equity: Decimal, risk_pct: Decimal, timeframe: str,
              leverage: int, max_position_pct: Decimal) -> Plan:
    """Stop and target read from the market for that side (owner's crypto band 3-15%), size from risk."""
    from trading_intelligence.strategy.exit_plan import plan_exits

    if side not in ("BUY", "SELL"):
        raise ValueError("side must be BUY or SELL")
    if equity <= 0:
        raise FuturesError("saldo de futuros en cero: el dueño mueve USDT de Spot a Futuros en la app")
    bid, ask = market.book(symbol)
    price = ask if side == "BUY" else bid
    exits = plan_exits(market.candles(symbol, timeframe, 500), price, side=side,
                       min_stop_pct=CRYPTO_MIN_STOP_PCT, max_stop_pct=CRYPTO_MAX_STOP_PCT)
    rules = market.rules(symbol)
    long = side == "BUY"
    sl = rules.round_price(exits.stop, up=not long)  # never nearer the price than planned
    tp = rules.round_price(exits.target, up=not long)
    distance = abs(price - sl)
    if distance <= 0:
        raise FuturesError(f"{symbol}: stop sin distancia")
    qty = equity * risk_pct / 100 / distance
    qty = min(qty, Decimal(leverage) * equity * max_position_pct / 100 / price)  # the Spot program's 40% cap
    qty = rules.floor_qty(qty)
    if qty <= 0 or qty < rules.min_qty or qty * price < rules.min_notional:
        raise FuturesError(f"{symbol}: con {equity:.2f} USDT y riesgo {risk_pct}% la posición no llega al mínimo de "
                           f"Binance ({rules.min_notional} USDT): no se opera")
    return Plan(symbol, side, qty, price, sl, tp, (distance * qty).quantize(Decimal("0.01")))


class FuturesBroker:
    """REAL orders on Binance USDⓈ-M."""
    name, unit = "Binance Futuros", "unidades"

    def __init__(self, market: FuturesMarket, limits: FuturesLimits) -> None:
        if not limits.approved:
            raise FuturesError("los límites de futuros no están aprobados por el dueño: dinero real rechazado")
        self.market, self.limits = market, limits

    def equity(self) -> tuple[Decimal, str]:
        return self.market.balance(), "USDT"

    def positions(self) -> dict[str, Position]:
        """Our symbols' positions; stop/target orders left behind by a closed position are cancelled."""
        amounts = {s: v for s, v in self.market.position_amounts().items() if s in self.limits.symbols}
        for algo in self.market.open_algos():
            sym = str(algo.get("symbol"))
            if sym in self.limits.symbols and sym not in amounts and \
                    str(algo.get("clientAlgoId", "")).startswith(CLIENT_PREFIX):
                self.market.cancel_algo(sym, str(algo.get("algoId")))
        return {s: Position(s, "BUY" if amt > 0 else "SELL", abs(amt), f"{s}:{'L' if amt > 0 else 'S'}", entry)
                for s, (amt, entry) in amounts.items()}

    def candles(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        return self.market.candles(symbol, timeframe, count)

    def plan(self, symbol: str, side: str, risk_pct: Decimal, timeframe: str) -> Plan:
        return size_plan(self.market, symbol, side, self.market.balance(), min(risk_pct, self.limits.risk_pct),
                         timeframe, self.limits.max_leverage, self.limits.max_position_pct)

    def open(self, plan: Plan) -> str:
        self.market.prepare(plan.symbol, self.limits.max_leverage)
        self.market.market(plan.symbol, plan.side, plan.qty, reduce_only=False)
        exit_side = "SELL" if plan.side == "BUY" else "BUY"
        try:
            self.market.conditional(plan.symbol, exit_side, "STOP_MARKET", plan.sl)
        except LiveError:
            self.market.market(plan.symbol, exit_side, plan.qty, reduce_only=True)  # never left without a stop
            raise FuturesError(f"{plan.symbol}: Binance no aceptó el stop; cerré la posición al momento")
        try:
            self.market.conditional(plan.symbol, exit_side, "TAKE_PROFIT_MARKET", plan.tp)
        except LiveError as error:
            logger.warning("%s: take profit not placed (%s); the stop and the engine still guard it", plan.symbol, error)
        return f"{plan.symbol}:{'L' if plan.side == 'BUY' else 'S'}"

    def close(self, position: Position) -> None:
        for algo in self.market.open_algos():
            if algo.get("symbol") == position.symbol and str(algo.get("clientAlgoId", "")).startswith(CLIENT_PREFIX):
                self.market.cancel_algo(position.symbol, str(algo.get("algoId")))
        self.market.market(position.symbol, "SELL" if position.side == "BUY" else "BUY", position.qty,
                           reduce_only=True)

    def move_stop(self, position: Position, stop: Decimal, target: Decimal) -> None:
        """The stop that follows the gain: the new stop goes in first, then the old one is cancelled, so the
        position is never without one. If Binance refuses two at once, the old one is swapped; if the new
        one is still refused, the position is closed."""
        exit_side = "SELL" if position.side == "BUY" else "BUY"
        rules = self.market.rules(position.symbol)
        stop = rules.round_price(stop, up=position.side != "BUY")
        old = [str(a.get("algoId")) for a in self.market.open_algos()
               if a.get("symbol") == position.symbol and a.get("type") == "STOP_MARKET"
               and str(a.get("clientAlgoId", "")).startswith(CLIENT_PREFIX)]
        try:
            self.market.conditional(position.symbol, exit_side, "STOP_MARKET", stop)
        except LiveError:
            for algo_id in old:
                self.market.cancel_algo(position.symbol, algo_id)
            try:
                self.market.conditional(position.symbol, exit_side, "STOP_MARKET", stop)
            except LiveError:
                self.close(position)
                raise FuturesError(f"{position.symbol}: Binance no aceptó el stop nuevo; cerré la posición")
            return
        for algo_id in old:
            self.market.cancel_algo(position.symbol, algo_id)


class PaperFuturesBroker:
    """SHADOW: real public prices, simulated positions with their stop, target and taker fee."""
    name, unit = "Binance Futuros (SHADOW)", "unidades"

    def __init__(self, market: FuturesMarket, capital: Decimal, state_path: Path, *, leverage: int = 1,
                 max_position_pct: Decimal = Decimal("40"), fee: Decimal = TAKER_FEE) -> None:
        self.market, self.state_path, self.leverage, self.max_position_pct, self.fee = market, Path(state_path), \
            leverage, max_position_pct, fee
        self.book: dict[str, Any] = json.loads(self.state_path.read_text(encoding="utf-8")) \
            if self.state_path.exists() else {"cash": str(capital), "positions": {}, "closed": []}

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.book, indent=1), encoding="utf-8")
        tmp.replace(self.state_path)

    def _exit(self, sym: str, price: Decimal, why: str) -> None:
        p = self.book["positions"].pop(sym)
        qty, entry = Decimal(p["qty"]), Decimal(p["entry"])
        pnl = (price - entry) * qty if p["side"] == "BUY" else (entry - price) * qty
        fee = price * qty * self.fee
        self.book["cash"] = str(Decimal(self.book["cash"]) + pnl - fee)
        self.book["closed"].append({"symbol": sym, "side": p["side"], "entry": p["entry"], "exit": str(price),
                                    "qty": p["qty"], "pnl": str((pnl - fee - Decimal(p["fee"])).quantize(Decimal("0.0001"))),
                                    "why": why, "at": datetime.now(timezone.utc).isoformat()})

    def _settle(self) -> None:
        """A stop or a target touched since the last pass (on 1m bars) closes there; stop first if both."""
        for sym in list(self.book["positions"]):
            p = self.book["positions"][sym]
            bars = self.market.candles(sym, "1m", 120)
            bars = bars[bars.index + pd.Timedelta(minutes=1) > pd.Timestamp(p["checked"])]  # bars still open then
            if bars.empty:
                continue
            sl, tp, long = Decimal(p["sl"]), Decimal(p["tp"]), p["side"] == "BUY"
            low, high = Decimal(str(bars["low"].min())), Decimal(str(bars["high"].max()))
            if (long and low <= sl) or (not long and high >= sl):
                self._exit(sym, sl, "stop")
            elif (long and high >= tp) or (not long and low <= tp):
                self._exit(sym, tp, "meta")
            else:
                p["checked"] = bars.index[-1].isoformat()

    def equity(self) -> tuple[Decimal, str]:
        total = Decimal(self.book["cash"])
        for sym, p in self.book["positions"].items():
            bid, ask = self.market.book(sym)
            mid, qty, entry = (bid + ask) / 2, Decimal(p["qty"]), Decimal(p["entry"])
            total += (mid - entry) * qty if p["side"] == "BUY" else (entry - mid) * qty
        return total.quantize(Decimal("0.0001")), "USDT"

    def positions(self) -> dict[str, Position]:
        self._settle()
        self._save()
        return {s: Position(s, p["side"], Decimal(p["qty"]), p["ticket"], Decimal(p["entry"]))
                for s, p in self.book["positions"].items()}

    def candles(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        return self.market.candles(symbol, timeframe, count)

    def plan(self, symbol: str, side: str, risk_pct: Decimal, timeframe: str) -> Plan:
        return size_plan(self.market, symbol, side, self.equity()[0], risk_pct, timeframe, self.leverage,
                         self.max_position_pct)

    def open(self, plan: Plan) -> str:
        fee = plan.price * plan.qty * self.fee
        ticket = f"paper-{uuid.uuid4().hex[:8]}"
        self.book["cash"] = str(Decimal(self.book["cash"]) - fee)
        self.book["positions"][plan.symbol] = {
            "side": plan.side, "qty": str(plan.qty), "entry": str(plan.price), "sl": str(plan.sl), "tp": str(plan.tp),
            "fee": str(fee), "ticket": ticket, "checked": datetime.now(timezone.utc).isoformat()}
        self._save()
        return ticket

    def close(self, position: Position) -> None:
        bid, ask = self.market.book(position.symbol)
        self._exit(position.symbol, bid if position.side == "BUY" else ask, "señal contraria")
        self._save()

    def move_stop(self, position: Position, stop: Decimal, target: Decimal) -> None:
        self.book["positions"][position.symbol]["sl"] = str(stop)
        self._save()


def main(argv: Optional[list[str]] = None, transport=None, env: Optional[Mapping[str, str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Binance Futuros: operador automático en los dos sentidos")
    parser.add_argument("accion", nargs="?", choices=("operar", "continuar"), default="operar",
                        help="continuar: el dueño ordena seguir tras el aviso de pérdida")
    parser.add_argument("--modo", choices=("shadow", "real"), default="shadow")
    parser.add_argument("--capital", default="37", help="SHADOW: capital simulado en USDT")
    parser.add_argument("--limites", type=Path, default=DEFAULT_LIMITS)
    parser.add_argument("--limite-perdida", help="%% de la sesión, dentro de la banda que aprobó el dueño")
    parser.add_argument("--simbolos", nargs="+", help="por defecto, los de los límites")
    parser.add_argument("--temporalidad", default="5m")
    parser.add_argument("--ventanas", nargs="*", default=list(DEFAULT_WINDOWS))
    parser.add_argument("--cada-dentro", type=int, default=2)
    parser.add_argument("--cada-fuera", type=int, default=5)
    parser.add_argument("--senal", choices=VARIANTS, default=DEFAULT_VARIANT, help="lógica de entrada")
    parser.add_argument("--dir", type=Path, default=Path("live_runs/futures_auto"))
    parser.add_argument("--una-vez", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    d: Path = args.dir / args.modo
    if args.accion == "continuar":
        owner_continue(d)
        print("orden registrada: el operador la aplica en su próxima decisión")
        return 0
    try:
        limits = load_futures_limits(args.limites).for_session(
            Decimal(args.limite_perdida) if args.limite_perdida else None)
        if args.modo == "real":
            market = FuturesMarket(FuturesCredentials.from_env(env), d / "orders.json", transport=transport)
            broker: object = FuturesBroker(market, limits)
            market.verify()
        else:
            market = FuturesMarket(None, transport=transport)
            broker = PaperFuturesBroker(market, Decimal(args.capital), d / "paper.json", leverage=limits.max_leverage,
                                        max_position_pct=limits.max_position_pct)
        auto = TwoWayAuto(broker, list(args.simbolos or limits.symbols), d / "state.json",  # type: ignore[arg-type]
                          timeframe=args.temporalidad, risk_pct=limits.risk_pct, max_open=limits.max_open,
                          loss_limit_pct=limits.loss_limit_pct, warn_before=limits.warn_before_usd,
                          profit_target_pct=limits.profit_target_pct, windows=args.ventanas,
                          inside_every_min=args.cada_dentro, outside_every_min=args.cada_fuera,
                          signal=signal_for(args.senal), notify=make_notify(console, from_env()))
        equity, _ = auto.broker.equity()
        print(f"{auto.broker.name} · saldo {equity} USDT · {limits.max_leverage}x · riesgo {limits.risk_pct}% por "
              f"operación · posición máx. {limits.max_position_pct}% · {limits.max_open} posiciones · límite de "
              f"pérdida {limits.loss_limit_pct}% (aviso {limits.warn_before_usd} USD antes) · meta "
              f"{limits.profit_target_pct}% · señal {args.senal} · cada {args.cada_dentro} min en "
              f"{' '.join(args.ventanas)} (Ecuador), cada {args.cada_fuera} fuera")
        if args.una_vez:
            auto.step()
        else:
            auto.run()
    except (LiveError, ValueError) as error:
        print(f"Futuros: {error}")
        return 1
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
