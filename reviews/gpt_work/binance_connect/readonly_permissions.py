"""One-shot Binance account permission check. Never places orders or saves keys.

Run interactively: python -B readonly_permissions.py
The API key and secret are entered without echo and remain only in this process.
"""

from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import sys
import time
from collections.abc import Callable
from typing import Any
from urllib import error, parse, request


API_BASE = "https://api.binance.com"
PERMISSIONS_PATH = "/sapi/v1/account/apiRestrictions"
MAX_RESPONSE_BYTES = 16_384
PERMISSION_FLAGS = frozenset({
    "enableReading",
    "enableWithdrawals",
    "enableInternalTransfer",
    "enableMargin",
    "enableFutures",
    "permitsUniversalTransfer",
    "enableVanillaOptions",
    "enableFixApiTrade",
    "enableFixReadOnly",
    "enableSpotAndMarginTrading",
    "enablePortfolioMarginTrading",
})
RESPONSE_FIELDS = PERMISSION_FLAGS | {"ipRestrict", "createTime"}


class NoRedirect(request.HTTPRedirectHandler):
    """Never forward the API key or URL signature to a redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def build_request(api_key: str, secret: str, timestamp_ms: int) -> request.Request:
    """Construct only the documented signed, read-only permissions GET."""
    if not api_key or not secret:
        raise ValueError("API key and secret are required")
    query = parse.urlencode((("timestamp", timestamp_ms), ("recvWindow", 5000)))
    signature = hmac.new(secret.encode("utf-8"), query.encode("ascii"), hashlib.sha256).hexdigest()
    return request.Request(
        f"{API_BASE}{PERMISSIONS_PATH}?{query}&signature={signature}",
        headers={"X-MBX-APIKEY": api_key},
        method="GET",
    )


def summarize_permissions(payload: Any) -> tuple[bool, tuple[str, ...]]:
    """Fail closed unless Binance explicitly reports read and no trade/withdrawal."""
    if not isinstance(payload, dict):
        raise ValueError("Invalid permissions response")
    if set(payload) - RESPONSE_FIELDS:
        raise ValueError("Unexpected field in permissions response")
    for name in PERMISSION_FLAGS:
        if type(payload.get(name)) is not bool:
            raise ValueError(f"Missing or invalid permission flag: {name}")
    active_non_read = tuple(
        sorted(
            name
            for name in PERMISSION_FLAGS
            if name not in ("enableReading", "enableFixReadOnly")
            and payload[name] is True
        )
    )
    read_only = payload["enableReading"] and not active_non_read
    return read_only, active_non_read


def check_permissions(
    api_key: str,
    secret: str,
    *,
    opener: Callable[..., Any] | None = None,
    timestamp_ms: int | None = None,
) -> tuple[bool, tuple[str, ...]]:
    """Perform exactly one signed GET; return flags, never balances or identity."""
    signed = build_request(api_key, secret, timestamp_ms if timestamp_ms is not None else int(time.time() * 1000))
    if opener is None:
        opener = request.build_opener(NoRedirect()).open
    with opener(signed, timeout=10) as response:
        if response.status != 200:
            raise ValueError(f"Unexpected HTTP status: {response.status}")
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Permissions response too large")
    return summarize_permissions(json.loads(raw))


def main() -> int:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("Ejecuta esta comprobación en una consola PowerShell interactiva.")
        return 2
    print("Una sola consulta GET firmada de permisos. No consulta saldos ni envía órdenes.")
    api_key = getpass.getpass("API key de solo lectura (oculta): ").strip()
    secret = getpass.getpass("Secret de esa clave (oculto): ").strip()
    try:
        read_only, extra = check_permissions(api_key, secret)
    except error.HTTPError as exc:
        print(f"Binance rechazó la consulta (HTTP {exc.code}). No se imprimieron credenciales.")
        return 1
    except (error.URLError, TimeoutError, OSError):
        print("No se pudo contactar la API de Binance desde esta PC.")
        return 1
    except (ValueError, json.JSONDecodeError):
        print("La respuesta de permisos no pudo validarse; no se considera conectada.")
        return 1
    finally:
        del secret
    if not read_only:
        print("Conexión autenticada, pero la clave NO es exclusivamente de lectura.")
        print("Permisos adicionales activos: " + (", ".join(extra) or "lectura deshabilitada"))
        return 2
    print("Conexión autenticada de SOLO LECTURA: OK. Trading y retiros deshabilitados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
