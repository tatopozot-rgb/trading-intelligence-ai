---
type: spec
tags: [trading-intelligence, strategy, validation]
status: reference
aliases: ["Strategy Validation Framework"]
---

# Strategy Validation Framework — Trading Intelligence AI

> Author: Trading claude work
> Last updated: 2026-10-05
> Status: CANONICAL — applies to all strategies before live/paper deployment

## Purpose

No strategy goes into even PAPER trading without passing this framework.
The default position is: **the strategy does not work** until proven otherwise with evidence.

"It looks good on a chart" is not evidence.
"It worked last year" is not sufficient.
"The logic makes sense" is not evidence.

---

## Stage 0: Pre-Validation Checklist

Before running any backtest, answer these questions. Fail any → do not backtest yet.

| Question | Why It Matters |
|----------|---------------|
| Is the entry signal defined precisely enough to code deterministically? | Ambiguous signals produce spurious results |
| Is the exit signal (stop, target, time) defined completely? | Partial exits lead to survivorship bias |
| Is there a plausible economic rationale for the edge? | Pure curve-fitting without rationale is fragile |
| What market conditions is this strategy designed for? | Know regime applicability upfront |
| What is the minimum holding period? | Determines minimum data granularity needed |
| What assets does it apply to? | Avoids testing on assets that don't match the theory |

---

## Stage 1: Data Requirements

### Minimum Sample Size
- **Minimum 30 completed trades** in the test period for any statistical validity.
- **Preferred: 100+ trades** for meaningful metrics.
- **Minimum 2 full years** of data (to include different market regimes).
- **Minimum 4 years** preferred for crypto (to include at least one full bull/bear cycle).

### Data Quality Checks (Mandatory)
```
1. Check for gaps > 1 trading hour in minute data → mark as suspect
2. Check for zero-volume candles at unusual times → possible bad data
3. Check for price spikes > 3x average range → flag for review, do not auto-remove
4. Verify data source aligns with the exchange being targeted (Binance Spot, not FTX historical)
5. Check timestamps are UTC and consistent
6. Verify OHLCV consistency: H >= O, H >= C, L <= O, L <= C, H >= L
```

### Look-Ahead Bias Prevention
- All signals computed using data available at bar CLOSE, not at next bar open.
- Entry executed at NEXT bar open (not signal bar close).
- No use of future data in any indicator calculation.
- Indicators that require "current bar" close are evaluated at confirmed close only.

---

## Stage 2: Backtest Methodology

### Execution Model (Realistic)
```
Fills:
- Market orders: fill at next bar OPEN ± slippage
- Limit orders: fill only if price reaches limit (conservative: require bar to touch, not just equal)
- Slippage: default 5 basis points each way (configurable per asset/timeframe)

Fees (Binance Spot, as of knowledge cutoff):
- Taker: 0.1% (0.001) — market orders, most entries
- Maker: 0.1% (0.001) — limit orders (same unless BNB discount applied)
- Apply both entry and exit fees to every trade

Minimum trade size: enforce Binance minimums
```

### What Must Be Included
- Fees on every trade (entry + exit)
- Slippage on every trade
- Realistic position sizing (fixed fractional, not fixed lots)
- Correct handling of compounding (sizing off current equity, not starting equity)

### What Must NOT Be Done
- No curve-fitting parameters to maximize Sharpe/returns post-hoc
- No cherry-picking the best time period
- No excluding "outlier" trades (unless documented with pre-defined rule)
- No using the full dataset to tune then testing on the same dataset

---

## Stage 3: In-Sample / Out-of-Sample Split

### Methodology: Walk-Forward Analysis

**Not acceptable**: train on 80% of data, test on 20% — this is a single OOS test.
**Required**: rolling or anchored walk-forward.

```
Anchored Walk-Forward (preferred for shorter histories):
- IS period: months 1–18
- OOS period: months 19–24 → record metrics
- IS period: months 1–24
- OOS period: months 25–30 → record metrics
- Continue until end of data

Rolling Walk-Forward (preferred for longer histories):
- IS window: 12 months
- OOS window: 3 months
- Step: 3 months
- Continue until end of data
```

**OOS performance must be within acceptable range of IS performance.**
OOS significantly better than IS = likely overfitting (variance artifact).
OOS significantly worse than IS = likely overfitting to past regime.

**Acceptable degradation: OOS Sharpe ≥ 60% of IS Sharpe (guideline, not hard rule)**

---

## Stage 4: Performance Metrics

### Mandatory Metrics

```
Return Metrics:
- Total return (%)
- CAGR (compound annual growth rate)
- Monthly return distribution (mean, std, skew)

Risk Metrics:
- Maximum drawdown (%)
- Average drawdown duration (days)
- Maximum consecutive losing trades
- Daily VaR 95% (historical)

Risk-Adjusted Metrics:
- Sharpe Ratio (annualized, 0% risk-free rate for crypto — no risk-free asset)
- Sortino Ratio (downside deviation only — preferred for non-normal distributions)
- Calmar Ratio (CAGR / MaxDrawdown) — indicates recovery efficiency

Trade Quality Metrics:
- Win Rate (%)
- Average Win / Average Loss (Payoff Ratio)
- Profit Factor (gross profit / gross loss)
- Expectancy per trade (average $ profit per trade, fee-adjusted)
- Average holding period

Execution Metrics:
- Total number of trades
- Turnover (% of equity turned over per day/month)
- Total fees paid
- Average slippage cost per trade

Robustness Metrics:
- Parameter sensitivity (see Stage 5)
```

### Interpretation Guidelines

