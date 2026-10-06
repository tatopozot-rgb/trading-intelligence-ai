---
type: project
tags: [project, trading-intelligence]
status: active
---

# Trading Intelligence

AI-powered multi-agent trading system for Binance (primary) and XM
(Phase 2, not started). PAPER mode only; no real money moves without
explicit `LIVE_ACTIVATION_APPROVAL` from the owner. PAPER/backtesting/
walk-forward/shadow validation are internal gates, not the destination —
the goal is a complete, production-ready, auditable system.

## Repository

[github.com/tatopozot-rgb/trading-intelligence-ai](https://github.com/tatopozot-rgb/trading-intelligence-ai)
— the single source of truth for code and technical decisions. This vault
is Mission Control's *second* surface (after Notion), for the owner's own
reference — never the authority.

## Agents

- [[Trading Codex (cloud)]] — cloud engineering + coordination lead
- [[Trading Claude-Work (GPT Work)]] — review, quant, Notion ops
- [[Claude Code local]] — local execution on the owner's PC

## Current state (as observed 2026-10-06 ~02:45 UTC — a snapshot, not live)

- **PR chain #3 → #4 → #5**: open, not merged. Waiting on Claude Code
  local's Finding 2 (daily-loss test coverage) and Finding 3 (persistent
  automatic halt) work, then Trading Claude-Work's risk sign-off.
- **PR #6** (Agent City Notion handoff): merged.
- **Research package** (`trading_intelligence/`): 191/191 tests passing,
  ruff clean, mypy clean.
- See [[Current Checkpoint]] for the full detail and [[Agent City]] for
  the visual/org view.

## Safety constraints (non-negotiable, don't let any note below contradict these)

- No martingale, no revenge trading, no automatic risk increase after a loss.
- Risk engine decisions are final; no agent bypasses them.
- `LIVE_ACTIVATION_APPROVAL` is asked exactly once, only when everything
  else (architecture, risk, quant, security, tests, CI, crash recovery,
  cross-review, docs) is genuinely done.
