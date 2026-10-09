# Pre-registration: "experimento horarios" (2-hour windows, 20-minute bars), PAPER only

Registered 2026-10-09 by the Quant/Strategy session at the leader's request (owner's goal:
operate and analyse every 20 minutes in ~2-hour sessions; after two weeks, pick the best
hours and markets), **before any result was computed**. Research/PAPER only: public data,
no account, no key, no orders. `trading_intelligence/live/` and `config/live_limits.json`
are not touched.

- Code: `trading_intelligence/backtesting/experimento_horarios.py`
- Workflow: `.github/workflows/experimento-horarios.yml`
- Output: `docs/experimento_horarios/`

This file is frozen once committed. A later change is a new pre-registration.

## Design (fixed)

- **Universe:** the 12 symbols of `config/live_limits.json` (2026-10-09) plus PAXGUSDT,
  frozen in code.
- **Bars:** public 5-minute Binance spot klines, aggregated into 20-minute bars that open at
  :00/:20/:40 UTC. A 20-minute bar missing any of its four 5-minute bars is dropped and
  counted as a gap.
- **Windows:** 12 per UTC day, each 2 hours long, starting 00:00, 02:00, …, 22:00 UTC. Each
  window is shown in UTC and in **UTC−5**, labeled as the owner's probable local time
  (Ecuador).
- **Inside a window:**
  - Every symbol and strategy starts flat and has one position at a time.
  - There are 6 decisions, at the window start and at each 20-minute close up to 1h40
    (:00/:20/:40). Each fills at the next 20-minute bar's open.
  - **Every position is force-closed at the window's last close.**
  - Indicators see the trailing 500 20-minute bars (≈ 7 days) up to the decision, including
    bars before the window (warm-up). There is no look-ahead.
- **Strategies, long-only Spot, using the repo's classes unchanged on 20-minute bars:**
  - **tendencia:** `default_router(symbol, "20m")`. That is `DualMACrossover`, EMA 20/50,
    routed for TREND_UP (confidence ≥ 0.5) and BREAKOUT_UP, with its swing-low stop over the
    last 10 bars. It exits on a bearish cross.
  - **rango:** `BollingerReversion` (repo defaults: BB 20/2, RSI 14 < 30 within 5 bars, exit
    at the middle band or RSI ≥ 50, stop 1.5 × ATR14), gated on RANGE at confidence ≥ 0.5,
    as `router_with_range_reversion` registers it.
  - **baseline:** buy at the window's first open and sell at its last close. This measures
    pure time-of-day drift.
- **Execution and costs:**
  - The fill model is `BacktestEngine`'s.
  - Entries fill at the next open × (1 + 5 bps).
  - Stops are checked on every bar: a gap fills at the open × (1 − 5 bps), and a touch fills
    at the stop × (1 − 10 bps).
  - Signal exits fill at the next open × (1 − 5 bps); forced closes at the close × (1 − 5 bps).
  - Fee: **0.1% per side**.
  - Size: a fixed **10 USDT** notional per trade, reported as **net % per trade**
    = P&L / (entry notional + entry fee).

## Periods

- **Reference (does not decide):** the 14 UTC days before 2026-10-10 (backfill), plus any
  day before 2026-10-10. Labeled "referencia: datos pasados".
- **Forward (decides):** **2026-10-10 → 2026-10-23**, 14 UTC days, each replayed the next
  day at 00:20 UTC.
  - Half 1 is days 1–7 (2026-10-10 → 10-16); half 2 is days 8–14 (10-17 → 10-23).

## Selection rule (fixed now; applied once, after 2026-10-23)

A **cell** is one window × symbol × strategy: 12 × 13 × 3 = 468 cells.

1. **Candidates** come from half 1: net mean > 0 and **at least 7 trades**. Seven is the
   minimum because baseline cells have exactly one trade per day.
2. **Confirmation** comes from half 2. For every candidate, a one-sided t-test of the half-2
   trades' net % against 0 (H1: mean > 0). A candidate with fewer than 7 half-2 trades or a
   mean ≤ 0 gets p = 1.
