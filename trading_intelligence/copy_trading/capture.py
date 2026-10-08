"""
Owner-friendly capture: one CSV row per lead trader, exactly as the Binance app shows
it, converted into a validated snapshot (source "binance_app_manual").

    python -m trading_intelligence.copy_trading.capture traders.csv \
        --captured-at 2026-10-08T15:00:00-05:00 --out docs/snapshots/binance_app_2026-10-08.json

Columns (header row required; see docs/templates/copy_trading_capture.template.csv):
  trader_id, name, market (SPOT|USDM_FUTURES), active (yes/no), profit_share_pct,
  aum_usd, copiers, max_leverage, roi_7d, roi_30d, roi_90d, roi_180d, mdd_pct,
  lead_days, trades, win_rate_pct,
  symbols      "BTCUSDT:45;ETHUSDT:35;SOLUSDT:20"   (% of trading, as shown)
  last_pnls    "12.4;-3.1;8.0;..."                  (realized PnL of recent closed positions)

Empty cells are allowed where the app shows nothing; the evaluator then fails the
related criterion closed (unknown is never a pass). No API key or account data here.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from trading_intelligence.copy_trading.sources import parse_snapshot

REQUIRED = ("trader_id", "market", "active", "mdd_pct", "lead_days", "trades")
ROI_COLUMNS = {7: "roi_7d", 30: "roi_30d", 90: "roi_90d", 180: "roi_180d"}
_YES = {"yes", "si", "sí", "true", "1", "y", "s"}
_NO = {"no", "false", "0", "n"}


class CaptureError(ValueError):
    pass


def _num(row: dict, col: str, line: int, *, required: bool = False) -> Optional[str]:
    raw = (row.get(col) or "").strip().replace("%", "").replace(",", "")
    if not raw:
        if required:
            raise CaptureError(f"line {line}: column {col!r} is required")
        return None
    try:
        d = Decimal(raw)
    except InvalidOperation:
        raise CaptureError(f"line {line}: column {col!r} is not a number: {row.get(col)!r}") from None
    if not d.is_finite():
        raise CaptureError(f"line {line}: column {col!r} is not finite")
    return str(d)


def _pairs(text: str, line: int) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in filter(None, (p.strip() for p in (text or "").split(";"))):
        if ":" not in part:
            raise CaptureError(f"line {line}: symbols entry {part!r} must look like BTCUSDT:45")
        sym, pct = (x.strip() for x in part.split(":", 1))
        try:
            share = Decimal(pct.replace("%", "")) / 100
        except InvalidOperation:
            raise CaptureError(f"line {line}: bad share in {part!r}") from None
        out[sym.upper()] = str(share)
    total = sum((Decimal(v) for v in out.values()), Decimal("0"))
    if out and abs(total - 1) > Decimal("0.05"):
        raise CaptureError(f"line {line}: symbol shares add up to {total * 100:.0f}%, expected about 100%")
    return out


def rows_to_snapshot(rows: list[dict], captured_at: str) -> dict:
    when = datetime.fromisoformat(captured_at)
    if when.tzinfo is None:
        raise CaptureError("--captured-at needs a timezone, e.g. 2026-10-08T15:00:00-05:00")
    traders = []
    for i, row in enumerate(rows, start=2):
        row = {(k or "").strip().lower(): (v or "") for k, v in row.items()}
        for col in REQUIRED:
            if not row.get(col, "").strip():
                raise CaptureError(f"line {i}: column {col!r} is required")
        active = row["active"].strip().lower()
        if active not in _YES | _NO:
            raise CaptureError(f"line {i}: active must be yes/no, got {row['active']!r}")
        roi = {d: v for d, col in ROI_COLUMNS.items() if (v := _num(row, col, i)) is not None}
        trader: dict = {
            "trader_id": row["trader_id"].strip(),
            "name": (row.get("name") or row["trader_id"]).strip(),
            "market": row["market"].strip().upper(),
            "active": active in _YES,
            "max_leverage": _num(row, "max_leverage", i) or "1",
            "reported": {
                "roi_pct_by_days": {str(d): v for d, v in roi.items()},
                "max_drawdown_pct": _num(row, "mdd_pct", i, required=True),
                "lead_days": int(Decimal(_num(row, "lead_days", i, required=True) or "0")),
                "trades": int(Decimal(_num(row, "trades", i, required=True) or "0")),
                "win_rate_pct": _num(row, "win_rate_pct", i),
            },
            "symbol_share": _pairs(row.get("symbols", ""), i),
            "closed_trade_pnls": [p for p in (x.strip() for x in (row.get("last_pnls") or "").split(";")) if p],
        }
        for col in ("profit_share_pct", "aum_usd"):
            if (v := _num(row, col, i)) is not None:
                trader[col] = v
        if (v := _num(row, "copiers", i)) is not None:
            trader["copiers"] = int(Decimal(v))
        traders.append(trader)
    data = {"source": "binance_app_manual", "captured_at": when.isoformat(), "traders": traders, "events": []}
    parse_snapshot(data)  # the same validation every consumer applies
    return data


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Convert a lead-trader capture CSV into a snapshot.")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--captured-at", required=True, help="when the figures were read, with timezone")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    with args.csv.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    try:
        data = rows_to_snapshot(rows, args.captured_at)
    except (CaptureError, ValueError) as error:
        print(f"Capture rejected: {error}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Snapshot written: {args.out} ({len(data['traders'])} traders, "
          f"{sum(1 for t in data['traders'] if not t['active'])} no longer leading)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
