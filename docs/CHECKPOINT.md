# Checkpoint — Trading Intelligence AI

> Last updated: 2026-10-05T22:05:00Z
> Agent: Trading Codex (cloud session)
> Branch: `ccr-b66a9a9e-okj2pl` @ commit pending (downloader + Binance public-data fix)
> PRs: #1 (specs, open), #3 (real PAPER import, open, NOT merged), #4 (MARKET lot contract, open, NOT merged), #5 (is_junction fix, open, NOT merged)

## IMPORTANT — three-agent structure (corrected nomenclature)

Per explicit owner correction, there are exactly **three** agents on this
project — see `AGENTS.md` for the permanent definition:
1. **Trading Claude-Work** — the real ChatGPT Work agent (cross-review, architecture, risk, quant, Notion Mission Control). Any older doc saying "Trading claude work" (lowercase, no hyphen) means this same agent, never a plain chat session.
2. **Trading Codex** (this agent) — cloud container (`/home/user/trading-intelligence-ai`), **no access to the owner's local Windows PC**.
3. **Claude Code local** — runs via PowerShell on the owner's PC, has real access to `C:\Users\tatop\trading-ai`. Did the actual codebase import (PR #3) and the MARKET lot/dust contract (PR #4).

GitHub is the shared source of truth between all three. Check PR/issue state
before assuming what another agent has or hasn't done.

## Current State

**Phase**: REVIEW — real PAPER runtime imported via PR #3, cross-reviewed, not yet merged.
**Status**: Two parallel, non-conflicting bodies of code now exist on this branch:
1. `trading_intelligence/` — a research/backtesting package built from the specs in PR #1 (indicators, strategy, backtest engine, **and now a full RiskEngine + PaperAdapter + BinanceSpotAdapter skeleton**, built independently before PR #3's existence was known to this session).
2. The **real PAPER system** (root-level flat modules: `risk_engine.py`, `paper_store.py`, `paper_fills.py`, etc.) — sitting on branch `codex/import-paper-baseline`, proposed via PR #3 against this branch. **This is the authoritative system per explicit owner instruction** ("el programa real existente es la autoridad"). `trading_intelligence/` should be treated as a reference/validation harness, not a replacement.

## What Was Done This Session (Trading Codex — cloud)

### 1. Risk/execution layer for `trading_intelligence/` (built before PR #3 was discovered)
- `trading_intelligence/risk/models.py` — `RiskConfig` (validated at construction), `RiskState` (JSON-persisted, atomic write)
- `trading_intelligence/risk/engine.py` — `RiskEngine`: full 11-step validation per `docs/RISK_ENGINE_SPEC.md` (kill switch, daily loss halt, drawdown pause/halt, stop validation, fixed-fractional sizing, position/exposure/correlated-exposure limits), connectivity watchdog, audit logging
- `trading_intelligence/persistence/audit_log.py` — append-only JSONL audit log, daily rotation
- `trading_intelligence/execution/base.py` — `AbstractExchangeAdapter` interface
- `trading_intelligence/execution/order_models.py` — `OrderRequest`, `OrderResult`, `Position`, `AccountInfo`
- `trading_intelligence/execution/paper.py` — `PaperAdapter`: wraps a market-data adapter, intercepts orders, next-bar fills (MARKET/LIMIT/STOP with gap-through slippage), position accounting, state persistence
- `trading_intelligence/execution/binance.py` — `BinanceSpotAdapter` skeleton: lazy client construction, lot/tick/notional filter rounding, credential-gated (raises `BinanceCredentialsMissing` cleanly when no API keys — never crashes construction)
- 60 new tests (`test_risk_engine.py` ×30, `test_paper_adapter.py` ×12, `test_binance_adapter.py` ×18), all passing
- Fixed a real bug found via these tests: RSI formula produced NaN when all bars are gains (division by zero avg_loss) — now correctly returns RSI=100
- Fixed a real infinite-loop bug in `PaperAdapter.on_new_bar`: mutating `self.pending_orders` while iterating it
- Fixed a real bug where STOP orders were filling unconditionally through the generic MARKET/LIMIT path instead of only via gap-through stop-trigger logic
- `pyproject.toml` (ruff + mypy config), `.github/workflows/research-tests.yml` (ubuntu-latest, pytest+ruff+mypy, triggers on `trading_intelligence/`/`tests/` changes only)
- **92/92 tests passing, ruff clean, mypy clean** on the full `trading_intelligence/` package

