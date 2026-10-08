# Pre-registration: 4h forward confirmation of `tendencia` and `tendencia_rango`

Registered 2026-10-08 by the Quant/Strategy session, before any 4h bar after
2026-10-01 was looked at by this session. Research only: public klines, no key, no
orders. Code: `trading_intelligence/backtesting/forward_confirmation.py` (the constants
there are this document; tests in `tests/test_forward_confirmation.py`).

**This document is frozen.** Any change to the hypothesis, data, rule or dates after
this commit voids the test. A later idea is a new pre-registration with a new start
date, never an edit here. The git history of this file is the audit trail.

## Why

Section 45 of `docs/CHECKPOINT.md`: at 4h, out-of-sample on 2024-10 → 2026-10, both
profiles were nominally positive but not significant:

| Profile | Trades | Mean net/trade | Profit factor | p |
|---|---|---|---|---|
| tendencia | 206 | +3.51% | 1.99 | 0.088 |
| tendencia_rango | 235 | +3.06% | 1.90 | 0.090 |

The operator now refuses real orders except at 4h (section 46). Whether 4h has an edge
needs evidence from data that played no part in building or choosing it.

## Hypothesis

- **H1 (primary, `tendencia`):** on 4h Binance spot bars after 2026-10-01, the mean net
  return per closed trade, after 0.1% fee per side and 5 bps slippage, is > 0.
- **H0:** it is ≤ 0.
- **Secondary, `tendencia_rango`:** the same hypothesis, judged by the same rule and
  reported separately. A GO there alone is labeled secondary and is not a GO for the
  operator's default profile.

## Data and engine (fixed)

- Timeframe 4h. Bars with open time ≥ **2026-10-01 00:00 UTC** and < the look date.
  **No bar before 2026-10-01 is used**, not even as indicator warm-up. Each symbol's
  engine starts cold, exactly like every OOS window in section 45.
- Symbols: the 12 symbols in `config/live_limits.json` on 2026-10-08, frozen in code:
  BTCUSDT ETHUSDT BNBUSDT SOLUSDT XRPUSDT DOGEUSDT ADAUSDT LINKUSDT AVAXUSDT LTCUSDT TRXUSDT DOTUSDT.
- Source: data-api.binance.vision public klines with the feed's impossible-bar guard.
  Gaps are reported, never filled.
- Profiles exactly as `live/operator.py` builds them at 4h (parity test in
  `tests/test_real_data_validation.py`), with code as of this commit.
- BacktestEngine with a trailing 500-bar window, 0.1% fee per side, 5 bps slippage, and
  10,000 per symbol at 1% risk per trade. Only **closed** trades count; a trade still open
  at the look date is ignored, which is the section 45 rule.
- Statistic: all closed trades of all 12 symbols, pooled. Two-sided one-sample t-test of
  the net return per trade against 0.

## Looks and the exact rule

Each look uses all data from 2026-10-01 up to the look date. The code refuses to run a
look before its date, and refuses any date not listed here.

| Look | Can declare | Rule (applied in this order) |
|---|---|---|
| **2027-04-01** (futility) | REFUTED only | trades ≥ 30 and (mean ≤ 0 or PF < 1.0) → **REFUTED**; otherwise INCONCLUSIVE |
| **2027-10-01** (evaluation) | GO or REFUTED | REFUTED as above; else trades ≥ 30, PF ≥ 1.3, mean > 0 and **p < 0.025** → **GO**; otherwise INCONCLUSIVE |
| **2028-10-01** (final) | GO, REFUTED or NO-GO | as 2027-10-01, except anything not GO or REFUTED is **NO-GO** |

- p < 0.025 at each GO look is Bonferroni over the two GO looks. The overall false-GO rate
  stays ≤ 0.05. The futility look cannot add false GOs.
- The first GO or REFUTED ends the test. INCONCLUSIVE means wait for the next look.
- Code changes after this commit (strategy, router, engine, fees) do not move the test.
  The evaluation runs the code at this commit. A changed strategy is a new hypothesis.

## Expected power (stated in advance)

From the section 45 numbers (per-trade standard deviation ≈ 29% for `tendencia` and
≈ 28% for `tendencia_rango`; about 8.6 and 9.8 pooled trades per month), and **if the
true edge equals the section 45 estimate**:

| Look | Expected trades | Power to GO |
|---|---|---|
| 2027-10-01 | ~103 (`tendencia`) / ~118 | ~0.15 at the registered p < 0.025 |
| 2028-10-01 | ~206 / ~235 | ~0.30 at the registered p < 0.025 |

The true edge is probably smaller than a backtest estimate. So **INCONCLUSIVE and
NO-GO are the likely outcomes even if a real edge exists.** This test is much better at
catching a 4h profile that loses (REFUTED) than at proving one that wins. Nobody should
read "not yet refuted" as "validated". Only GO means validated.

## Known limitations, disclosed now

- On 2026-10-08, about one week of 4h bars after 2026-10-01 already exists. This session
  has not looked at them. The scheduled PAPER loop (`.github/workflows/paper-loop.yml`)
  has been running `tendencia` at 4h on real data since before this registration, and its
  run summaries show recent decisions. Neither can change the rule above, which is fixed
  in code.
- PAPER loop results are separate evidence. They show live-path behavior: feed, state,
  and fills on unseen bars. They do not replace this test, because the PAPER loop sizes
  positions with the risk engine rather than at 1% per trade.
- Crypto regimes last months. A 12–24 month window is still one or two market phases.

## How to run a look (on or after its date)

Dispatch-only, like `.github/workflows/real-data-walk-forward.yml` (GitHub IPs cannot
reach api.binance.com; data-api.binance.vision works):

```
python -m trading_intelligence.backtesting.forward_confirmation --look 2027-10-01 --workers 4 --out results
```

Record the printed outcome lines and the commit used in a new CHECKPOINT section.
