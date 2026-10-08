"""
SYNTHETIC copy-trading universe for tests and demos. Not market data, not real traders.

Each trader is built to exercise one rule:
  steady_a / steady_b  good long records -> selected
  martingale           good-looking record, then averages down -> blocked at runtime
  lucky_short          45 spectacular days -> HISTORY_TOO_SHORT
  deep_drawdown        big return, 50%+ drawdown -> DRAWDOWN_TOO_DEEP
  one_hit              profit from one trade -> PROFIT_CONCENTRATED_IN_FEW_TRADES
  illiquid             small caps -> ILLIQUID_SYMBOLS
  futures_20x          leveraged futures -> MARKET_NOT_ALLOWED, LEVERAGE_TOO_HIGH
  blown_up             stopped leading after losses -> INACTIVE (kept: survivorship)

Price paths (hours after the first event) make the risk rules visible: an ETH dip of
~4% that recovers (temporary drawdown, held), a SOL fall past the envelope while the
regime turns TREND_DOWN (thesis invalidated, exited before the leader), and an injected
order failure healed by the leader's next event.
"""
from __future__ import annotations

import random
from bisect import bisect_right
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

from trading_intelligence.copy_trading.evaluator import SelectionCriteria
from trading_intelligence.copy_trading.follower import ExecutionModel
from trading_intelligence.copy_trading.risk import CopyRiskConfig
from trading_intelligence.copy_trading.sources import parse_snapshot
from trading_intelligence.risk.models import RiskConfig

CAPTURED_AT = datetime(2026, 10, 1, tzinfo=timezone.utc)
T0 = CAPTURED_AT - timedelta(days=10)

PATHS: dict[str, list[tuple[float, float]]] = {
    "BTCUSDT": [(0, 60000), (48, 61000), (96, 63000), (150, 64500), (240, 64000)],
    "ETHUSDT": [(0, 2400), (30, 2410), (45, 2370), (55, 2335), (60, 2310), (100, 2380), (140, 2480), (240, 2470)],
    "SOLUSDT": [(0, 150), (40, 151), (60, 146), (70, 140), (90, 135), (130, 128), (240, 130)],
}
SOL_DOWNTREND = (62.0, 135.0)  # hours during which SOL's regime is TREND_DOWN


def _hours(ts: datetime) -> float:
    return (ts - T0).total_seconds() / 3600


def price_at(symbol: str, ts: datetime) -> Decimal:
    points = PATHS[symbol]
    h = _hours(ts)
    xs = [p[0] for p in points]
    i = bisect_right(xs, h)
    if i == 0:
        return Decimal(str(points[0][1]))
    if i == len(points):
        return Decimal(str(points[-1][1]))
    (x0, y0), (x1, y1) = points[i - 1], points[i]
    return Decimal(str(round(y0 + (y1 - y0) * (h - x0) / (x1 - x0), 6)))


def regime_at(symbol: str, ts: datetime) -> Optional[str]:
    if symbol == "SOLUSDT" and SOL_DOWNTREND[0] <= _hours(ts) <= SOL_DOWNTREND[1]:
        return "TREND_DOWN"
    return "RANGE"


def failure_at(symbol: str, ts: datetime) -> Optional[str]:
    if symbol == "ETHUSDT" and 30 <= _hours(ts) < 30.1:
        return "SIMULATED_EXCHANGE_TIMEOUT"
    return None


def _returns(seed: int, days: int, mean: float, vol: float) -> list[str]:
    rng = random.Random(seed)
    return [f"{max(-0.5, rng.gauss(mean, vol)):.6f}" for _ in range(days)]


def _trades(seed: int, n: int, mean: float, vol: float, one_hit: float = 0.0) -> list[str]:
    rng = random.Random(seed)
    pnls = [round(rng.gauss(mean, vol), 4) for _ in range(n)]
    if one_hit:
        pnls[0] = one_hit
    return [str(p) for p in pnls]


LIQUID = {"BTCUSDT": "0.4", "ETHUSDT": "0.35", "SOLUSDT": "0.25"}