| Metric | Minimum Acceptable | Good | Note |
|--------|-------------------|------|------|
| Profit Factor | > 1.3 | > 1.5 | After fees |
| Win Rate | Context-dependent | — | Must match payoff ratio |
| Expectancy | > 0 (after fees) | > $X per trade | Fees must be included |
| Max Drawdown | < 20% | < 10% | PAPER max, adjust for live |
| Sharpe (OOS) | > 0.5 | > 1.0 | Annualized |
| Sortino | > 0.8 | > 1.5 | Annualized |
| Min Trades | 30 | 100+ | Total in test period |

**Important**: a strategy with 55% win rate and 1:1 payoff has 10% edge before fees. With 0.2% round-trip fees, it needs >20 basis points edge per trade just to break even on fees. Calculate break-even frequency for the asset.

---

## Stage 5: Robustness & Sensitivity Analysis

### Parameter Sensitivity (Mandatory)

For every tunable parameter:
1. Test ±20% and ±50% from chosen value
2. Plot performance metric vs parameter value
3. **Accept only if performance degrades gracefully (not cliff-edge)**

```
Example for a 20-period moving average:
Test: [10, 14, 16, 18, 20, 22, 24, 26, 30]
Result must show smooth degradation, not:
- massive cliff at exactly 20 → overfit
- random performance → no real signal
```

If performance is hypersensitive to parameter values: **reject the strategy**.

### Monte Carlo Simulation
Run 1000+ Monte Carlo simulations shuffling trade order (not returns):
- Report P5, P25, P50, P75, P95 outcomes
- Report % of simulations with max drawdown > halt threshold
- Report % of simulations with negative total return

### Regime Analysis
Test separately on:
- Bull market periods (trending up)
- Bear market periods (trending down)
- Sideways/consolidation periods
- High volatility periods (VIX analog: BTC realized vol > 80% annualized)
- Low volatility periods

**A strategy that only works in one regime must be labeled as such.**
It must have an explicit regime filter or be inactive outside its regime.

---

## Stage 6: Bias Checklist

Run through these explicitly before declaring a strategy validated.

| Bias | Check | How to Detect |
|------|-------|--------------|
| Look-ahead bias | All signals use only past data | Code review: trace every data access |
| Survivorship bias | Historical data includes all assets, not just survivors | Check data source |
| Overfitting | OOS performance >> IS performance | Walk-forward analysis |
| Data snooping | Strategy not modified after seeing test results | Commit timestamp discipline |
| Selection bias | Not only testing assets that are obvious winners | Define universe before testing |
| Transaction cost underestimation | All fees and slippage included | Verify fee model |
| Sample size bias | Sufficient trades for statistical validity | N ≥ 30 minimum |
| Regime selection bias | Not only testing in favorable regime | Multi-regime analysis |
| Compounding error | Using fixed size instead of dynamic | Verify position sizing code |
| Time-of-day bias | Crypto patterns differ at different hours | Test across all hours or acknowledge |

---

## Stage 7: Statistical Significance

For win rate claims:
```
Null hypothesis: strategy has 50% win rate (coin flip)
Required: p-value < 0.05 to reject null

Minimum trades for 55% win rate to be significant at p<0.05: ~400 trades
Minimum trades for 60% win rate to be significant at p<0.05: ~97 trades
Minimum trades for 65% win rate to be significant at p<0.05: ~43 trades

Use: scipy.stats.binom_test(wins, n=total_trades, p=0.5, alternative='greater')
```

For return claims:
```
t-test on daily/trade returns:
t = mean_return / (std_return / sqrt(n))
p-value from t-distribution
Claim significant only if p < 0.05
```

**A strategy with 52% win rate and 200 trades is NOT statistically significant.**
Do not deploy it — gather more data or abandon.

---

## Stage 8: Go/No-Go Decision Matrix

A strategy gets a GO only if ALL of the following are true:

| Criterion | Requirement | Verified? |
|-----------|-------------|-----------|
| Economic rationale | Documented and plausible | — |
| Data quality | Passes all quality checks | — |
| Sample size | ≥ 30 OOS trades (≥ 100 preferred) | — |
| No look-ahead bias | Code review confirms | — |
| OOS Sharpe | ≥ 0.5 annualized | — |
| Profit factor (OOS) | ≥ 1.3 after all fees | — |
| Max drawdown (OOS) | Within acceptable range | — |
| Expectancy | > 0 after fees | — |
| Parameter sensitivity | Graceful degradation | — |
| Regime analysis | Performance understood by regime | — |
| Statistical significance | p < 0.05 on edge claim | — |
| Bias checklist | All biases addressed | — |

Any NO = strategy is NOT deployed. Document why and what would be needed.

---

## Continuous Monitoring in Paper Trading

Once a strategy passes Stage 8 and goes to PAPER:

```
Monitor weekly:
- Actual vs expected win rate (flag if diverging > 10 percentage points)
- Actual vs expected payoff ratio
- Actual fees vs modeled fees
- Fill quality (actual fill vs signal price)
- Drawdown vs historical max drawdown

Trigger review if:
- 10 consecutive losing trades (was this in the backtest distribution?)
- Actual performance < P10 Monte Carlo outcome
- Market regime clearly changed
- Any parameter that was sensitive starts approaching cliff-edge value
```

---

## Notes for Codex

- This framework produces files: `results/backtest_{strategy}_{date}.json`
- Results are stored in structured JSON, not just a summary metric
- Every backtest run is versioned and reproducible (same data + same params = same result)
- No modifying historical backtest results — only add new runs
- Backtesting code is pure Python with no side effects outside result files