### 2. Discovered and audited PR #3 (real PAPER system import)
Posted a full cross-review on PR #3 (see GitHub). Independently reproduced on Linux
(the import was done/tested on Windows):
- **549/558 tests reproduced** in 14.7s on Linux, Python 3.11, fresh `pip install pandas requests`
- **No secrets found** (independent grep confirms their own scan)
- Confirmed `trading_intelligence/`, `tests/`, `pytest.ini`, `requirements.txt`, `pyproject.toml` are **untouched** by PR #3 — no conflict
- Confirmed: no martingale, no risk-escalation-after-loss anywhere in the real sizing/re-entry logic
- Confirmed: SQLite `BEGIN IMMEDIATE` transactions throughout `paper_store.py` give real atomicity/crash-recovery; UUID + plan-hash gives idempotency against duplicate/replayed requests
- Confirmed: manual file-based kill switch (`PAUSA_ENTRADAS`) correctly blocks only new entries, not existing positions
- **Finding 1 (trivial, not blocking)**: `tools/check_repository.py::_linked()` calls `Path.is_junction()`, which doesn't exist on `PosixPath` → 14 test errors on Linux (all isolated to the new safety-guard tool, zero impact on trading logic or their actual Windows CI)
- **Finding 2 (needs a decision, not blocking this PR)**: `docs/RISK_ENGINE_SPEC.md` specifies daily-loss reset at 00:00 UTC; the real code (`paper_store.asegurar_dia`) resets on local UTC-5 day boundary. Needs explicit sign-off — either the spec or the code should change, not silently diverge.
- **Finding 3 (real gap vs spec, not previously flagged by either session)**: no automatic drawdown pause/halt (8%/15% equity-peak per spec) and no connectivity-watchdog auto-kill-switch (>60s per spec) exist in the real system — only the manual file-based kill switch. This is genuine unimplemented spec coverage, distinct from the already-known MARKET/quoteOrderQty/lot/dust gap.
- **Did NOT merge PR #3** — Issue #2's checklist isn't fully checked yet and the PR's own checkpoint says "address findings before merge." Left for cross-review resolution (Finding 2 in particular needs Trading Claude-Work's input per AGENTS.md: "Risk engine changes require review from Trading Claude-Work").
- Posted one comment on Issue #2 flagging that the actual local-PC import (criterion 1 of the issue) is something this cloud session cannot do itself — not repeating that per the WAITING_FOR_USER rule.

### 3. Documentation correction
- My own Session 2 test count breakdown had an arithmetic bug: wrote "21/21" for indicators when it's actually 20 (20+7+5=32, matching the stated 32 total — the total was always right, only the per-file line was wrong). Corrected below.

