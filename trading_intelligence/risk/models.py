"""Risk engine configuration and state models. Per docs/RISK_ENGINE_SPEC.md."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Optional


@dataclass
class RiskConfig:
    """
    Risk parameters. All validated at construction — invalid config refuses to run.
    Defaults mirror docs/RISK_ENGINE_SPEC.md.
    """

    max_risk_per_trade_pct: float = 1.0
    max_position_size_pct: float = 5.0
    daily_loss_limit_pct: float = 2.0
    max_trades_per_day: int = 20
    max_daily_turnover_pct: float = 30.0
    drawdown_pause_pct: float = 8.0
    drawdown_halt_pct: float = 15.0
    drawdown_lookback_days: int = 30
    max_open_positions: int = 5
    max_correlated_exposure_pct: float = 10.0
    max_total_exposure_pct: float = 20.0
    default_slippage_bps: float = 5.0
    include_fees_in_risk_calc: bool = True
    kill_switch_active: bool = False
    taker_fee_rate: float = 0.001

    # Not in the original spec's yaml block — required to implement the
    # STOP_TOO_TIGHT check (spec step 5) but no numeric default was given there.
    min_stop_distance_pct: float = 0.1

    # Connectivity watchdog — auto kill switch per spec "Kill Switch" section.
    max_connectivity_gap_seconds: float = 60.0

    # A MARKET entry is approved on one bar and fills at the next bar's open.
    # The fill is vetoed if, at the actual fill price, the loss at the approved
    # stop would exceed the per-trade risk budget by more than this percentage
    # (normal slippage and small inter-bar moves pass; a gap that multiplies
    # the risk does not). Not in the original spec — added when GPT Work's
    # review showed a +50% gap turning a 1% risk into ~10%. 0 = no tolerance.
    max_fill_risk_overshoot_pct: float = 25.0

    # How open positions count toward the total / correlated exposure caps.
    # "entry" (default, the spec's behaviour): the notional at entry, forever.
    # "entry_or_market": the HIGHER of entry notional and current market value, so
    # a position that has run up counts for what it is now worth while one that
    # has fallen is never discounted below what was committed. Opt-in: the
    # survival bench showed real exposure drifting to 30-55% against a 20% cap
    # under "entry"; whether to change the policy is the owner's call.
    exposure_basis: str = "entry"

    # What to do when the risk-sized position exceeds max_position_size_pct. False (default, the
    # original behaviour): reject the entry. True: shrink it to the cap minus cap_headroom_pct, so
    # the next-open fill check (FILL_EXCEEDS_POSITION_CAP) still has room for normal slippage. A
    # smaller position at the same stop only lowers the loss at the stop, never raises it. Opt-in:
    # the live operator enables it because 1m-5m stops are tight and every entry was rejected.
    cap_position_size: bool = False
    cap_headroom_pct: float = 2.0

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        checks = [
            (0 < self.max_risk_per_trade_pct <= 100, "max_risk_per_trade_pct must be in (0, 100]"),
            (0 < self.max_position_size_pct <= 100, "max_position_size_pct must be in (0, 100]"),
            (0 < self.daily_loss_limit_pct <= 100, "daily_loss_limit_pct must be in (0, 100]"),
            (self.max_trades_per_day > 0, "max_trades_per_day must be > 0"),
            (0 < self.max_daily_turnover_pct <= 1000, "max_daily_turnover_pct out of range"),
            (0 < self.drawdown_pause_pct < self.drawdown_halt_pct,
             "drawdown_pause_pct must be < drawdown_halt_pct"),
            (self.drawdown_halt_pct <= 100, "drawdown_halt_pct must be <= 100"),
            (self.drawdown_lookback_days > 0, "drawdown_lookback_days must be > 0"),
            (self.max_open_positions > 0, "max_open_positions must be > 0"),
            (0 < self.max_correlated_exposure_pct <= 100, "max_correlated_exposure_pct out of range"),
            (0 < self.max_total_exposure_pct <= 100, "max_total_exposure_pct out of range"),
            (self.default_slippage_bps >= 0, "default_slippage_bps must be >= 0"),
            (0 <= self.taker_fee_rate < 1, "taker_fee_rate must be in [0, 1)"),
            (0 < self.min_stop_distance_pct, "min_stop_distance_pct must be > 0"),
            (isinstance(self.cap_position_size, bool), "cap_position_size must be a bool"),
            (0 <= self.cap_headroom_pct < 50, "cap_headroom_pct must be in [0, 50)"),
            (self.max_connectivity_gap_seconds > 0, "max_connectivity_gap_seconds must be > 0"),
            (self.max_fill_risk_overshoot_pct >= 0, "max_fill_risk_overshoot_pct must be >= 0"),
            (self.exposure_basis in ("entry", "entry_or_market"),
             "exposure_basis must be 'entry' or 'entry_or_market'"),
        ]
        for ok, message in checks:
            if not ok:
                raise ValueError(f"Invalid RiskConfig: {message}")


@dataclass
class OpenPositionInfo:
    position_id: str
    symbol: str
    notional_value: Decimal


@dataclass
class RiskState:
    """
    Mutable, persisted risk engine state. Survives restart — if kill_switch
    was True when persisted, the engine starts halted (per spec).
    """

    kill_switch: bool = False
    kill_switch_reason: str = ""

    current_day: str = ""              # ISO date (UTC), e.g. "2026-10-05"
    equity_at_day_start: str = "0"      # Decimal serialized as str
    daily_realized_pnl: str = "0"
    daily_trade_count: int = 0
    daily_turnover: str = "0"
    trading_day_halted: bool = False

    # Rolling equity history for drawdown peak: list of [iso_date, equity_str]
    equity_history: list = field(default_factory=list)
    drawdown_paused: bool = False

    last_connectivity_ok_at: Optional[str] = None  # ISO datetime

    open_positions: dict = field(default_factory=dict)  # position_id -> {symbol, notional_value}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RiskState":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(self.to_dict(), indent=2))
        tmp_path.replace(path)  # atomic on POSIX

    @classmethod
    def load(cls, path: Path) -> "RiskState":
        path = Path(path)
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        return cls.from_dict(data)
