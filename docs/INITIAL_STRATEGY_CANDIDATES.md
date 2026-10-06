---
type: spec
tags: [trading-intelligence, strategy]
status: reference
aliases: ["Initial Strategy Candidates"]
---

# Initial Strategy Candidates — Trading Intelligence AI

> Author: Trading claude work
> Last updated: 2026-10-05
> Status: CANDIDATES — None deployed. All require validation per STRATEGY_VALIDATION_FRAMEWORK.md

## Purpose

This document lists strategy candidates for initial backtesting and evaluation.
None of these are approved. All must pass the full validation framework.

**Selection criteria for candidates:**
1. Economic rationale exists (not just curve-fit to history)
2. Simple enough to implement cleanly and test correctly
3. Compatible with Binance Spot (no shorting, no leverage required)
4. Generates sufficient trade frequency for statistical validity
5. Has meaningful precedent in quantitative literature

---

## What This System is NOT Optimized For

Before listing candidates, be explicit about non-goals:

- **HFT / Market-making**: Requires colocation, sub-millisecond infrastructure. Not feasible here.
- **Pure arbitrage**: Requires multiple exchange simultaneous access and capital on both sides.
- **News-driven alpha**: Requires NLP pipeline and real-time news feeds (possible future add-on).
- **On-chain analytics**: Could be added later, not in initial scope.
- **Order flow / microstructure**: Too complex for initial implementation.

---

## Candidate 1: Dual Moving Average Crossover (Trend Following)

**Rationale**: Crypto markets have exhibited strong momentum and trend behavior. Trend following
is the oldest systematic strategy category with the most literature support. On longer timeframes,
crypto trends have been pronounced. Simple, transparent, non-anticipatory.

