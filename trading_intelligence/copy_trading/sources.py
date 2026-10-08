"""
Where trader data may come from. Only sources Binance offers and permits are accepted.

Verified 2026-10-08 against the official binance-connector-python source
(clients/copy_trading): the official Copy Trading API is exactly the two endpoints in
OFFICIAL_COPY_TRADING_ENDPOINTS, both about the CALLER's own lead-trader account. So:

- "binance_app_manual": figures the owner (or Claude Code local, with the owner) reads
  from the lead-trader pages of the Binance app/website and records in a snapshot
  file, with the capture time. No scraping.
- "binance_official_api": anything later obtainable through a documented endpoint.
- "synthetic": generated data for tests and demos; refused unless explicitly allowed,
  and always labelled as synthetic in reports.

Anything else (leaderboard scrapers, third-party "smart money" APIs built on
undocumented web endpoints) raises UnverifiedSource.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from trading_intelligence.copy_trading.models import LeaderAction, LeaderEvent, Market, Side, TraderRecord

OFFICIAL_COPY_TRADING_ENDPOINTS = {
    "/sapi/v1/copyTrading/futures/userStatus": "is the CALLER a futures lead trader (lead-trader account only)",
    "/sapi/v1/copyTrading/futures/leadSymbol": "symbols the CALLER may lead-trade (lead-trader account only)",
}
OFFICIAL_SOURCES = frozenset({"binance_app_manual", "binance_official_api"})
SYNTHETIC_SOURCE = "synthetic"


class UnverifiedSource(ValueError):
    """Data whose provenance is not an official, permitted Binance channel."""


@dataclass
class Snapshot:
    source: str
    captured_at: datetime
    traders: list[TraderRecord]
    events: list[LeaderEvent]

    @property
    def synthetic(self) -> bool:
        return self.source == SYNTHETIC_SOURCE


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp without timezone: {value!r}")
    return parsed.astimezone(timezone.utc)


def _dec(value: object) -> Decimal:
    d = Decimal(str(value))
    if not d.is_finite():
        raise ValueError(f"non-finite number {value!r}")
    return d


def check_source(source: str, *, allow_synthetic: bool = False) -> None:
    if source in OFFICIAL_SOURCES:
        return
    if source == SYNTHETIC_SOURCE and allow_synthetic:
        return
    raise UnverifiedSource(
        f"source {source!r} is not an official Binance channel; accepted: {sorted(OFFICIAL_SOURCES)}"
        + (" (synthetic data must be explicitly allowed)" if source == SYNTHETIC_SOURCE else "")
    )


def parse_snapshot(data: dict, *, allow_synthetic: bool = False) -> Snapshot:
    source = str(data.get("source", ""))
    check_source(source, allow_synthetic=allow_synthetic)
    captured_at = _dt(data["captured_at"])
    traders = []
    for t in data.get("traders", []):
        traders.append(TraderRecord(
            trader_id=str(t["trader_id"]),
            name=str(t.get("name", t["trader_id"])),
            market=Market(t["market"]),
            source=source,
            captured_at=captured_at,
            active=bool(t["active"]),
            daily_returns=tuple(_dec(r) for r in t["daily_returns"]),
            profit_share_pct=_dec(t.get("profit_share_pct", "10")),
            aum_usd=_dec(t["aum_usd"]) if t.get("aum_usd") is not None else None,
            copiers=int(t["copiers"]) if t.get("copiers") is not None else None,
            max_leverage=_dec(t.get("max_leverage", "1")),
            symbol_share={str(k): _dec(v) for k, v in t.get("symbol_share", {}).items()},
            closed_trade_pnls=tuple(_dec(p) for p in t.get("closed_trade_pnls", [])),
        ))
    ids = [t.trader_id for t in traders]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate trader_id in snapshot")
    events = []
    for e in data.get("events", []):
        if e["trader_id"] not in ids:
            raise ValueError(f"event for unknown trader {e['trader_id']!r}")
        ts = _dt(e["ts"])
        if ts > captured_at:
            raise ValueError(f"event at {ts.isoformat()} is after the snapshot capture time (look-ahead)")
        events.append(LeaderEvent(
            trader_id=str(e["trader_id"]), ts=ts, symbol=str(e["symbol"]),
            action=LeaderAction(e["action"]), side=Side(e["side"]), price=_dec(e["price"]),
            target_fraction=_dec(e["target_fraction"]), leverage=_dec(e.get("leverage", "1")),
        ))
    events.sort(key=lambda ev: ev.ts)
    return Snapshot(source=source, captured_at=captured_at, traders=traders, events=events)


def load_snapshot(path: Path, *, allow_synthetic: bool = False) -> Snapshot:
    return parse_snapshot(json.loads(Path(path).read_text(encoding="utf-8")), allow_synthetic=allow_synthetic)
