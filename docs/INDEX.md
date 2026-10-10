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

- [[ESTADO_ACTUAL]] — **start here**: what runs, the approved limits, the schedule, the desk, Monday's checklist
- [[CHECKPOINT]] — the latest work blocks (history up to 2026-10-10 in `archivo/`)
- [[AGENT_COORDINATION]] — who's doing what, right now
- [[AUTOMATIZACION]] — what runs on its own, and the memory rule
- `archivo/` — superseded documents, kept for history

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
differently in places — see [[archivo/FINDING_3_HALT_DESIGN|FINDING_3_HALT_DESIGN]] (archived) and
`AGENT_COORDINATION.md`'s Finding 2/3 entries for where they currently
diverge and why that divergence is a tracked decision, not an oversight.

## Operations

- [[DEPLOYMENT_RUNBOOK]] — modes, startup, crash recovery, rollback
- [[archivo/FINDING_3_HALT_DESIGN|FINDING_3_HALT_DESIGN]] — design note for the persistent halt (archived)

## Live surfaces (not files — linked for completeness)

- [GitHub repo](https://github.com/tatopozot-rgb/trading-intelligence-ai) — source of truth
- [Notion Operations Center](https://app.notion.com/p/3f002a0ff45f81c58fecc00ba9221812) — Mission Control
- [Agent City (Notion)](https://app.notion.com/p/3f102a0ff45f81678550e6b88514b55f) — V0
- [Agent City (web snapshot)](https://claude.ai/artifact/98zjB7JbToV2ernTsjdLKD) — V1, a point-in-time read, not a live feed

## Sistema PAPER real (módulos raíz, Claude Code local)

Sección añadida al resolver el merge del PR #9: conserva el índice que traía la rama local.

- [Importación y reproducción](archivo/IMPORTACION_2026-10-05.md) (archivado)
- [Mission Control y protocolo de ciclos](archivo/MISSION_CONTROL.md) (archivado)
- [Operación y arquitectura](../README.md)
- [Fills](../MODELO_FILLS_PAPER.md)
- [Controles](../CONTRATO_CONTROLES_PAPER.md)
- [Ejecución offline](../CONTRATO_EJECUCION_OFFLINE.md)
- [Binance/XM separados](../PLATAFORMAS_BINANCE_XM.md)
- [Conexión, bloqueos, lectura firmada y Testnet](../CONEXION_BINANCE.md)
- [Cartera](../CONTRATO_CARTERA_PAPER.md)
- [Diagnóstico negativo](../RESULTADO_CARTERA_PAPER.md)
- [Roadmap](../PLAN_PILOTO.md)
- [Historial](../CHECKPOINTS.md)
- [Diagnóstico sin operar](../ENTORNO_Y_DIAGNOSTICO.md)
- [Handoff de la capa de API (H1-H3)](archivo/HANDOFF_CLAUDE_LOCAL_API.md) (archivado)
- `history/`: checkpoint y coordinación de la rama local tal como estaban antes de este merge
  (`CHECKPOINT_CLAUDE_LOCAL_2026-10-08.md`, `COORDINATION_CLAUDE_LOCAL_2026-10-08.md`).