3. **Benjamini–Hochberg at q = 0.10** is applied over **all candidates** (the cells tested in
   half 2).
   - A cell **qualifies** only if its half-1 mean > 0 with n ≥ 7, its half-2 mean > 0 with
     n ≥ 7, and it survives BH.
   - q = 0.10 is the conventional exploratory false-discovery rate.
4. **Pooled views,** with more power and the same split-half and BH rule:
   - **by window**: all symbols, per strategy; 12 tests per strategy;
   - **by symbol**: all windows, per strategy; 13 tests per strategy.
5. **What "best hours / markets" may claim:** only qualifying cells or pooled rows.
   - If nothing qualifies, the report says so: **no hour or market is shown to be better
     than chance.**
   - Daily heat-maps and top/bottom-5 lists are descriptive only. With 468 cells, some will
     look good by luck every day.
6. Nothing found here authorizes real money (CLAUDE.md). A qualifying cell would be a
   hypothesis for its own forward test.

## Daily output

- `docs/experimento_horarios/<date>.json` and `<date>.md` (Spanish):
  - per window × symbol × strategy: trades, win rate, net % sum and mean;
  - window × symbol tables, in text, for the day and cumulative (forward and reference
    separately);
  - top and bottom 5 cells in plain Spanish.
- `docs/experimento_horarios/resumen.md` and `.json`: the cumulative view. After
  2026-10-23 it also carries the selection-rule outcome.

---

## Amendment 1 (2026-10-09 ~15:15 UTC, before any result was computed)

**Reason:** the owner clarified the design through the leader. A backfill under the original
design had been dispatched (run `37949279922`). It was cancelled about 10 seconds in, while
still fetching data. It produced and committed no result (verified: `docs/experimento_horarios/`
does not exist on the branch). Nothing below was chosen with any result in view. Where this
amendment conflicts with the text above, the amendment governs.

1. **Trading days.** Every day is computed and stored. The decision scope changes:
   - **Monday–Friday** is the primary decision scope.
   - **Saturday** is reported separately, so the owner can choose Mon–Fri or Mon–Sat. The
     Mon–Sat variant runs through the same rule as an alternative. This choice is a
     disclosed fork, not a hidden one.
   - **Sunday** is recorded and excluded from every decision.
   - A **per-weekday breakdown** (mean net % per trade, per strategy) is added to the daily
     and cumulative reports.
2. **Halves count trading days.** The forward period stays **2026-10-10 → 2026-10-23**.
   - It contains the 10 weekdays 2026-10-12 → 10-16 and 10-19 → 10-23, plus Saturdays
     10-10 and 10-17.
   - **Half 1** is the days up to 2026-10-16; **half 2** is 2026-10-17 → 10-23, each
     filtered to the scope.
   - The minimum trades per half equals the number of scope days in that half: **5**
     (Mon–Fri) or **6** (Mon–Sat). That is the most a baseline cell can reach (one trade
     per day).
3. **The owner's window, a PRIMARY planned hypothesis:** **07:00–10:00 Ecuador = 12:00–15:00
   UTC (3 hours, 9 twenty-minute bars)**. It is simulated separately, with the same
   strategies, costs and rules, and kept outside the exploratory BH family.
   - **Primary test (3 tests, Bonferroni α = 0.05/3):** for each strategy, pooled over the
     13 symbols, on the Mon–Fri scope. It passes if:
     - half-1 mean > 0;
     - half-2 mean > 0;
     - a one-sided t-test on half-2 trades gives p < 0.0167;
     - each half has at least 5 trades.
   - **Per symbol within the owner's window:** 13 × 3 = 39 tests, under their own BH at
     q = 0.10, with the same split-half conditions.
   - The 12 two-hour windows remain the **exploratory search**, under BH as registered above.
4. **Monitoring like a trader.**
   - Entries are still decided on completed 20-minute bars at :00/:20/:40. They fill at the
     next minute's open × (1 + 5 bps).
   - Once a position is open, its exit is checked **every 3 minutes on 1-minute klines**:
     - **Stop:** hit when any 1-minute low reaches it. The fill is at the stop × (1 − 10
       bps), the touch slippage `BacktestEngine` uses (kept for conservatism). If that
       minute opened below the stop, the fill is at its open × (1 − 5 bps).
     - **Exit condition:** the strategy's own `on_exit_signal`, evaluated at each 3-minute
       check on the 20-minute series whose last bar is the **in-progress** 20-minute bar
       built from the 1-minute data so far, which is what a trader watching live sees.
       Fill at the next minute's open × (1 − 5 bps).
     - **Forced close** at the window's last minute close × (1 − 5 bps).
   - **Data:** public **1-minute** Binance spot klines, from which the 20-minute bars are
     built. A 20-minute bar missing any minute is dropped; a window with a missing bar is
     skipped and counted.
