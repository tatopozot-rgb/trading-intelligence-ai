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
