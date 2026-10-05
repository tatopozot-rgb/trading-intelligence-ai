# AGENTS.md — Trading Intelligence AI

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
- GitHub is the single source of truth for all code and technical decisions. Notion is Mission Control (coordination view, not technical authority). Obsidian is planned as later technical memory.
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
