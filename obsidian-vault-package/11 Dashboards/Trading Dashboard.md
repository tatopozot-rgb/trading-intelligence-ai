---
type: dashboard
tags: [dashboard, trading-intelligence]
---

# Trading Dashboard

A plain-markdown dashboard — written without assuming any community
plugin (Dataview, etc.) is installed in this vault, since that couldn't
be verified from the cloud session that wrote this. If Dataview *is*
installed, this note could later be rewritten as live queries over the
Notion/GitHub data instead of this manual snapshot — worth doing, not
done here.

## Project health

| | |
|---|---|
| Phase | Review of import + MARKET contract; Agent City running |
| Health | 🔵 REVIEW |
| Open PRs | #1, #3, #4, #5 |
| Merged PRs | #6 |
| Research tests | 191/191 passing, ruff clean, mypy clean |
| Real PAPER system tests | 558 reported (Windows, not independently re-run this pass) |

## Blockers (open, as of this snapshot)

- `TECH-CI-001` — Windows runtime CI not run on a remote service (research CI is separate, doesn't cover it).
- `WAIT-NOTION-VISUAL-001` — authenticated visual QA of the Notion UI needs the owner's own browser session.

## Critical path right now

[[Claude Code local]] implementing Finding 2's tests and Finding 3's
persistent halt → [[Trading Claude-Work (GPT Work)]] setting real risk
thresholds and signing off → PR #3→#4→#5 merge.

## Live surfaces

- [GitHub repo](https://github.com/tatopozot-rgb/trading-intelligence-ai)
- [Notion Operations Center](https://app.notion.com/p/3f002a0ff45f81c58fecc00ba9221812)
- [Agent City — Notion (V0)](https://app.notion.com/p/3f102a0ff45f81678550e6b88514b55f)
- [Agent City — web snapshot (V1)](https://claude.ai/artifact/98zjB7JbToV2ernTsjdLKD)
- [[Agent City]] — this vault's own view