5. **Ecuador time (UTC−5) first in every report**, UTC in brackets. The owner confirmed
   Ecuador.
6. **Unchanged:** universe, strategies, costs (0.1% per side + 5 bps, 10 USDT per trade),
   the 12 two-hour windows, the backfill (14 days before 2026-10-09, reference only), the
   forward dates, BH q = 0.10 for the exploratory family, and the PAPER-only scope.

---

## Amendment 2 (2026-10-09 ~15:40 UTC, before any forward data)

**Reason:** the reference backfill (run `37949990464`, 2026-09-25 → 10-08, which decides
nothing) showed something the design did not anticipate. `tendencia` and `rango` almost never
trade inside a window: 33 and 9 trades in 10 weekdays, never more than 2 in any window ×
symbol cell. So no strategy cell could ever reach the per-half minimum.

**Disclosure:** this amendment was written **after seeing that reference data**, and only to
make the registered question answerable. No forward day exists yet. The first is Saturday
2026-10-10; the first decisive weekday is Monday 2026-10-12. The rules below were not
chosen by looking at which hours or symbols did well.

1. **Strategy (d) "ruptura" (opening-range breakout), parameters fixed now:**
   - **Opening range:** the window's first 20-minute bar (high and low).
   - **Entry:** long, at the first 20-minute decision from the second bar onward whose last
     completed 20-minute close is **above the range high**. Fill at that minute's open ×
     (1 + 5 bps). **At most one entry per window.** No regime gate, no other filter.
   - **Stop:** the range low. It is checked on every 1-minute low; the touch fills at the
     stop × (1 − 10 bps), a gap at the open × (1 − 5 bps), as in Amendment 1. If the entry
     fill is at or below the range low, the trade is skipped.
   - **Exit:** the stop, or the forced close at the window's last minute close × (1 − 5 bps).
     There is no other exit.
   - Costs and size as registered: 0.1% per side + 5 bps, 10 USDT per trade.
2. **Confirmatory tests for tendencia, rango and ruptura are POOLED.** Same split halves,
   one-sided t-test on half 2, and half-1 mean > 0. **Minimum 15 trades per half** for every
   pooled test (all four strategies). Families:
   - **Owner's window 07–10 Ecuador (12–15 UTC), pooled over the 13 symbols, per strategy**
     (tendencia, rango, ruptura, baseline). These 4 tests remain **PRIMARY**, at
     **Bonferroni α = 0.05/4 = 0.0125**.
   - **Pooled by window** (all 13 symbols), per strategy: 12 tests per strategy, BH at
     q = 0.10, with all 12 as the denominator.
   - **Pooled by symbol** (all 12 two-hour windows), per strategy: 13 tests per strategy,
     BH at q = 0.10, with all 13 as the denominator.
   - **Window × symbol cells:** for tendencia, rango and ruptura, **descriptive only**.
     Baseline cells keep the registered cell-level rule: at least one trade per scope day
     per half, and BH at q = 0.10 over the candidates.
   - **Owner's window per symbol:** baseline only, 13 tests, BH at q = 0.10 over all 13. The
     other strategies are descriptive only there.
   - At the reference trade rate, tendencia and rango will probably not reach 15 trades per
     half in most pooled tests. A test that cannot reach the minimum reports "insufficient
     trades", never a pass.
3. **Unchanged:** split halves (half 1 ≤ 2026-10-16; half 2 2026-10-17 → 10-23); the Mon–Fri
   decision scope with Mon–Sat as the disclosed alternative; Sunday excluded; BH q = 0.10
   within each family; the 3-minute 1-minute monitoring; Ecuador time first; PAPER only.
4. The reference backfill is **re-run** so the reference reports include ruptura. It is
   still labeled "referencia: datos pasados" and still decides nothing.
