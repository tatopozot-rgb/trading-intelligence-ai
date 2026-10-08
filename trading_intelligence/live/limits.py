"""Owner-approved limits for real trading, loaded fail-closed from config/live_limits.json."""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "live_limits.json"


class LimitsNotApproved(RuntimeError):
    pass


@dataclass(frozen=True)
class OwnerLimits:
    loss_limit_pct: Decimal  # of the session capital: at this loss the session stops and closes its positions
    warn_before_usd: Decimal  # this many USD before the loss limit: new entries pause and the owner is asked
    max_position_pct: Decimal  # one position, of session equity
    max_open_positions: int
    allowed_symbols: frozenset[str]

    def loss_limit_usd(self, capital: Decimal) -> Decimal:
        return capital * self.loss_limit_pct / 100

    def warn_at_usd(self, capital: Decimal) -> Decimal:
        return max(Decimal("0"), self.loss_limit_usd(capital) - self.warn_before_usd)


def load_limits(path: Path = DEFAULT_PATH) -> OwnerLimits:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise LimitsNotApproved(f"owner limits unreadable at {path}: {error}") from None
    if data.get("approved_by_owner") is not True:
        raise LimitsNotApproved("owner limits are not approved: real trading refused")
    if data.get("market") != "SPOT" or data.get("max_leverage") != 1:
        raise LimitsNotApproved("only Spot without leverage is approved")
    if data.get("withdrawals") is not False:
        raise LimitsNotApproved("withdrawals must be false")
    try:
        limits = OwnerLimits(
            loss_limit_pct=Decimal(str(data["loss_limit_pct"])),
            warn_before_usd=Decimal(str(data["warn_before_usd"])),
            max_position_pct=Decimal(str(data["max_position_pct"])),
            max_open_positions=int(data["max_open_positions"]),
            allowed_symbols=frozenset(str(s) for s in data["allowed_symbols"]),
        )
    except (KeyError, TypeError, ValueError, ArithmeticError) as error:
        raise LimitsNotApproved(f"owner limits malformed: {error}") from None
    if not (0 < limits.loss_limit_pct <= 100 and 0 < limits.max_position_pct <= 100):
        raise LimitsNotApproved("loss_limit_pct and max_position_pct must be in (0, 100]")
    if limits.warn_before_usd < 0 or limits.max_open_positions < 1 or not limits.allowed_symbols:
        raise LimitsNotApproved("warn_before_usd >= 0, max_open_positions >= 1 and a symbol list are required")
    return limits
