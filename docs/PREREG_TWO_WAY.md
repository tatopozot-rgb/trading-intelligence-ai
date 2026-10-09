# Pre-registration: two-way (long and short) time-series momentum, research only

Registered 2026-10-09 by the Quant/Strategy session at the leader's request (owner: a logic
for USDⓈ-M futures that pays over weeks, buying or selling), **before any result of this
study was computed or seen**. Research only: public data, no key, no orders.
`trading_intelligence/live/` and `config/live_limits.json` are not touched.

- Code: `trading_intelligence/backtesting/two_way_momentum.py`
- Workflow: `.github/workflows/two-way-momentum.yml`

This file is frozen once committed. A later change is a new pre-registration.

## Strategy family (primary, one only): time-series momentum (TSMOM)

**Why this one, not the Donchian breakout.** Sections 45 and 61 tested an EMA-cross trend
rule with a swing stop. Its short side lost, apparently by entering late and being stopped
by sharp bounces. A Donchian breakout with an ATR stop is the same family: a discrete entry
on a price event, with a tight protective stop. TSMOM is structurally different:
- It always holds a position (long or short) sized by volatility.
- It has no stop, so a bounce does not exit it.
- It decides on a horizon of weeks, which is what the owner asked for.

Its evidence base is also broader:
- Moskowitz, Ooi and Pedersen (2012, *Journal of Financial Economics*): TSMOM across 58
  futures markets, with the volatility-scaling convention used here.
- Liu and Tsyvinski (2021, *Review of Financial Studies*): time-series momentum in
  cryptocurrency returns at 1–4 week horizons.

**Parameters, fixed from convention, not from data:**

| Parameter | Value | Source |
|---|---|---|
| Signal | sign of the past **28-day** close-to-close return (+ → long, − → short, 0 → flat) | 4-week horizon (Liu & Tsyvinski) |
| Rebalance | **weekly**: decision on the daily close of each Sunday (bar ending Monday 00:00 UTC), executed at the next daily open (Monday 00:00 UTC) | weeks-horizon request; next-bar execution as `BacktestEngine` |
| Volatility estimate | standard deviation of the past **60** daily log returns × √365 | MOP use a ~60-day center of mass |
| Size per symbol | notional = L × (equity / N) × min(1, **40%** / σ) | MOP 40% annualized per-asset target, capped at 1× the symbol's allocation |
| Leverage L | **1 (primary)**; 2 and 3 as sensitivity only | owner's futures plan: 1× |

- **N** is the number of symbols with enough history (at least 61 daily closes) at that
  rebalance.
- Within the week, quantities are held fixed; there is no stop.
- The universe is equal-weight, with no cross-sectional ranking.

## Costs (fixed)

- Fee 0.05% per side plus 5 bps slippage. Together that is 0.10% of each traded notional,
  charged on |Δquantity| × execution price at every rebalance, including opening and
  closing.
- **Funding:**
  - Real historical USDⓈ-M funding rates, from `fapi.binance.com/fapi/v1/fundingRate` or
    from the monthly files at `data.binance.vision/data/futures/um/monthly/fundingRate/`.
  - Sign: with a positive rate, longs pay and shorts receive (notional × rate at each
    funding time).
  - Fallback, for any symbol or period without real rates (including before a perpetual
    existed): 0.01% per 8h charged to **both** longs and shorts.
  - Which source applied is reported per symbol.
- **Prices:** Binance **spot** daily klines (data-api.binance.vision) are the price proxy
  for the perpetual. The basis is not modelled; this is disclosed.

## Data

- **Primary:** daily bars **2019-01-01 → 2022-10-01**, a period not used by sections 45 or 61.
- **Symbols:** the 12 in `config/live_limits.json` plus PAXGUSDT, each from its first
  available daily bar. Symbols listed later (SOL, AVAX, DOT, PAXG, …) simply join when they
  have 61 closes.
- **Secondary:** 2022-10-01 → 2026-10-01 is also reported. It is labeled **already seen**
  (sections 45/61 used it) and decides nothing.

## Evaluation (fixed)

- The primary period is split into **5 equal calendar folds** (by rebalance weeks). Each
  fold starts with a fresh 10,000 of equity. Indicators use all earlier data, which is
  allowed because nothing is fitted.
- There is no IS/OOS split, because no parameter is estimated. The whole primary period is
  out of sample for the parameter choice.
- Equity is marked daily at the close; intraday extremes are not modelled, which is
  disclosed. If equity reaches ≤ 0, the fold is ruined and equity stays at 0.
- **Unit of evidence:** the portfolio's net weekly return. The t-test is two-sided against 0.
  Weekly portfolio returns are used rather than per-symbol trades because symbols move
  together; pooling symbol-weeks would overstate significance. Symbol-week statistics are
  still reported.

**Verdict at L = 1 (primary period), applied in this order:**
1. **NO-GO** if weeks ≥ 30 and (mean weekly return ≤ 0 or profit factor < 1.0).
2. **GO** if weeks ≥ 30, profit factor ≥ 1.3, mean > 0, p < 0.05, **and** at least 3 of 5
   folds end with positive return.
3. **INCONCLUSIVE** otherwise.

Profit factor = sum of positive weekly P&L / |sum of negative weekly P&L|, across folds.

## Reported

- For L = 1, 2 and 3:
  - weeks, mean and median weekly return, profit factor, p;
  - folds positive;
  - worst fold max drawdown;
  - share of folds whose drawdown reached **−20%, −35% (the owner's standard limit) and
    −50%**;
  - ruined folds.
- **Long and short separately:** the weekly P&L contributed by long positions and by short
  positions (each / equity at the start of the week), with mean, profit factor and p.
- Per symbol: symbol-weeks, mean return on the symbol's allocation, and funding source.
- Per fold: return and drawdown.
- Benchmark: equal-weight buy-and-hold of the same symbols over the same weeks, at the same
  rebalance and costs, with no funding.

## Forward-PAPER plan (fixed now, used only if GO)

1. **No real money before 12 weeks of forward PAPER** on live data. Signals and sizes are
   computed by this exact code on each Monday's data. Real money also needs explicit owner
   authorization (CLAUDE.md).
2. **During PAPER:**
   - Stop immediately if the paper drawdown reaches −20%: the low end of the owner's band.
   - Stop if any week's realized costs plus funding differ from the model by more than 2×.
3. **After 12 weeks, any real money starts at 1×** under `config/live_limits.json` limits.
   The 12 weeks prove the pipeline, not the edge (about 12 data points). The edge question
   is answered by the primary-period test above, and by a confirmation that accumulates
   ≥ 52 forward weeks before position size is increased.
4. If the verdict is NO-GO or INCONCLUSIVE, no PAPER deployment is proposed from this study.
