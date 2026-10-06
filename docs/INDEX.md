---
type: index
tags: [trading-intelligence, index]
status: living
aliases: ["Docs Index", "MOC"]
---

# Trading Intelligence AI — documentation index

> This is the Obsidian-ready entry point for `docs/`. GitHub is still the
> source of truth for code and technical decisions (per `AGENTS.md`) — this
> index and the frontmatter on each doc exist so a future Obsidian vault
> pointed at this repo is navigable and graph-viewable immediately, not a
> replacement for GitHub, and never blocking on Obsidian actually being
> connected. Wikilinks below (`[[like this]]`) are Obsidian's own syntax;
> GitHub renders them as plain text rather than breaking, so this file is
> safe to read on either.

## Coordination (read these first)

- [[AGENT_COORDINATION]] — who's doing what, right now
- [[CHECKPOINT]] — the running session log
- [[AGENT_CITY_DATA_CONTRACT]] — the Agent City data contract (sources, freshness rules, status semantics)
- `checkpoints/`[[GPT_WORK_AGENT_CITY_2026-10-06]] — a bounded handoff checkpoint

Permanent agent roles and rules live in `AGENTS.md` at the repo root (not
under `docs/`, so not indexed here — it's the first file every agent reads).

## Specifications (the design, written before implementation)

- [[SYSTEM_ARCHITECTURE]] — component map and data flow
- [[RISK_ENGINE_SPEC]] — the deterministic risk engine's intended design
- [[PAPER_TRADING_SIMULATION_SPEC]] — fill models, fees, position accounting
- [[STRATEGY_VALIDATION_FRAMEWORK]] — the out-of-sample gate every strategy must pass
- [[INITIAL_STRATEGY_CANDIDATES]] — the four candidate strategies
- [[BINANCE_INTEGRATION_NOTES]] — Binance Spot API reference
- [[XM_METATRADER_INTEGRATION]] — XM/MetaTrader research (Phase 2, not started)

Two of these (`RISK_ENGINE_SPEC`, `PAPER_TRADING_SIMULATION_SPEC`) describe
the design that `trading_intelligence/` implements closely and the real
PAPER system (root `*.py` modules, imported via PR #3) implements
differently in places — see [[FINDING_3_HALT_DESIGN]] and
`AGENT_COORDINATION.md`'s Finding 2/3 entries for where they currently
diverge and why that divergence is a tracked decision, not an oversight.

## Operations

- [[DEPLOYMENT_RUNBOOK]] — modes, startup, crash recovery, rollback
- [[FINDING_3_HALT_DESIGN]] — grounded design note for the real system's missing persistent halt

## Live surfaces (not files — linked for completeness)

- [GitHub repo](https://github.com/tatopozot-rgb/trading-intelligence-ai) — source of truth
- [Notion Operations Center](https://app.notion.com/p/3f002a0ff45f81c58fecc00ba9221812) — Mission Control
- [Agent City (Notion)](https://app.notion.com/p/3f102a0ff45f81678550e6b88514b55f) — V0
- [Agent City (web snapshot)](https://claude.ai/artifact/98zjB7JbToV2ernTsjdLKD) — V1, a point-in-time read, not a live feed
