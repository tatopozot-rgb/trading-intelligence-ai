"""
Binance Spot REAL-money transport. Standard library only (the owner's PC blocks
unsigned DLLs). Host fixed to api.binance.com; MARKET orders only; never a withdrawal,
transfer, margin or futures path.

Safety rules (same design as Claude Code local's Testnet transport, PR #9 H2):
- The key must have Spot trading and reading, IP restriction, and NOTHING else:
  withdrawals, transfers, margin, futures or any unknown permission -> refused.
- Every order is written to a journal BEFORE it is sent. An uncertain answer
  (timeout, 5xx, unreadable) is never resent: it is reconciled by client order id,
  and no new order is sent while one is unreconciled.
- 418/429 -> cooldown (Retry-After); 403/451 -> blocked until the owner reviews.
- Credentials come from the PC's environment by NAME; their values never appear in
  a repr, log, exception or journal.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Callable, Mapping, Optional

logger = logging.getLogger(__name__)

HOST = "api.binance.com"
BASE = f"https://{HOST}"
KEY_VAR = "BINANCE_TRADE_API_KEY"
SECRET_VAR = "BINANCE_TRADE_SECRET_KEY"
RECV_WINDOW_MS = 5000
TIMEOUT = 15.0
RESTRICTED = {403, 418, 429, 451}
ALLOWED_TRUE_PERMISSIONS = frozenset({"enableReading", "enableSpotAndMarginTrading", "enableFixReadOnly"})
_SYMBOL = re.compile(r"^[A-Z0-9]{5,20}$")

PENDING, FILLED, REJECTED, UNCERTAIN, NOT_FOUND = "PENDING_SEND", "FILLED", "REJECTED", "UNCERTAIN", "NOT_FOUND"
UNRESOLVED = frozenset({PENDING, UNCERTAIN})


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


Transport = Callable[[str, str, Mapping[str, str], float], HttpResponse]


class LiveError(RuntimeError):
    """Fixed, safe message: never a key, signature, signed query or remote body."""


class UnsafeKey(LiveError):
    pass


class Restricted(LiveError):
    pass


class Unreconciled(LiveError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # a redirect would forward the key header to another host


def urllib_transport(method: str, url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
    if urllib.parse.urlsplit(url).netloc != HOST or not url.startswith("https://"):
        raise LiveError("only https://api.binance.com is allowed")
    opener = urllib.request.build_opener(_NoRedirect())
    req = urllib.request.Request(url, headers=dict(headers), method=method, data=b"" if method == "POST" else None)
    try:
        with opener.open(req, timeout=timeout) as resp:
            return HttpResponse(resp.status, dict(resp.headers.items()), resp.read(5_000_001))
    except urllib.error.HTTPError as error:
        with error:
            return HttpResponse(error.code, dict(error.headers.items()), error.read(5_000_001))


class Credentials:
    __slots__ = ("_key", "_secret")
    _FORMAT = re.compile(r"[A-Za-z0-9]{16,256}")

    def __init__(self, key: str, secret: str) -> None:
        for value in (key, secret):
            if type(value) is not str or not self._FORMAT.fullmatch(value):
                raise LiveError("credential with unexpected format")
        self._key, self._secret = key, secret

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "Credentials":
        env = os.environ if env is None else env
        key, secret = env.get(KEY_VAR), env.get(SECRET_VAR)
        if not key or not secret:
            raise LiveError(f"{KEY_VAR} / {SECRET_VAR} are not set on this PC (WAITING_FOR_USER)")
        return cls(key, secret)

    def header(self) -> dict[str, str]:
        return {"X-MBX-APIKEY": self._key}

    def sign(self, query: str) -> str:
        return hmac.new(self._secret.encode(), query.encode(), hashlib.sha256).hexdigest()

    def __repr__(self) -> str:
        return "Credentials(<redacted>)"

    __str__ = __repr__

    def __reduce__(self):
        raise TypeError("credentials are not serializable")


def check_key_permissions(data: object) -> bool:
    """Returns ipRestrict (True). Raises UnsafeKey for anything but read + Spot trading."""
    if not isinstance(data, dict):
        raise UnsafeKey("could not determine the key's permissions")
    if data.get("enableWithdrawals") is not False:
        raise UnsafeKey("the key has WITHDRAWALS enabled (or unknown): disable them in Binance")
    if data.get("enableReading") is not True or data.get("enableSpotAndMarginTrading") is not True:
        raise UnsafeKey("the key needs reading and Spot trading enabled")
    if data.get("ipRestrict") is not True:
        raise UnsafeKey("the trading key must be restricted to this PC's IP")
    for name, value in data.items():
        if isinstance(name, str) and name.startswith(("enable", "permits")):
            if not isinstance(value, bool):
                raise UnsafeKey("the key has a permission that could not be determined")
            if value and name not in ALLOWED_TRUE_PERMISSIONS:
                label = name if re.fullmatch(r"[A-Za-z]{1,60}", name) else "unknown"
                raise UnsafeKey(f"the key has a permission that is not allowed: {label}")
    return True


@dataclass(frozen=True)
class SymbolRules:
    step: Decimal
    min_qty: Decimal
    min_notional: Decimal

    def floor_qty(self, qty: Decimal) -> Decimal:
        if self.step <= 0:
            return qty
        return (qty / self.step).to_integral_value(rounding=ROUND_DOWN) * self.step


@dataclass(frozen=True)
class Fill:
    client_id: str
    symbol: str
    side: str
    status: str
    executed_qty: Decimal  # base asset, net of any commission charged in the base asset
    quote_qty: Decimal  # USDT spent (BUY) or received (SELL), net of commission charged in USDT
    fee_usdt: Decimal  # all commission valued in USDT (BNB valued at its price)
    avg_price: Decimal
    fee_other_usdt: Decimal = Decimal("0")  # commission paid in another asset (e.g. BNB), valued in USDT


class Journal:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def read(self) -> dict[str, dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            raise LiveError("order journal unreadable: needs review") from None
        if not isinstance(data, dict) or not isinstance(data.get("orders"), dict):
            raise LiveError("order journal malformed: needs review")
        return data["orders"]

    def write(self, orders: Mapping[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
        tmp.write_text(json.dumps({"orders": orders}, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)


class SpotTrader:
    def __init__(self, credentials: Optional[Credentials], journal_path: Path, *,
                 transport: Optional[Transport] = None, clock: Callable[[], float] = time.time) -> None:
        """credentials=None: public market data only (prices, exchange rules); any
        signed call raises."""
        if credentials is not None and type(credentials) is not Credentials:
            raise TypeError("Credentials required")
        self._cred = credentials
        self._transport = transport or urllib_transport
        self._clock = clock
        self.journal = Journal(journal_path)
        self._offset_ms: Optional[int] = None
        self._cooldown_until = 0.0
        self._blocked = False
        self._rules: dict[str, SymbolRules] = {}
        self.key_checked = False

    def __repr__(self) -> str:
        return f"SpotTrader(host={HOST}, key_checked={self.key_checked})"

    # --- transport ---------------------------------------------------------

    def _send(self, method: str, path: str, query: str, headers: Mapping[str, str]) -> Optional[HttpResponse]:
        if self._blocked:
            raise Restricted("Binance answered 403/451 earlier: blocked until the owner reviews")
        if self._clock() < self._cooldown_until:
            raise Restricted("Binance rate-limit cooldown active")
        url = f"{BASE}{path}?{query}" if query else f"{BASE}{path}"
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
        resp = self._send("GET", path, urllib.parse.urlencode(params), {})
        data = self._json(resp)
        if resp is None or resp.status != 200 or data is None:
            raise LiveError(f"public read failed on {path} (HTTP {None if resp is None else resp.status})")
        return data

    def _sync_time(self) -> None:
        data = self._public("/api/v3/time", {})
        server = data.get("serverTime") if isinstance(data, dict) else None
        if not isinstance(server, int):
            raise LiveError("could not read Binance server time")
        self._offset_ms = server - int(self._clock() * 1000)

    def _signed(self, method: str, path: str, params: Mapping[str, str]) -> Optional[HttpResponse]:
        if self._cred is None:
            raise LiveError("no credentials: this trader is public-data only")
        if self._offset_ms is None:
            self._sync_time()
        assert self._offset_ms is not None
        query = urllib.parse.urlencode({**params, "recvWindow": str(RECV_WINDOW_MS),
                                        "timestamp": str(int(self._clock() * 1000) + self._offset_ms)})
        query = f"{query}&signature={self._cred.sign(query)}"
        return self._send(method, path, query, self._cred.header())

    def _signed_read(self, path: str, params: Mapping[str, str]) -> object:
        resp = self._signed("GET", path, params)
        data = self._json(resp)
        if resp is None or resp.status != 200 or data is None or (isinstance(data, dict) and "code" in data):
            code = data.get("code") if isinstance(data, dict) else None
            raise LiveError(f"signed read failed on {path} (HTTP {None if resp is None else resp.status}, code {code})")
        return data

    # --- reads ---------------------------------------------------------------

    def verify_key(self) -> bool:
        self.key_checked = False
        ip_restricted = check_key_permissions(self._signed_read("/sapi/v1/account/apiRestrictions", {}))
        self.key_checked = True
        return ip_restricted

    def free_balance(self, asset: str) -> Decimal:
        data = self._signed_read("/api/v3/account", {"omitZeroBalances": "true"})
        for b in data.get("balances", []) if isinstance(data, dict) else []:
            if b.get("asset") == asset:
                return Decimal(str(b["free"]))
        return Decimal("0")

    def price(self, symbol: str) -> Decimal:
        if not _SYMBOL.match(symbol):
            raise ValueError(f"invalid symbol {symbol!r}")
        data = self._public("/api/v3/ticker/price", {"symbol": symbol})
        p = Decimal(str(data["price"])) if isinstance(data, dict) and "price" in data else Decimal("0")
        if not p.is_finite() or p <= 0:
            raise LiveError(f"impossible price for {symbol}")
        return p

    def rules(self, symbol: str) -> SymbolRules:
        if symbol in self._rules:
            return self._rules[symbol]
        data = self._public("/api/v3/exchangeInfo", {"symbol": symbol})
        try:
            info = data["symbols"][0]  # type: ignore[index]
            filters = {f["filterType"]: f for f in info["filters"]}
        except (KeyError, IndexError, TypeError):
            raise LiveError(f"exchange rules unavailable for {symbol}") from None
        if info.get("status") != "TRADING" or info.get("quoteAsset") != "USDT":
            raise LiveError(f"{symbol} is not a trading USDT pair")
        lot = filters.get("MARKET_LOT_SIZE") or {}
        step = Decimal(str(lot.get("stepSize", "0")))
        if step <= 0:
            lot = filters.get("LOT_SIZE", {})
            step = Decimal(str(lot.get("stepSize", "0")))
        notional = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL") or {}
        rules = SymbolRules(step=step, min_qty=Decimal(str(lot.get("minQty", "0"))),
                            min_notional=Decimal(str(notional.get("minNotional", "5"))))
        self._rules[symbol] = rules
        return rules

    # --- orders --------------------------------------------------------------

    def unresolved(self) -> list[str]:
        return sorted(k for k, o in self.journal.read().items() if o["state"] in UNRESOLVED)

    def market_order(self, symbol: str, side: str, quantity: Decimal, fee_price: Callable[[str], Decimal]) -> Fill:
        if not self.key_checked:
            raise UnsafeKey("key permissions not verified in this process")
        if side not in ("BUY", "SELL") or not _SYMBOL.match(symbol) or quantity <= 0:
            raise ValueError("invalid order")
        orders = self.journal.read()
        if any(o["state"] in UNRESOLVED for o in orders.values()):
            raise Unreconciled("an earlier order is unresolved: reconcile before sending another")
        client_id = f"ti-{uuid.uuid4().hex[:24]}"
        record = {"state": PENDING, "symbol": symbol, "side": side, "quantity": str(quantity),
                  "created": self._clock()}
        orders[client_id] = record
        self.journal.write(orders)  # if this fails, nothing is sent
        resp = self._signed("POST", "/api/v3/order", {
            "symbol": symbol, "side": side, "type": "MARKET", "quantity": format(quantity, "f"),
            "newClientOrderId": client_id, "newOrderRespType": "FULL"})
        data = self._json(resp)
        if resp is not None and resp.status == 200 and isinstance(data, dict) and data.get("clientOrderId") == client_id:
            fill = self._fill_from(client_id, data, fee_price)
            record.update(state=FILLED if fill.executed_qty > 0 else REJECTED, executed=str(fill.executed_qty),
                          quote=str(fill.quote_qty), fee_usdt=str(fill.fee_usdt), status=fill.status)
            self.journal.write(orders)
            return fill
        code = data.get("code") if isinstance(data, dict) else None
        if resp is not None and 400 <= resp.status < 500 and resp.status not in RESTRICTED and isinstance(code, int):
            record.update(state=REJECTED, code=code)
            self.journal.write(orders)
            raise LiveError(f"Binance rejected the order (code {code})")
        record.update(state=UNCERTAIN, http=None if resp is None else resp.status)
        self.journal.write(orders)
        raise Unreconciled(f"order {client_id} outcome unknown: it will be reconciled, never resent")

    def reconcile(self, fee_price: Callable[[str], Decimal]) -> list[Fill]:
        """Looks up every unresolved order by client id. Returns the fills it confirms."""
        orders = self.journal.read()
        confirmed: list[Fill] = []
        for client_id in sorted(k for k, o in orders.items() if o["state"] in UNRESOLVED):
            record = orders[client_id]
            resp = self._signed("GET", "/api/v3/order", {"symbol": record["symbol"], "origClientOrderId": client_id})
            data = self._json(resp)
            if resp is not None and resp.status == 200 and isinstance(data, dict) and data.get("clientOrderId") == client_id:
                trades = self._signed_read("/api/v3/myTrades", {"symbol": record["symbol"], "orderId": str(data["orderId"])})
                data = {**data, "fills": [{"price": t["price"], "qty": t["qty"], "commission": t["commission"],
                                           "commissionAsset": t["commissionAsset"]}
                                          for t in trades if isinstance(t, dict)]} if isinstance(trades, list) else data
                if data.get("status") in ("NEW", "PARTIALLY_FILLED", "PENDING_NEW"):
                    continue  # still working: stays unresolved, looked up again next time
                fill = self._fill_from(client_id, data, fee_price)
                record.update(state=FILLED if fill.executed_qty > 0 else REJECTED, executed=str(fill.executed_qty),
                              quote=str(fill.quote_qty), fee_usdt=str(fill.fee_usdt), status=fill.status)
                if fill.executed_qty > 0:
                    confirmed.append(fill)
            elif resp is not None and resp.status == 400 and isinstance(data, dict) and data.get("code") == -2013 \
                    and self._clock() - record["created"] >= 10:
                record["state"] = NOT_FOUND
            self.journal.write(orders)
        return confirmed

    def _fill_from(self, client_id: str, data: dict, fee_price: Callable[[str], Decimal]) -> Fill:
        symbol, side = data["symbol"], data["side"]
        base = symbol[:-4]
        executed = Decimal(str(data.get("executedQty", "0")))
        quote = Decimal(str(data.get("cummulativeQuoteQty", "0")))
        fee_base = fee_quote = fee_other_usdt = Decimal("0")
        for f in data.get("fills", []) or []:
            commission, asset = Decimal(str(f.get("commission", "0"))), f.get("commissionAsset")
            if asset == base:
                fee_base += commission
            elif asset == "USDT":
                fee_quote += commission
            elif commission > 0:
                fee_other_usdt += commission * fee_price(f"{asset}USDT")
        avg = quote / executed if executed > 0 else Decimal("0")
        if side == "BUY":
            net_qty, net_quote = executed - fee_base, quote + fee_quote
        else:
            net_qty, net_quote = executed, quote - fee_quote
        fee_usdt = fee_base * avg + fee_quote + fee_other_usdt
        return Fill(client_id, symbol, side, str(data.get("status")), net_qty, net_quote, fee_usdt, avg,
                    fee_other_usdt)
