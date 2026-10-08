"""
Evaluate and select lead traders with auditable criteria, not by recent gains.

Every trader gets the same metrics, every rejection names the failed criteria, and a
selection keeps incumbents unless they fail a criterion or a newcomer is materially
better (hysteresis), so the portfolio does not churn on noise.

Survivorship: returns are shrunk toward zero by history length (a short lucky record
counts for little), traders that stopped leading stay in the universe statistics, and a
snapshot with no inactive traders is flagged: it only shows today's winners.

The thresholds in SelectionCriteria are PROPOSED defaults for PAPER research, not
owner-ratified values.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Optional

from trading_intelligence.copy_trading.models import Market, TraderRecord

DEFAULT_LIQUID_SYMBOLS = frozenset({
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "TRXUSDT",
    "LINKUSDT", "AVAXUSDT", "DOTUSDT", "LTCUSDT", "BCHUSDT", "TONUSDT", "SUIUSDT",
})

# Rejection / removal reason codes (stable strings: they are journaled and reported).
INACTIVE = "INACTIVE"
MARKET_NOT_ALLOWED = "MARKET_NOT_ALLOWED"
HISTORY_TOO_SHORT = "HISTORY_TOO_SHORT"
TOO_FEW_TRADES = "TOO_FEW_TRADES"
DRAWDOWN_TOO_DEEP = "DRAWDOWN_TOO_DEEP"
NOT_PROFITABLE_AFTER_SHRINKAGE = "NOT_PROFITABLE_AFTER_SHRINKAGE"
INCONSISTENT = "INCONSISTENT"
PROFIT_CONCENTRATED_IN_FEW_TRADES = "PROFIT_CONCENTRATED_IN_FEW_TRADES"
SYMBOL_CONCENTRATED = "SYMBOL_CONCENTRATED"
ILLIQUID_SYMBOLS = "ILLIQUID_SYMBOLS"
LEVERAGE_TOO_HIGH = "LEVERAGE_TOO_HIGH"

# A trader failing one of these has a broken thesis: copied positions are exited now.
# Any other failure (or being out-ranked) is a wind-down: no new entries, follow exits.
INVALIDATING_REASONS = frozenset({INACTIVE, DRAWDOWN_TOO_DEEP, LEVERAGE_TOO_HIGH, MARKET_NOT_ALLOWED})


@dataclass(frozen=True)
class SelectionCriteria:
    allowed_markets: frozenset[Market] = frozenset({Market.SPOT})
    min_history_days: int = 180
    min_trades: int = 20
    max_drawdown: Decimal = Decimal("0.35")
    min_shrunk_annual_return: Decimal = Decimal("0")
    shrinkage_prior_days: int = 365
    min_consistency: Decimal = Decimal("0.5")  # share of positive 30-day blocks
    max_top3_trade_share: Decimal = Decimal("0.5")  # of gross realized profit
    max_symbol_share: Decimal = Decimal("0.6")
    min_liquid_share: Decimal = Decimal("0.8")
    liquid_symbols: frozenset[str] = DEFAULT_LIQUID_SYMBOLS
    max_leverage: Decimal = Decimal("1")
    max_selected: int = 3
    displace_ratio: Decimal = Decimal("1.3")  # a newcomer must score 30% above the incumbent it replaces
    drawdown_floor: Decimal = Decimal("0.05")  # score denominator floor


@dataclass
class TraderMetrics:
    history_days: int
    trades: int
    total_net_return: Decimal
    annual_net_return: Decimal
    shrunk_annual_return: Decimal
    max_drawdown: Decimal
    consistency: Decimal
    worst_30d: Decimal
    top3_trade_share: Optional[Decimal]
    max_symbol_share: Optional[Decimal]
    liquid_share: Optional[Decimal]
    score: Decimal
    basis: str = "daily_series"  # or "reported_windows" (app figures: coarser, flagged in reports)


@dataclass
class TraderEvaluation:
    trader_id: str
    name: str
    active: bool
    metrics: TraderMetrics
    failed: list[str] = field(default_factory=list)

    @property
    def eligible(self) -> bool:
        return not self.failed


@dataclass
class SelectionDecision:
    trader_id: str
    decision: str  # ADD | KEEP | REMOVE_INVALIDATED | REMOVE_WIND_DOWN | REJECT | NOT_SELECTED
    reasons: list[str]
    score: Decimal


@dataclass
class UniverseStats:
    traders: int
    inactive: int
    survivorship_warning: Optional[str]
    mean_annual_active: Optional[Decimal]
    mean_annual_inactive: Optional[Decimal]


def _q(x: float) -> Decimal:
    return Decimal(str(round(x, 6)))


def _concentration(record: TraderRecord, criteria: SelectionCriteria):
    top3: Optional[Decimal] = None
    gains = sorted((p for p in record.closed_trade_pnls if p > 0), reverse=True)
    if gains:
        top3 = (sum(gains[:3], Decimal("0")) / sum(gains, Decimal("0"))).quantize(Decimal("0.0001"))
    max_sym = max(record.symbol_share.values()) if record.symbol_share else None
    liquid = (
        sum((v for s, v in record.symbol_share.items() if s in criteria.liquid_symbols), Decimal("0"))
        if record.symbol_share else None
    )
    return top3, max_sym, liquid


def _metrics_from_reported(record: TraderRecord, criteria: SelectionCriteria) -> TraderMetrics:
    """App figures only: the longest reported ROI window within the lead period sets the
    return, the reported MDD the drawdown, and the share of positive windows stands in
    for consistency. Coarser than a daily series; reports say so (basis)."""
    rep = record.reported
    assert rep is not None
    share = float(record.profit_share_pct) / 100
    windows = {d: float(v) / 100 for d, v in rep.roi_pct_by_days.items() if d <= rep.lead_days}
    if windows:
        w = max(windows)
        gross = windows[w]
        net = gross * (1 - share) if gross > 0 else gross
        annual = (1 + net) ** (365 / w) - 1 if net > -1 else -1.0
    else:
        annual = -1.0
    n = rep.lead_days
    shrunk = annual * n / (n + criteria.shrinkage_prior_days) if n else 0.0
    positives = [v for v in windows.values() if v > 0]
    consistency = len(positives) / len(windows) if windows else 0.0
    worst = windows.get(30, min(windows.values(), default=0.0))
    max_dd = float(rep.max_drawdown_pct) / 100
    top3, max_sym, liquid = _concentration(record, criteria)
    dd = max(Decimal(str(max_dd)), criteria.drawdown_floor)
    return TraderMetrics(
        history_days=n, trades=rep.trades,
        total_net_return=_q(net if windows else -1.0), annual_net_return=_q(annual), shrunk_annual_return=_q(shrunk),
        max_drawdown=_q(max_dd), consistency=_q(consistency), worst_30d=_q(worst),
        top3_trade_share=top3, max_symbol_share=max_sym, liquid_share=liquid,
        score=(_q(shrunk) / dd).quantize(Decimal("0.0001")), basis="reported_windows",
    )


def compute_metrics(record: TraderRecord, criteria: SelectionCriteria) -> TraderMetrics:
    if not record.daily_returns and record.reported is not None:
        return _metrics_from_reported(record, criteria)
    share = float(record.profit_share_pct) / 100
    # Copy traders pay the leader a share of profits; approximated per day on gains.
    net = [float(r) if r <= 0 else float(r) * (1 - share) for r in record.daily_returns]
    equity, peak, max_dd = 1.0, 1.0, 0.0
    curve = []
    for r in net:
        equity *= 1 + r
        curve.append(equity)
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak if peak > 0 else 1.0)
    n = len(net)
    total = curve[-1] - 1 if curve else 0.0
    annual = (1 + total) ** (365 / n) - 1 if n and total > -1 else -1.0
    shrunk = annual * n / (n + criteria.shrinkage_prior_days) if n else 0.0
    blocks = [net[i:i + 30] for i in range(0, n - n % 30, 30)]
    block_returns = [math.prod(1 + r for r in b) - 1 for b in blocks]
    consistency = sum(1 for b in block_returns if b > 0) / len(block_returns) if block_returns else 0.0
    worst_30d = min(block_returns) if block_returns else 0.0

    top3, max_sym, liquid = _concentration(record, criteria)
    dd = max(Decimal(str(max_dd)), criteria.drawdown_floor)
    return TraderMetrics(
        history_days=n, trades=len(record.closed_trade_pnls),
        total_net_return=_q(total), annual_net_return=_q(annual), shrunk_annual_return=_q(shrunk),
        max_drawdown=_q(max_dd), consistency=_q(consistency), worst_30d=_q(worst_30d),
        top3_trade_share=top3, max_symbol_share=max_sym, liquid_share=liquid,
        score=(_q(shrunk) / dd).quantize(Decimal("0.0001")),
    )


def evaluate(record: TraderRecord, criteria: SelectionCriteria) -> TraderEvaluation:
    m = compute_metrics(record, criteria)
    failed = []
    if not record.active:
        failed.append(INACTIVE)
    if record.market not in criteria.allowed_markets:
        failed.append(MARKET_NOT_ALLOWED)
    if m.history_days < criteria.min_history_days:
        failed.append(HISTORY_TOO_SHORT)
    if m.trades < criteria.min_trades:
        failed.append(TOO_FEW_TRADES)
    if m.max_drawdown > criteria.max_drawdown:
        failed.append(DRAWDOWN_TOO_DEEP)
    if m.shrunk_annual_return <= criteria.min_shrunk_annual_return:
        failed.append(NOT_PROFITABLE_AFTER_SHRINKAGE)
    if m.consistency < criteria.min_consistency:
        failed.append(INCONSISTENT)
    # Unknown concentration/liquidity is a failure, not a pass (fail closed).
    if m.top3_trade_share is None or m.top3_trade_share > criteria.max_top3_trade_share:
        failed.append(PROFIT_CONCENTRATED_IN_FEW_TRADES)
    if m.max_symbol_share is None or m.max_symbol_share > criteria.max_symbol_share:
        failed.append(SYMBOL_CONCENTRATED)
    if m.liquid_share is None or m.liquid_share < criteria.min_liquid_share:
        failed.append(ILLIQUID_SYMBOLS)
    if record.max_leverage > criteria.max_leverage:
        failed.append(LEVERAGE_TOO_HIGH)
    return TraderEvaluation(record.trader_id, record.name, record.active, m, failed)


def universe_stats(evaluations: list[TraderEvaluation]) -> UniverseStats:
    active = [e.metrics.annual_net_return for e in evaluations if e.active]
    inactive = [e.metrics.annual_net_return for e in evaluations if not e.active]

    def mean(xs: list[Decimal]) -> Optional[Decimal]:
        return (sum(xs, Decimal("0")) / len(xs)).quantize(Decimal("0.0001")) if xs else None

    warning = None
    if evaluations and not inactive:
        warning = ("the snapshot lists no trader that stopped leading: it only shows survivors, so "
                   "every return in it overstates what following a random leader earns")
    return UniverseStats(len(evaluations), len(inactive), warning, mean(active), mean(inactive))


def select(
    evaluations: list[TraderEvaluation], criteria: SelectionCriteria, incumbents: frozenset[str] = frozenset(),
) -> list[SelectionDecision]:
    by_id = {e.trader_id: e for e in evaluations}
    decisions: dict[str, SelectionDecision] = {}
    kept: list[TraderEvaluation] = []
    for tid in sorted(incumbents):
        ev = by_id.get(tid)
        if ev is None:
            decisions[tid] = SelectionDecision(tid, "REMOVE_INVALIDATED", ["MISSING_FROM_SNAPSHOT"], Decimal("0"))
        elif not ev.eligible:
            kind = "REMOVE_INVALIDATED" if INVALIDATING_REASONS & set(ev.failed) else "REMOVE_WIND_DOWN"
            decisions[tid] = SelectionDecision(tid, kind, list(ev.failed), ev.metrics.score)
        else:
            kept.append(ev)
    kept.sort(key=lambda e: e.metrics.score, reverse=True)
    while len(kept) > criteria.max_selected:  # the cap was lowered
        dropped = kept.pop()
        decisions[dropped.trader_id] = SelectionDecision(
            dropped.trader_id, "REMOVE_WIND_DOWN", ["OVER_MAX_SELECTED"], dropped.metrics.score)

    newcomers = sorted(
        (e for e in evaluations if e.eligible and e.trader_id not in incumbents),
        key=lambda e: e.metrics.score, reverse=True,
    )
    for ev in newcomers:
        if len(kept) < criteria.max_selected:
            kept.append(ev)
            decisions[ev.trader_id] = SelectionDecision(ev.trader_id, "ADD", ["ELIGIBLE", "SLOT_FREE"], ev.metrics.score)
            continue
        weakest = min((k for k in kept if k.trader_id in incumbents), key=lambda k: k.metrics.score, default=None)
        if weakest is not None and ev.metrics.score > weakest.metrics.score * criteria.displace_ratio:
            kept.remove(weakest)
            decisions[weakest.trader_id] = SelectionDecision(
                weakest.trader_id, "REMOVE_WIND_DOWN", [f"DISPLACED_BY:{ev.trader_id}"], weakest.metrics.score)
            kept.append(ev)
            decisions[ev.trader_id] = SelectionDecision(
                ev.trader_id, "ADD", ["ELIGIBLE", f"DISPLACES:{weakest.trader_id}"], ev.metrics.score)
        else:
            decisions[ev.trader_id] = SelectionDecision(
                ev.trader_id, "NOT_SELECTED", ["ELIGIBLE", "NO_SLOT_OR_NOT_MATERIALLY_BETTER"], ev.metrics.score)
    for ev in kept:
        decisions.setdefault(ev.trader_id, SelectionDecision(ev.trader_id, "KEEP", ["STILL_ELIGIBLE"], ev.metrics.score))
    for ev in evaluations:
        decisions.setdefault(ev.trader_id, SelectionDecision(ev.trader_id, "REJECT", list(ev.failed), ev.metrics.score))
    return [decisions[k] for k in sorted(decisions)]


def selected_ids(decisions: list[SelectionDecision]) -> frozenset[str]:
    return frozenset(d.trader_id for d in decisions if d.decision in ("ADD", "KEEP"))


def metrics_dict(m: TraderMetrics) -> dict:
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in asdict(m).items()}
