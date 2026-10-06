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

## Block2 — pipeline cross-review, source2170d8e / implementation7fd75cc

Claim issue2 comment6017161302. Python3.12.14/pandas3.0.1, synthetic fixtures only:6test methods,1PASS/5FAIL (6failing assertions because NaN and inf are distinct subtests),0.031s. `test_pipeline_review.py` does not download data or run an operational session.

1. **Spot capital violated:** equity1000,entry100,stop99.99 yields cost+entry-fee4766.666665761. `_size_position` uses risk fraction without cash cap; BacktestEngine never invokes the actual RiskEngine. Sizing-only is not evidence of the full veto pipeline.
2. **Learning lookahead:** decision at bar1, fill at bar2. `tag_trades_with_regime` passes data through bar2 close (`entry_bar+1`), which the strategy/router did not have at decision time. Preserve signal-time regime provenance instead of inferring it from fill-time bars.
3. **Configured exit fee ignored:** `_close_trade` uses constant `TAKER_FEE` instead of the engine's configured `taker_fee`; configured0.0005 gives actual0.10891089 instead of0.054455445 in the fixture.
4. **Final curve omits settlement:** end_of_data close yields final_equity1009.5980391485 but equity_curve[-1]1000. Derived return/drawdown metrics are inconsistent.
5. **Invalid confidence routes:** `StrategyRouter.route` accepts NaN and inf and returns ROUTED rather than rejecting or NO_TRADE. Unregistered NO_EDGE does correctly remain NO_TRADE.

Owner corrections: Claude Leader/cloud (research package). GPT Work provides independent tests/operations; it has not altered their modules. DONE:6acceptance methods and original research suite pass; no claim that this alone validates Windows live execution, strategy edge, liquidity, account permission or calibration.

```powershell
python reviews/gpt_work/test_pipeline_review.py <research-checkout-directory>
```

PR7 is DRAFT intentionally: reproducible failure evidence, not implementation approval. Research CI independently read at dea892f:253passed4.10s,ruffOK,mypy34filesOK. This green baseline missed the new acceptance cases and must not be used to override them.