**Mechanism**:
- Fast MA crosses above Slow MA → BUY signal
- Fast MA crosses below Slow MA → EXIT signal (or inverse if shorting — but we're spot only)
- Spot only: only long trades (no short)

**Parameter space to test**:
- Fast MA: [5, 8, 10, 13, 20] periods
- Slow MA: [20, 34, 50, 55, 100, 200] periods
- MA type: SMA, EMA (test both)
- Timeframe: 1h, 4h, 1D

**Expected characteristics**:
- Win rate: likely 30-45% (trend followers win less often but win bigger)
- Payoff ratio: should be > 2:1 for strategy to work
- High drawdown during choppy/sideways markets (known weakness)

**Critical risks**:
- Prolonged sideways market → whipsaw losses
- In crypto bear markets on spot-only: cannot short, so long-only will lose periods of downtrend
- Need regime filter to avoid entering longs in confirmed bear market

**Regime filter requirement**: Add condition to suppress signals when price is below 200-day MA
(long-term trend filter to avoid buying into sustained downtrends)

**Statistical viability**: With daily bars on BTC from 2019-2024, likely 100+ trades per parameter set.

---

## Candidate 2: Momentum / Rate of Change (ROC)

**Rationale**: Asset price momentum — the tendency of recent winners to continue winning — is
one of the most replicated phenomena in academic finance literature. Crypto has shown strong
momentum characteristics.

**Mechanism**:
- Calculate ROC(n) = (price_now - price_n_bars_ago) / price_n_bars_ago
- Enter LONG when ROC crosses above threshold AND above zero
- Exit when ROC drops below zero or stop hit

**Parameter space**:
- ROC period: [10, 14, 20, 30, 50] bars
- Entry threshold: [0%, 1%, 2%, 5%] ROC
- Timeframe: 4h, 1D

**Expected characteristics**:
- Similar to MA crossover but more responsive
- Subject to same sideways market degradation

**Concerns**:
- At monthly/quarterly timescales: well-documented. At shorter: weaker evidence.
- Transaction costs erode edge quickly at shorter timeframes.

---

## Candidate 3: Volatility Breakout (Donchian Channel)

**Rationale**: Price breaking to new N-period highs/lows reflects genuine directional conviction
from market participants. Breakout systems have decades of evidence in futures/commodities.
Crypto shows pronounced breakout behavior, especially at ATH levels.

**Mechanism**:
- Track N-period high/low (Donchian channel)
- Enter LONG when price breaks above N-period high
- Stop loss at N/2-period low (channel midpoint)
- Exit on reverse signal or time-based exit

**Parameter space**:
- Channel period: [20, 40, 55, 80, 100, 200] bars
- Timeframe: 4h, 1D
- ATR-based stop variant (stop = entry - 2*ATR)

**Expected characteristics**:
- Low win rate (30-40%) but high payoff ratio required
- Works well in trending markets, extremely poorly in range markets

**Concerns**:
- Breakout failures ("fakeouts") are common in crypto
- Requires volume confirmation to reduce false breakouts
- Timing of entry (bar close vs first tick beyond high) matters

**Enhancement to test**: Add volume confirmation — require volume > N-period average volume at breakout bar.

---

## Candidate 4: RSI Mean Reversion (Short-Term)

**Rationale**: In range-bound markets, prices exhibit mean reversion. RSI measures
relative strength and identifies potential exhaustion points.

**Mechanism**:
- Enter LONG when RSI drops below oversold threshold (e.g. RSI < 30)
- Exit when RSI recovers above midline (e.g. RSI > 50) OR take profit at fixed level
- Stop loss at recent swing low

**Parameter space**:
- RSI period: [7, 9, 14]
- Oversold threshold: [20, 25, 30]
- Exit: RSI > 50, RSI > 60, fixed target
- Timeframe: 1h, 4h

**Expected characteristics**:
- Higher win rate (55-65%) but lower payoff ratio (targeting quick recoveries)
- Works well in ranging markets, VERY poorly in strong trends

**Critical risk**:
- In trending market, RSI stays oversold for extended periods while price falls further
- Must have regime filter: RSI mean reversion only in defined range-bound periods
- Oversold in a bear market trend is a VALUE TRAP — price can stay "oversold" for months

**Regime filter requirement**: Only trade this when price is between 20-day MA and 200-day MA
(rough proxy for range-bound behavior).

**Assessment**: This strategy has high failure risk in crypto's trending nature. Test it but
be prepared for the regime filter to eliminate most of its trades.

---

## Candidate 5: Trend + Momentum Combination

**Rationale**: Combining trend filter (MA) with momentum entry (RSI or ROC) attempts to
take long positions only when the trend is up AND momentum is accelerating. Reduces some
of the false signal problem.

**Mechanism**:
- **Long-term trend filter**: Price above 200-day EMA (or 50-day for shorter timeframe)
- **Momentum entry**: RSI crosses above 50 from below, OR ROC turns positive
- **Stop**: ATR-based (entry - 2 × ATR(14))
- **Target**: Risk multiple (e.g. 2R or 3R)

**Parameter space**:
- Trend MA: [50, 100, 200] bars
- Entry: RSI(14) cross 50, or ROC(10) > 0
- Risk multiple: [2R, 3R, 4R]
- Timeframe: 1h, 4h, 1D

**Expected characteristics**:
- More selective than pure crossover (fewer trades)
- Higher quality setups in theory
- Needs more data for statistical significance due to fewer trades

---

## Priority Order for Testing

```
Priority 1 (test first):
  Dual MA Crossover — simplest, most robust precedent, easy to test correctly

Priority 2:
  Volatility Breakout (Donchian) — well-established methodology

Priority 3:
  Trend + Momentum Combination — building on Priority 1 results

Priority 4:
  RSI Mean Reversion — risky in crypto context, test with skepticism

Priority 5:
  Momentum/ROC — test after MA crossover for comparison
```

---

## Strategies Deliberately NOT Included (and Why)

| Strategy | Reason Excluded |
|----------|----------------|
| Arbitrage | Requires multi-exchange simultaneous execution, significant infrastructure |
| Grid trading | Risk of capital lock-up, complex risk accounting |
| Martingale | Explicitly prohibited |
| AI/ML signal (standalone) | Overfitting risk without extensive validation; add only after baseline works |
| News sentiment | Requires NLP pipeline not yet built |
| On-chain metrics | Requires additional data sources not yet integrated |
| Options strategies | Binance Spot scope |
| Statistical arbitrage | Requires correlated pairs, more complex risk model |

---

## Next Steps When Codebase Arrives

1. Confirm data pipeline can produce clean OHLCV data for backtesting
2. Start with Priority 1 (Dual MA Crossover) as baseline
3. Run full backtest per STRATEGY_VALIDATION_FRAMEWORK.md
4. Only proceed to Priority 2 after Priority 1 is fully analyzed
5. Don't test all strategies simultaneously — depth > breadth
