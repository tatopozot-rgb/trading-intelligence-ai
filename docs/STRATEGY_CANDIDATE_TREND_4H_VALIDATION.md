---
type: validation
tags: [trading-intelligence, strategy, validation, quant-validation]
status: final — NO-GO, synthetic-only
aliases: ["4h Trend Candidate Validation"]
---

# Strategy Candidate Validation — DualMACrossover @ 4h (`candidate_router_trend_4h`)

> Author: Quant/Validation (cloud subagent, spawned by Trading Codex)
> Date: 2026-10-06
> Verdict: **NO-GO** on synthetic data — see Stage 3-4 below. Not promoted
> to `default_router()`. No real-data trial recommended on this candidate
> as-is.

## Why this candidate exists

`default_router()`'s only wired strategy, `DualMACrossover(1d, fast=20,
slow=50)`, has a recorded **NO-GO on real BTCUSDT 2019–2026 data**
(`docs/CHECKPOINT.md` section 12): 11 completed trades, below the
30-trade Stage 1 minimum, 0 walk-forward folds with IS Sharpe ≥ 0.5. This
candidate tests one specific, falsifiable hypothesis about *why*: that
the problem is trade **frequency** (too few independent crossover
opportunities in 7 years of daily bars), not the strategy's parameters or
its underlying logic.

## Stage 0 — Pre-validation checklist

| Question | Answer |
|---|---|
| Entry/exit signal defined deterministically? | Yes — identical to `default_router()`'s `DualMACrossover`, unchanged |
| Economic rationale? | Ride an established trend until the fast/slow MA relationship reverses. This does not depend on calendar bar size — stated before any backtest number was run |
| Market conditions targeted? | `TREND_UP` / `BREAKOUT_UP`, same as the real strategy |
| What changed vs. the real (NO-GO) strategy? | **Only the sampling frequency** (1D → 4h). `fast_period=20`, `slow_period=50`, and their ratio are byte-identical — this is not the "retune parameters post-hoc" move `STRATEGY_VALIDATION_FRAMEWORK.md` bans |
| Data granularity needed? | 4h — already an ordinary interval in this project's `HistoricalDataDownloader`/`BinanceSpotAdapter`, no new data-layer work required for a real trial |
| Assets | BTCUSDT spot, long-only (same as the real strategy; no margin/short logic — out of scope for this project by design) |

## Stage 1 — Data (synthetic, not real)

**This cloud session has no real Binance network access** (confirmed:
`api.binance.com` returns HTTP 403 via the egress proxy policy). Every
number below comes from `tests/synthetic_market.py` — a GARCH(1,1)
volatility-clustering + regime-switching-drift generator built to be
BTC-*shaped*, not a real-data claim. A fixed, predetermined battery of 15
seeds (1–15, chosen before any result was seen) was used throughout, per
the framework's anti-cherry-picking rule — no seed was dropped or
reselected after seeing its outcome.

Structural data-quality checks (OHLC consistency, no gaps, ≥4yr span) —
all pass; see `tests/test_trend_following_4h_candidate.py::TestStage1DataQuality`.

## Stage 2-3 — Results

### Trade frequency hypothesis: **CONFIRMED**

Full 15-seed battery, same price path per seed compared at 4h vs. resampled 1D:

| Metric | 4h | 1D (control) |
|---|---|---|
| Trade counts (15 seeds) | 125–164 (mean ≈ 140) | 16–29 (mean ≈ 21) |
| Seeds below the 30-trade minimum | **0/15** | **15/15** |

This matches the real-data finding closely (real 1D: 11 trades; synthetic
1D control: 16–29 trades, same order of magnitude) and confirms the
diagnosis: sampling the *identical* strategy logic more frequently
produces enough independent trade opportunities. The frequency fix, in
isolation, works exactly as hypothesized.

### Walk-forward GO/NO-GO: **NO-GO**

Ran `run_anchored_walk_forward` (the same harness and thresholds this
project uses for every other strategy) on a 5-seed sub-sample of the same
battery (seeds 1–5 — a smaller sub-sample than the trade-count check
above, for computational feasibility in this session; not silently
narrowed, documented here plainly):

| Seed | Folds | Verdict | Reason |
|---|---|---|---|
| 1 | 0 | NO-GO | No folds completed |
| 2 | 4 | NO-GO | 0/4 folds pass thresholds; p=0.119 ≥ 0.05; OOS trades 21 < 30 |
| 3 | 4 | NO-GO | 0/4 folds pass thresholds; p=0.523 ≥ 0.05; OOS trades 23 < 30; mean OOS Sharpe 0.29 < 0.5 |
| 4 | 2 | NO-GO | 0/2 folds pass thresholds; p=0.721 ≥ 0.05; OOS trades 16 < 30; mean OOS Sharpe −0.75 < 0.5 |
| 5 | 1 | NO-GO | 0/1 folds pass thresholds; p=0.687 ≥ 0.05; OOS trades 6 < 30; mean OOS Sharpe −0.43 < 0.5 |

**5/5 sampled seeds: NO-GO. 0/5: GO.**

## Stage 4 — Honest interpretation

Fixing the trade-frequency problem **does not, by itself, produce a
passing strategy** under this project's own walk-forward gate. The total
trade count over the full period is now comfortably above the Stage 1
minimum (125–164), but each individual OOS *fold* is still short on
trades (6–23) because the anchored walk-forward splits the period into
several OOS windows — the frequency fix helps the full-period total but
does not proportionally fix each fold's own sample size, and the OOS
Sharpe/significance numbers that did compute (seeds 3–5) are weak to
negative, not marginal.

**This is informative negative evidence, not a null result**: it rules
out "the real strategy's NO-GO is purely a sampling-frequency problem."
The deeper issue is more likely the edge itself (this specific
crossover's signal quality) and/or the walk-forward fold sizing
(`is_pct`/`oos_pct`/`step_pct` chosen here may carve OOS windows too
short for ANY 4h strategy to clear 30 trades per fold) — not something
this candidate's narrow, single-variable test can distinguish, and not
something to guess at by further tuning.

## Verdict

**NO-GO.** `candidate_router_trend_4h()` stays in
`trading_intelligence/strategy/router.py` as explicitly-not-wired,
opt-in code — useful as a tested reference for the next hypothesis, not
promoted to `default_router()`, and **not recommended for a real-data
trial as-is**: spending Claude Code local's real network access to test
this on real BTCUSDT would very likely reproduce the same synthetic
NO-GO, per the evidence above.

## What this leaves open (not resolved by this candidate)

- Whether a *different* walk-forward fold sizing (longer OOS windows,
  fewer folds) changes the per-fold trade-count problem — a methodology
  question, not a strategy-parameter one.
- Whether DualMACrossover's edge (any timeframe) is simply weak on
  BTC-like synthetic data, independent of frequency — would need a
  different strategy family, not a different timeframe, to test.
- Real-data confirmation of the synthetic 1D control's 16–29 trade range
  against the real 11-trade finding remains Claude Code local's domain
  (real network access); it is consistent, not identical, which is
  expected from any synthetic generator.
