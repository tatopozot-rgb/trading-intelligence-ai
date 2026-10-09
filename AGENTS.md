# AGENTS.md — Trading Intelligence AI

## Project Goal (corrected 2026-10-06 — read this before anything else)

PAPER mode, backtesting, walk-forward, and shadow/live-data validation are
**internal validation gates, not the destination**. The actual goal is a
complete, robust, deployable Trading Intelligence system prepared for real
operation. PAPER being "validated enough" is a milestone to pass through,
not a stopping point — immediately continue into LIVE-readiness
infrastructure (real adapters, auth, LIVE config, execution gates, dry-run,
shadow mode, deployment prep) once it is.

**The only human gate before real trading is `LIVE_ACTIVATION_APPROVAL`** —
asked exactly once, when architecture, risk, quant, security, tests, CI,
crash/restart recovery, persistence, cross-agent review, and documentation
are all genuinely done. Until that point, build everything that does not
move real money without stopping to ask or to hand the owner a roadmap —
execute. Drafting and refining this report is itself a job for Trading
Claude-Work when the system is actually ready, not earlier.

No martingale, no revenge trading, no automatic risk increase after a loss,
ever. No strategy is declared validated without surviving the full
STRATEGY_VALIDATION_FRAMEWORK.md gate on out-of-sample data — "no se opera"
(don't trade) remains a valid, correct outcome when no real edge exists.

## Agents

There are exactly **three** executors on this project. "Trading Claude Work"
in any older document refers to the real ChatGPT Work agent below — never
to a plain chat session.

| Agent | Role | Primary Focus | Environment |
|-------|------|---------------|-------------|
| **Trading Claude-Work** | Quantitative & Strategy (real ChatGPT Work) | Cross-review, architecture, risk, quantitative analysis, research, general coordination, Notion Mission Control, connectors, review of important PRs | ChatGPT Work |
| **Trading Codex — Core Engineering** | Engineering (this agent, cloud) | Implementation, code, tests, debugging, GitHub, CI, refactoring, infrastructure, APIs, persistence, cloud execution | Claude Code, cloud container (no access to the owner's local PC) |
| **Claude Code local** | Local execution (PowerShell on the owner's PC) | Local code inspection, PowerShell, Python, Git, local tests, changes requiring the Windows filesystem, commit/push, real validation on the PC | Claude Code, local on `C:\Users\tatop\trading-ai` |

Do not attribute work to "plain chat" — every contribution belongs to one of
the three agents above.

## Rules

### Coordination
- GitHub is the single source of truth for all code and technical decisions. Notion is Mission Control (coordination view, not technical authority).
- **Shared memory in Obsidian (owner's order, 2026-10-09).** Every agent (Claude local, Claude Leader, Quant, GPT Work) reads the vault note `09 Checkpoints/Memoria viva.md` and then `docs/CHECKPOINT.md` before starting. At the end of every work block it records what it did, what it decided and why, what is pending, and any new owner order. Claude local writes the vault directly; the cloud agents write `docs/CHECKPOINT.md`, and Claude local copies it into the vault daily. GitHub wins on any conflict. Never put secrets in the vault; balances may go there, never in the public repo. Details: `docs/AUTOMATIZACION.md`.
- All three agents MUST read `docs/CHECKPOINT.md` and recent commits/PRs/issues before starting any work session.
- Avoid modifying the same files simultaneously. Use `docs/AGENT_COORDINATION.md` to claim files and tasks. Check who holds a claim before editing.
- When claiming a task, update `AGENT_COORDINATION.md` with: task, responsible agent, affected files, status.
- Use Pull Requests for non-trivial changes. Tag the relevant agent for review when cross-domain (e.g. risk/architecture changes → Trading Claude-Work; local-filesystem changes → Claude Code local).

### Code Standards
- All code must include error handling appropriate to the failure mode.
- No hardcoded credentials, API keys, or secrets in code. Use environment variables.
- Tests are mandatory for risk engine, order execution, and position management.
- Type hints required for Python. Strict typing for TypeScript if used.
- Logging at appropriate levels: DEBUG for development, INFO for operations, WARNING/ERROR for issues.

### Trading Safety
- System MUST remain in PAPER mode until explicitly authorized for live trading.
- No agent ever bypasses the deterministic risk engine.
- No martingale or automatic risk increase to recover losses.
- No real money operations, fund movements, or withdrawal enablement without explicit owner authorization.
- Daily loss limits, position size limits, and exposure limits are non-negotiable.
- No historical backtest result validates profitability or a strategy for live use. Negative diagnostics stand until re-validated with evidence.

### Credit/Token Management
- Use the cheapest effective tool for mechanical tasks (tests, linting, formatting).
- Don't repeat analysis already completed by another agent — check GitHub/Notion/checkpoint first.
- Read checkpoints and commits before spending tokens on context-building.
- If credits run out, leave `docs/CHECKPOINT.md` fully updated before stopping.

### Checkpoint Protocol
- Update `docs/CHECKPOINT.md` after completing any significant unit of work.
- Include: what was done, what's next, current blockers, test status, exact next step.
- On "continue from last checkpoint" — resume immediately without re-analyzing from scratch.

### Review Protocol
- Any agent may review another's work when it improves quality.
- Risk engine and fill-semantics changes require review from Trading Claude-Work.
- Architecture changes affecting the real local system require review from Claude Code local (it has ground truth on the actual running program).
- Security-sensitive changes require review from more than one agent.

### WAITING_FOR_USER
- If a question to the owner is already recorded and unanswered, do not repeat it. Keep exactly one record per open question and continue other work.
- Only escalate to WAITING_FOR_USER for things only the owner can decide (credentials, 2FA, real-money authorization, login) — not for ordinary technical decisions.
