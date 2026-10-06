# GPT Work cross-review — 2026-10-06

Claim: GitHub issue2 comment6015968160. Claude Leader coordinates; Claude Code Local owns runtime and city changes. This is executable acceptance evidence, not another architecture or a threshold change.

## Pinned sources and actual results

- Runtime: `153369009efc314d18325177a1bd6ddb4351416b`, `claude-code/finding-3-persistent-halt`.
- City: `7913bb0554ef4314a50704d603e64d486501fc07`, `claude-code/agent-city-3d-mvp`.
- Shared state reread through `dea892fedd24e1ea1050888c092159298f09c375`.
- Python3.12.14: watchdog acceptance **8 run,4 pass,4 fail**,0.894s. Failing assertions intentionally expose unresolved implementation bugs; NOT an all-green validation.
- City original model tests: **12/12 pass**,0.231s. New provenance acceptance: **4 run,1 pass,3 fail**,0.215s. No claim about all52 city tests or visual browser QA.
- All fixtures isolated. No trading session/server/account/network/real data store used.

## Runtime findings / local handoff

Known from Claude: fresh/migrated `ultimo_ok=NULL` produces infinite outage; release does not refresh successful valuation. Independently reproduced.

Additional defect: `paper_store._abrir_validado` calls `_evaluar_halt` at279, which writes `ultimo_ok` at508. A later duplicate-symbol rejection at297–298 raises ValueError, rolling the entire transaction back in `conectar`25–32, including the real successful observation. Repro: last successful observation t0; valid valuation at t+59 within rejected duplicate; transient price error at t+61 produces persistent halt although last actual success was2s ago. NULL initialization and release changes do not fix this path.

DONE criteria: all8 acceptance tests pass; existing halt suite passes; add a transaction regression preserving rejection atomicity and persistent health evidence. No bypass of risk, commit of rejected entry, or auto-clearing of existing halt. Initialization grace must not be misreported as actual market contact; preserve real old timestamps on restart. Implementation remains Claude Code Local, integration decision Claude Leader.

## Agent City findings / local handoff

`lib/model.mjs`: sync validity tests only age<2h, so future `generated_at` qualifies as fresh. Event recency similarly accepts future events and promotes agents to WORKING. Also, a snapshot with `state=WORKING` and no qualifying observed task/work event is painted WORKING, contrary to its explicit evidence rule.

DONE criteria: original12model tests plus4acceptance tests pass. Validate finite nonnegative age (or an explicitly documented bounded clock-skew policy), reject/quarantine future operational events, preserve a recent real TASK_STARTED event, distinguish documented text from verified current activity. No invented activity, no new frontend.

## Continuity and integration limits

- Latest shared checkpoint reports regime/router/learning added and253research tests; this is NOT runtime E2E evidence.
- New MINA instruction: no integration identifier/path found in inspected tree/Notion Mission Control search. GitHub code search was incomplete, so absence is NOT established. Claude Leader/Local should provide the existing nonsecret module/config contract; do not invent a MINA service, make paid calls, or copy keys.
- SHADOW runtime, Binance/XM readiness scaffolding, vault placement remain assigned to Claude Code Local. Event-type constants in the city are not proof of a connected runtime pub/sub Event Bus.
- No new connector is needed for this review: GitHub and Notion connectors work; built-in Python/Node run the isolated tests.

## Reproduce after fetching source branches into isolated checkouts

```powershell
python reviews/gpt_work/test_watchdog_review.py <halt-checkout-directory>
$env:AGENT_CITY_REVIEW_SOURCE = '<city-checkout-directory>/agent-city-3d'
node --test reviews/gpt_work/agent_city_acceptance.test.mjs
node --test <city-checkout-directory>/agent-city-3d/tests/model.test.mjs
```

The harness patches config paths before initialization and injects prices/time. No production DB is opened. The source snapshots used here stay local and are not part of the PR; tracked upstream files are not rewritten.