def snapshot_data() -> dict:
    def trader(tid: str, name: str, *, seed: int, days: int, mean: float, vol: float, active: bool = True,
               market: str = "SPOT", leverage: str = "1", symbols: Optional[dict] = None,
               trades: Optional[list[str]] = None) -> dict:
        return {
            "trader_id": tid, "name": name, "market": market, "active": active,
            "daily_returns": _returns(seed, days, mean, vol), "profit_share_pct": "10",
            "aum_usd": "250000", "copiers": 120, "max_leverage": leverage,
            "symbol_share": symbols or LIQUID,
            "closed_trade_pnls": trades if trades is not None else _trades(seed + 1, 80, 12, 30),
        }

    def ev(tid: str, h: float, symbol: str, action: str, fraction: str, side: str = "LONG", leverage: str = "1") -> dict:
        ts = T0 + timedelta(hours=h)
        return {"trader_id": tid, "ts": ts.isoformat(), "symbol": symbol, "action": action, "side": side,
                "price": str(price_at(symbol, ts)), "target_fraction": fraction, "leverage": leverage}

    return {
        "source": "synthetic",
        "captured_at": CAPTURED_AT.isoformat(),
        "traders": [
            trader("steady_a", "steady_a", seed=1, days=420, mean=0.0016, vol=0.010),
            trader("steady_b", "steady_b", seed=2, days=320, mean=0.0013, vol=0.009),
            trader("martingale", "martingale", seed=3, days=400, mean=0.0012, vol=0.008),
            trader("lucky_short", "lucky_short", seed=4, days=45, mean=0.010, vol=0.02),
            trader("deep_drawdown", "deep_drawdown", seed=5, days=400, mean=0.003, vol=0.045),
            trader("one_hit", "one_hit", seed=6, days=400, mean=0.0010, vol=0.006,
                   trades=_trades(16, 40, -2, 10, one_hit=5000)),
            trader("illiquid", "illiquid", seed=7, days=400, mean=0.0015, vol=0.010,
                   symbols={"PEPEUSDT": "0.6", "FLOKIUSDT": "0.3", "BTCUSDT": "0.1"}),
            trader("futures_20x", "futures_20x", seed=8, days=400, mean=0.0020, vol=0.012,
                   market="USDM_FUTURES", leverage="20"),
            trader("blown_up", "blown_up", seed=9, days=300, mean=-0.004, vol=0.03, active=False),
        ],
        "events": [
            ev("steady_a", 2, "BTCUSDT", "OPEN", "0.5"),
            ev("steady_a", 100, "BTCUSDT", "INCREASE", "0.7"),
            ev("steady_a", 150, "BTCUSDT", "CLOSE", "0"),
            ev("steady_a", 30, "ETHUSDT", "OPEN", "0.4"),  # our first order fails (injected)
            ev("steady_a", 33, "ETHUSDT", "INCREASE", "0.45"),  # heals the failed copy
            ev("steady_a", 140, "ETHUSDT", "CLOSE", "0"),
            ev("steady_b", 40, "SOLUSDT", "OPEN", "0.5"),
            ev("steady_b", 130, "SOLUSDT", "CLOSE", "0"),
            ev("martingale", 31, "ETHUSDT", "OPEN", "0.2"),
            ev("martingale", 45, "ETHUSDT", "INCREASE", "0.4"),
            ev("martingale", 55, "ETHUSDT", "INCREASE", "0.6"),
            ev("martingale", 60, "ETHUSDT", "INCREASE", "0.8"),
            ev("illiquid", 10, "BTCUSDT", "OPEN", "0.3"),
            ev("futures_20x", 12, "SOLUSDT", "OPEN", "0.3", side="SHORT", leverage="20"),
        ],
    }


# PROPOSED research values for the demo account, not owner limits.
DEMO_RISK = RiskConfig(max_total_exposure_pct=60.0, max_open_positions=6, max_correlated_exposure_pct=60.0,
                       max_position_size_pct=20.0, max_daily_turnover_pct=500.0, max_trades_per_day=100)


def run(state_dir: Path, *, starting_equity: Decimal = Decimal("1000"),
        execution: Optional[ExecutionModel] = None, copy_config: Optional[CopyRiskConfig] = None):
    from trading_intelligence.copy_trading.pipeline import run_pipeline

    snap = parse_snapshot(snapshot_data(), allow_synthetic=True)
    return run_pipeline(
        snap, price_at, state_dir, starting_equity=starting_equity, criteria=SelectionCriteria(),
        copy_config=copy_config or CopyRiskConfig(), risk_config=DEMO_RISK, execution=execution or ExecutionModel(),
        regime_at=regime_at, failure_at=failure_at,
    )
