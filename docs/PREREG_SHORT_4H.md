# Pre-registration: short side of the 4h trend logic (real data, research only)

Registered 2026-10-09 by the Quant/Strategy session, at the leader's request, **before
any short-side result was computed or seen**. Research only: public klines, no key, no
orders. `trading_intelligence/live/` and `config/live_limits.json` are not touched. Code:
`trading_intelligence/backtesting/short_side_validation.py`. Workflow:
`.github/workflows/short-side-walk-forward.yml`.

This document is frozen once committed. A later change is a new pre-registration.

## Question

Can the existing 4h trend logic make money in downtrends when it shorts them, after
futures-like costs? Does adding the short side improve on long-only 4h?

## Strategy (mirror of `tendencia` at 4h, no new parameters)

The long side is `default_router(symbol, "4h")`: `DualMACrossover` with EMA 20/50, no
trend filter, and a swing-low stop over the last 10 bars. It is routed for TREND_UP
(confidence ≥ 0.5) and BREAKOUT_UP (≥ 0.0). The short side mirrors it:

| | Long (existing) | Short (mirror) |
|---|---|---|
| Regime (router) | TREND_UP ≥ 0.5, BREAKOUT_UP ≥ 0.0 | TREND_DOWN ≥ 0.5, BREAKOUT_DOWN ≥ 0.0 |
| Entry signal | EMA20 crosses above EMA50 on the bar's close | EMA20 crosses below EMA50 on the bar's close |
| Protective stop | lowest low of the previous 10 bars (below entry) | highest high of the previous 10 bars (above entry) |
| Exit signal | EMA20 crosses below EMA50 | EMA20 crosses above EMA50 |

**Deviation from the leader's wording, decided now:** the leader asked for an "ATR stop
above entry". The long side does not use an ATR stop; it uses a 10-bar swing stop. The
same message asks to mirror the long side's exits without adding parameters. The swing-high
stop is the exact mirror. An ATR multiple would add a parameter that nothing here has
validated. So the swing-high stop is registered.

## Execution and costs (fixed)

- Same execution model as `BacktestEngine`:
  - The signal fires on the bar's close; the fill comes at the next bar's open ± 5 bps
    slippage.
  - Stops are checked first on each bar. A gap-through fills at the open with 1×
    slippage; a touch fills at the stop with 2× slippage, in the adverse direction for
    the side.
  - Each decision sees the trailing 500 bars.
  - Size risks 1% of equity per trade (10,000 start), with notional capped at equity
    (no leverage).
  - A trade still open at the end of a window is closed at the last close. That is what
    `BacktestEngine` does and what section 45 counted.
- **Futures-like costs:**
  - Taker fee **0.05% per side**.
  - Slippage 5 bps (as section 45).
  - **Funding 0.01% of entry notional charged to shorts at every 00:00/08:00/16:00 UTC
    timestamp t with entry < t ≤ exit.** Longs pay no funding. That is conservative for
    shorts only.
- One position per symbol at a time. In `long+short` mode, the regime decides the
  direction; the regimes are mutually exclusive.

## Data

- 4h public Binance klines, **2022-10-01 → 2026-10-01**: the same period and
  impossible-bar guard as section 45.
- Symbols: the 12 in `config/live_limits.json` on 2026-10-09, plus **PAXGUSDT** when its
  klines cover the period. A symbol whose first bar is more than one day after
  2022-10-01 is excluded and reported, never padded.
- Disclosure: section 45 already used this period for the long side. The short side has
  never been run on it, and nothing in the short rule was chosen by looking at it.

## Walk-forward (as section 45)

- Per symbol, IS = first 50%. Then five consecutive non-overlapping 10% OOS windows, each
  simulated cold (fresh 10,000).
- Results pool every OOS trade of every symbol.
- No IS gate is applied. Section 45 showed that the framework's per-symbol criterion
  (≥ 30 OOS trades per fold) is structurally unreachable at this sample size, so it is
  reported for reference only and is **not** part of the verdict.

## Verdict (applied separately to `short` and to `long+short`, in this order)

Pooled OOS trades, two-sided one-sample t-test of net return per trade against 0:

1. **NO-GO** if trades ≥ 30 and (mean ≤ 0 or profit factor < 1.0).
2. **GO** if trades ≥ 30, profit factor ≥ 1.3, mean > 0 and p < 0.05.
3. **INCONCLUSIVE** otherwise (positive but not significant, or too few trades).

`long-only` under the same futures costs is computed in the same run as the baseline.
**The short side adds value** only if `short` is GO. "`long+short` beats `long-only` on
total OOS P&L" is reported but decides nothing, because it can come from luck in one
period. No parameter, stop, cost or period is changed after seeing results.

## Reported

For each mode (`long`, `short`, `long+short`):
- trades, win rate, mean / median net return per trade, profit factor and p;
- worst OOS-fold max drawdown;
- total OOS P&L and funding paid;
- per symbol: trades and mean;
- per fold: trades and mean.