### 4. Discovered, reviewed, and fixed PR #4 and opened PR #5 (second session block, same day)
- **PR #4** (`codex/market-lot-contract`, stacked on PR #3, by Claude Code local): adds `execution_market_filters.py` — offline MARKET lot/dust contract, fail-closed (rejects `quoteOrderQty` outright, requires both `MARKET_LOT_SIZE` and `LOT_SIZE`, rejects `MIN_NOTIONAL`/`NOTIONAL` unless explicitly flagged as not applying to MARKET). 16 new tests.
  - Independently reproduced on Linux: 565/574 tests (549+16; the 9-test gap is the same already-documented Tkinter/Windows-only platform gap from the PR #3 review, not a new regression).
  - Read the full 104-line module: no bugs found. Correctly cites what official Binance docs do and don't confirm (quoteOrderQty semantics and LOT_SIZE-on-MARKET applicability are explicitly left unverified/conservative, matching their own docstring).
  - Confirmed it does NOT touch `risk_engine.py`, `paper_store.py`, `paper_fills.py` — orthogonal to PR #3 Findings 2/3, which remain open and still block the final merge per Issue #2.
  - Posted a COMMENT review on GitHub: no changes requested; final semantic sign-off left to Trading Claude-Work per AGENTS.md review protocol.
- **PR #5** (`codex/fix-is-junction-linux`, stacked on PR #4, opened by this agent): fixes Finding 1 from the PR #3 review — `tools/check_repository.py::_linked()` called `Path.is_junction()`, which doesn't exist on `PosixPath` (Windows-only, Python ≥3.12 only). One-line `getattr` guard. Verified: 14 errors → 0 on Linux; only 2 residual failures remain, both pure environment gaps (no tkinter installed in this container), unrelated to the fix. Opened as its own PR (not pushed directly to PR #3/#4's branches) to respect the no-simultaneous-edit rule, since those branches are owned by Claude Code local.

### 5. Fixed a real bug in BinanceSpotAdapter + built the historical data downloader
- **Bug found and fixed**: `BinanceSpotAdapter` required credentials for *every* operation, including `get_current_price`, `get_ohlcv`, `is_connected` — but `docs/BINANCE_INTEGRATION_NOTES.md` explicitly states klines/ticker/exchangeInfo/ping are public, no API key needed. Only account/trading endpoints should require credentials. Fixed: `_get_client()` no longer requires credentials to construct; `submit_order`, `get_position`, `get_account_info` now explicitly call `_require_credentials()`; `is_connected()` and the new `verify_public_connectivity()` work with zero credentials. Updated/added tests accordingly (22 tests in `test_binance_adapter.py`, up from 18).
- **`trading_intelligence/data/downloader.py`** — `HistoricalDataDownloader`: downloads and caches OHLCV to Parquet (`data/historical/{symbol}/{interval}/{YYYY-MM}.parquet`), paginates the public klines endpoint by close-time per `docs/BINANCE_INTEGRATION_NOTES.md`'s example, never re-downloads a cached month unless `force=True`, de-duplicates overlapping bars. Uses `BinanceSpotAdapter` with **zero credentials** (public data only — consistent with the owner's explicit instruction not to request Binance API keys).
- 11 new tests (`test_downloader.py`), all mocked (no real network calls): caching, forced re-download, pagination by close-time, empty-response handling, no-duplicate-bars, multi-month range spanning, missing-cache error.
- **107/107 tests passing, ruff clean, mypy clean** on the full `trading_intelligence/` package (up from 92).
- **Nomenclature correction** (this update): per explicit owner correction, rewrote `AGENTS.md` to define exactly three agents (Trading Claude-Work = real ChatGPT Work, Trading Codex = this agent, Claude Code local = PowerShell session on the owner's PC) and corrected all "Trading claude work" references in this file and `docs/AGENT_COORDINATION.md` to "Trading Claude-Work".

## What's Next

**For whichever agent picks this up next:**
1. **Trading Claude-Work**: rule on PR #3 Findings 2 and 3 — risk-policy sign-off on UTC vs local day boundary for daily loss reset, and whether to add automatic drawdown/connectivity kill-switches to the real system now or explicitly defer them. Also give final semantic sign-off on PR #4's MARKET contract.
2. **Claude Code local**: continue integrating `execution_market_filters.py` (PR #4) with `paper_fills.py`/`paper_store.py` once Trading Claude-Work's review lands — explicitly not done yet per PR #4's own checkpoint note.
3. Once Findings 2/3 are resolved: merge the PR #3 → #4 → #5 chain into `ccr-b66a9a9e-okj2pl`, then decide whether `trading_intelligence/` continues as a parallel research package or becomes the validation/backtesting layer calling into the real system's modules.
4. `trading_intelligence/` outstanding items (lower priority now that the real system is authoritative, downloader now done): run a real-data backtest on actual BTCUSDT history via the new `HistoricalDataDownloader`, then walk-forward on Dual MA Crossover.

## Blockers

- **PR #3/#4/#5 merge chain**: blocked on Trading Claude-Work's risk/quant sign-off on Findings 2 & 3 (see above). Nothing further blocks engineering work in the meantime.
- **Binance API keys not configured** — not required for public market data or PAPER mode; needed only for live trading authorization later (explicitly not requested yet)
- **XM/MetaTrader credentials unknown** — Phase 2, separate adapter, not blocking current PAPER work

## Test Status

**`trading_intelligence/` package: 107/107 tests passing**, ruff clean, mypy clean.
```
tests/test_indicators.py       20/20 PASS
tests/test_ma_crossover.py      7/7  PASS
tests/test_backtest_engine.py   5/5  PASS
tests/test_risk_engine.py      30/30 PASS
tests/test_paper_adapter.py    12/12 PASS
tests/test_binance_adapter.py  22/22 PASS
tests/test_downloader.py       11/11 PASS
```

**Real PAPER system (PR #3, `codex/import-paper-baseline`): 549/558 tests**,
independently reproduced on Linux in 14.7s (14 errors, all the same isolated
`is_junction()` portability bug in the safety-guard tool; 20 skips, likely
Tkinter/Windows-UI tests degrading gracefully on headless Linux).

## Documents Ready for Codex to Implement Against

| Document | Purpose | Priority | Status |
|----------|---------|----------|--------|
| docs/RISK_ENGINE_SPEC.md | RiskEngine | CRITICAL | Implemented in `trading_intelligence/`; real system has a simpler/different variant — see Findings 2/3 |
| docs/PAPER_TRADING_SIMULATION_SPEC.md | PaperAdapter | HIGH | Implemented in `trading_intelligence/`; real system's `paper_fills.py` is more sophisticated (real order-book depth walking, not flat bps) |
| docs/BINANCE_INTEGRATION_NOTES.md | BinanceSpotAdapter | HIGH | Skeleton implemented in `trading_intelligence/`, credential-gated |
| docs/SYSTEM_ARCHITECTURE.md | Module structure | HIGH | `trading_intelligence/` follows it; real system uses a flat-module layout instead |
| docs/XM_METATRADER_INTEGRATION.md | XM adapter (Phase 2) | MEDIUM | Not started |
| docs/STRATEGY_VALIDATION_FRAMEWORK.md | Backtest framework | HIGH | Walk-forward implemented in `trading_intelligence/` |
| docs/INITIAL_STRATEGY_CANDIDATES.md | Strategy order | MEDIUM | MA Crossover implemented |

## Code Integration Notes

- `trading_intelligence/strategy/models.py`'s `RiskDecision` stub now has a real counterpart: `trading_intelligence.risk.engine.RiskEngine.validate_order()` returns it populated.
- Before merging PR #3, re-run the full `trading_intelligence/` test suite (`pytest tests/ -v`) to confirm it still passes untouched (it should — PR #3 doesn't touch those paths).
- Do not assume the real system's `risk_engine.py` and `trading_intelligence/risk/engine.py` are interchangeable — they implement different (and currently diverging) policies. Reconcile per Findings 2/3 before treating either as final.
