"""
Pre-registered forward confirmation of the 4h live profiles (research only).

Registered in docs/PREREG_4H_FORWARD.md on 2026-10-08, before any bar after
2026-10-01 was looked at. Every rule below is fixed there; this module only
implements it. Changing a constant here after that commit voids the test.

  * Data: 4h public Binance klines from FORWARD_START (inclusive) to the look
    date (exclusive), for the SYMBOLS fixed below. No bar before FORWARD_START
    is used, not even as warm-up: each symbol's engine starts cold, exactly as
    every OOS window in section 45 did.
  * Engine: BacktestEngine, trailing 500-bar window, 0.1% fee per side, 5 bps
    slippage. Only closed trades count (same rule as section 45).
  * Looks (cumulative from FORWARD_START): a futility look that can only
    REFUTE, then two looks that can declare GO at p < ALPHA each (Bonferroni
    over the two GO looks, so the overall false-GO rate stays <= 0.05).
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from multiprocessing import Pool
from pathlib import Path
from typing import Optional

import pandas as pd
from scipy import stats

from trading_intelligence.backtesting import real_data_validation as rdv
from trading_intelligence.backtesting.backtest_engine import BacktestEngine

TIMEFRAME = "4h"
FORWARD_START = "2026-10-01"
# The 12 symbols of config/live_limits.json on 2026-10-08, frozen here so a later
# edit of that file cannot change what this test measures.
SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
           "ADAUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT", "TRXUSDT", "DOTUSDT")
PRIMARY = "tendencia"
SECONDARY = "tendencia_rango"
# look date -> may this look declare GO?
LOOKS = {"2027-04-01": False, "2027-10-01": True, "2028-10-01": True}
FINAL_LOOK = "2028-10-01"
ALPHA = 0.025
MIN_TRADES = 30
MIN_PROFIT_FACTOR = 1.3


def forward_symbol(symbol: str, data: pd.DataFrame, profile: str) -> dict:
    result = BacktestEngine(router=rdv.profile_router(profile, symbol, TIMEFRAME),
                            history_bars=rdv.HISTORY_BARS).run(data)
    trades = [t for t in result.trades if t.exit_price is not None]
    return {
        "symbol": symbol,
        "bars": len(data),
        "first_bar": str(data.index[0]) if len(data) else None,
        "last_bar": str(data.index[-1]) if len(data) else None,
        "gaps": rdv.count_gaps(data, TIMEFRAME),
        "trade_returns": [t.return_pct for t in trades],
        "trade_pnls": [float(t.pnl) for t in trades],
    }


def verdict(symbols: list[dict], look: str) -> dict:
    """GO / REFUTED / INCONCLUSIVE at a registered look; NO-GO if the final look is not GO."""
    if look not in LOOKS:
        raise ValueError(f"{look} is not a registered look date: {sorted(LOOKS)}")
    returns = [r for s in symbols for r in s["trade_returns"]]
    pnls = [p for s in symbols for p in s["trade_pnls"]]
    wins, losses = sum(p for p in pnls if p > 0), abs(sum(p for p in pnls if p <= 0))
    pf = wins / losses if losses else (math.inf if wins else 0.0)
    mean = sum(returns) / len(returns) if returns else 0.0
    p = float(stats.ttest_1samp(returns, 0).pvalue) if len(returns) >= 2 else 1.0
    if math.isnan(p):
        p = 1.0
    if len(returns) >= MIN_TRADES and (mean <= 0 or pf < 1.0):
        outcome = "REFUTED"
    elif LOOKS[look] and len(returns) >= MIN_TRADES and pf >= MIN_PROFIT_FACTOR and mean > 0 and p < ALPHA:
        outcome = "GO"
    elif look == FINAL_LOOK:
        outcome = "NO-GO"
    else:
        outcome = "INCONCLUSIVE"
    return {"look": look, "outcome": outcome, "trades": len(returns), "mean_net_return_per_trade": mean,
            "profit_factor": pf, "p_value": p}


def _run(args: tuple[str, str, str]) -> dict:
    profile, symbol, look = args
    start = datetime.fromisoformat(FORWARD_START).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(look).replace(tzinfo=timezone.utc)
    return forward_symbol(symbol, rdv.fetch_klines(symbol, TIMEFRAME, start, end), profile)


def main(argv: Optional[list[str]] = None, now: Optional[datetime] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--look", choices=sorted(LOOKS), required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    now = now or datetime.now(timezone.utc)
    if now < datetime.fromisoformat(args.look).replace(tzinfo=timezone.utc):
        # No peeking: an early look is an unregistered look.
        parser.error(f"look {args.look} is in the future; the pre-registration forbids early looks")
    verdicts, symbols = {}, {}
    for profile in (PRIMARY, SECONDARY):
        with Pool(max(1, args.workers)) as pool:
            symbols[profile] = pool.map(_run, [(profile, s, args.look) for s in SYMBOLS])
        verdicts[profile] = verdict(symbols[profile], args.look)
    args.out.mkdir(parents=True, exist_ok=True)
    report = {p: {"verdict": verdicts[p], "symbols": symbols[p]} for p in verdicts}
    (args.out / f"forward_{args.look}.json").write_text(json.dumps(report, indent=1, default=str))
    for profile, v in verdicts.items():
        role = "primary" if profile == PRIMARY else "secondary"
        print(f"{profile} ({role}) @ {TIMEFRAME}, {FORWARD_START} -> {args.look}: **{v['outcome']}** — "
              f"{v['trades']} trades, mean {v['mean_net_return_per_trade']:+.3%}, "
              f"PF {v['profit_factor']:.2f}, p={v['p_value']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
