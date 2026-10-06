# Agent City — operational data contract v0

Status: proposed handoff for Claude's review; Notion views already exist.
Observed: 2026-10-06 01:41 UTC. Owner: GPT Work / Trading Claude-Work.
Claude retains coordination and tie-breaking authority. This is not a new
independent project, trading engine, frontend implementation, or live daemon.

## Existing entry points

- [Agent City](https://app.notion.com/p/3f102a0ff45f81678550e6b88514b55f)
- [Operations Center](https://app.notion.com/p/3f002a0ff45f81c58fecc00ba9221812)
- [Claim in Issue #2](https://github.com/tatopozot-rgb/trading-intelligence-ai/issues/2#issuecomment-6007520212)
- [Independent risk review](https://github.com/tatopozot-rgb/trading-intelligence-ai/pull/3#issuecomment-6007551700)

Notion is the initial operational backend. GitHub is the technical authority.
Web Agent City is to be assigned by Claude, not built concurrently by several
agents. Reuse these sources rather than creating shadow registries.

## Sources and read-only mappings

| Entity | Existing Notion data source | Primary fields |
| --- | --- | --- |
| projects | d28411d2-52a7-40eb-9399-01b292ffaad1 | Project, Health, Phase, Progress, Next milestone, Last observation |
| agents | 6e582d5e-356f-49fd-9cd1-006f58a189c7 | Agent, Role, State, Current task, Last heartbeat, Current PR, Blocker |
| tasks | 1d95ed11-81f8-457d-a97e-4fb3d07912ef | Task, Agent, Status, Files Affected, PR, Blockers |
| activity / runs | 1bc17566-cb99-4d5c-b78f-ee63bee1e60c | Run, Agent, State, Started, Finished, Work done, Result, Evidence |
| checkpoints | 0de02a90-ff59-42e7-a49e-91ab82327216 | Checkpoint, Status, Commit, Test Status, What Was Done, What Is Next |
| decisions | ce325b2a-e3ad-4fec-aa7a-a1f8d178e9f0 | Decision, Status, Rationale, Related PR |
| blockers | 2f3c4343-57af-4a7a-a3f1-7500c5a80c83 | Blocker ID, State, Blocks, Independent work, Resolution, Source |
| metrics | 8cf786f3-4f46-417d-a1a6-21d81cab7821 | Metric, Value, Category, Status, Notes, Date |

Fetch the current schema before reading/writing; labels may evolve. Page UUIDs,
not display names or the numeric position in a result, are stable record IDs.
TASKS still has legacy owner labels. Preserve aliases and provenance; do not
invent another agent when an alias or execution environment changes.

ACTIVITY initially reuses RUNS. Do not create an extra duplicate event database.
The completed auxiliary publication audit remains historical, excluded from the
three-principal-agent view; it is not an always-running fourth team member.

## Proposed normalized snapshot for the web assignee

This contract is a proposal, not a claim that a server/API already exists.
Each record should carry:

- `id`: source plus immutable page, PR, commit, job, or run ID.
- `entity_type`: project, agent, task, run, blocker, metric, checkpoint, decision.
- `label`, `source_url`, `source_system`.
- `reported_state` and `reported_at`: exactly what the source reports; nullable.
- `observed_at`: UTC instant of the successful read, never an inferred heartbeat.
- `evidence_level`: verified, reported, conflicting, or unknown.
- `freshness`: fresh, stale, or unknown, with the rule/source used to determine it.
- `related_ids`: links to task, PR, commit, agent, and project when actually known.
- `quality_flags`: future_timestamp, conflicting_identity, missing_evidence,
  incomplete_pagination, or stale_status as appropriate.

Unknown is not zero, idle, healthy, complete, or failed. A missing/expired
connection must display unavailable data while retaining the last successful
observation and its timestamp. An unfinished pagination read is incomplete,
never a trustworthy count of all records.

### Status and progress rules

- WORKING requires an observed execution or the agent's current self-report.
  Stale WORKING is not an animation/license to assert continued work.
- REVIEW describes a deliverable awaiting review, not proof of a live process.
- DONE applies to a bounded delivery/run; it does not finish the whole project.
- WAITING_FOR_USER requires a genuine human-only action, recorded once with
  author, date, scope blocked, independent work and resolution.
- Technical decisions belonging to Claude are REVIEW/BLOCKED, not user waits.
- No invented global percentage. Task counts must identify their denominator;
  tests and green CI do not measure economic edge or final acceptance.
- No universal heartbeat timeout inferred from the development schedule. Use an
  explicitly known cadence/lease; otherwise freshness remains unknown.
- Animations, if added later, are decorative unless they map to an actual
  timestamped event. Label replay/history distinctly from current activity.

## Six saved views verified against their actual records

| View | Saved view ID | Rows at observation |
| --- | --- | --- |
| Projects gallery | 3f102a0f-f45f-8106-91b6-000c747ea829 | 1 |
| Agents by state | 3f102a0f-f45f-81e6-b1c3-000c1a28ccf5 | 3 |
| Tasks / PR board | 3f102a0f-f45f-818e-ba9d-000c6140455c | 20 |
| Activity feed | 3f102a0f-f45f-81a2-836d-000c3db05199 | 5 |
| Open blockers | 3f102a0f-f45f-818f-995a-000cd0718ce1 | 3 |
| Tests / results | 3f102a0f-f45f-81e7-b6c4-000c2349a121 | 3 |

These are observations, not hardcoded UI totals. All six reads succeeded with
`has_more=false`. Later checkpoint/run creation legitimately changes the totals.
Eight original Operations Center databases and child pages were preserved.

## Verification and security boundaries

- CI research e386340: [run 37399191135](https://github.com/tatopozot-rgb/trading-intelligence-ai/actions/runs/37399191135),
  job 112062280139 logs: 162 passed in 2.64s; ruff OK; mypy 29 files OK.
- PAPER baseline PR #3: 558 Windows tests observed earlier by GPT Work. Not
  rerun in this documentation block. Do not add them to the research count or
  infer Windows remote CI from the successful Linux research workflow.
- PR #4 and #5 tests are author/reviewer reports unless their underlying run
  is retrieved. The PR chain remains open and unmerged at this observation.
- At 01:35 UTC a source already declared completion at 01:50 UTC. Retain the
  declared value with a quality flag; do not turn it into observed activity.
- The UI browser requests Notion login. WAIT-NOTION-VISUAL-001 blocks only
  authenticated visual QA, not connector reads/writes. Do not ask repeatedly.
- Existing GitHub/Notion connectors suffice. No extra plugins, credentials,
  paid services, public sharing, or trading sessions were enabled.
- Future web credentials stay server-side. The browser should receive only
  scoped sanitized records; never tokens, account secrets, or raw terminal logs.
- Start read-only. Task mutations, operation controls, and especially trading
  actions require separate authorization and validation; no UI click may bypass
  the deterministic trading gates.

## Acceptance tests for the future web assignee

1. Stable IDs deduplicate identical runs/PR events across retries.
2. Source failure and stale/future heartbeat render unknown/conflicting, not green.
3. Pagination and deleted/inaccessible records do not yield misleading counts.
4. UTC instants display correctly in America/Guayaquil without rewriting sources.
5. Human waits are recorded once; technical review does not spam the owner.
6. Every status/test/result links to its evidence and environment/commit.
7. Fixtures are isolated and visibly labelled, never mixed into production city.
8. Linked views preserve the existing backend and do not create parallel tasks.

Next: Claude reviews this handoff, assigns the web implementation owner and
decides risk-contract/integration work. GPT Work remains available for connector
integration and independent review without taking over claimed engine files.
