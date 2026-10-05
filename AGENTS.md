# AGENTS.md — Trading Intelligence AI

## Agents

| Agent | Role | Primary Focus |
|-------|------|---------------|
| **Trading Codex** | Core Engineering | Code, architecture, refactoring, tests, debugging, APIs, databases, GitHub, CI, security, performance, logging, error handling, automation |
| **Trading claude work** | Quantitative & Strategy | Quantitative analysis, mathematics, strategy, risk modeling, critical code review, complex research, result validation |

## Rules

### Coordination
- GitHub is the single source of truth for all code and technical decisions.
- Both agents MUST read `docs/CHECKPOINT.md` and recent commits before starting any work session.
- Avoid modifying the same files simultaneously. Use `docs/AGENT_COORDINATION.md` to claim files and tasks.
- When claiming a task, update `AGENT_COORDINATION.md` with: task, responsible agent, affected files, status.
- Use Pull Requests for non-trivial changes. Tag the other agent for review when cross-domain.

### Code Standards
- All code must include error handling appropriate to the failure mode.
- No hardcoded credentials, API keys, or secrets in code. Use environment variables.
- Tests are mandatory for risk engine, order execution, and position management.
- Type hints required for Python. Strict typing for TypeScript if used.
- Logging at appropriate levels: DEBUG for development, INFO for operations, WARNING/ERROR for issues.

### Trading Safety
- System MUST remain in PAPER mode until explicitly authorized for live trading.
- Claude NEVER bypasses the deterministic risk engine.
- No martingale or automatic risk increase to recover losses.
- No real money operations, fund movements, or withdrawal enablement without explicit owner authorization.
- Daily loss limits, position size limits, and exposure limits are non-negotiable.

### Credit/Token Management
- Use the cheapest effective tool for mechanical tasks (tests, linting, formatting).
- Don't repeat analysis already completed by the other agent.
- Read checkpoints and commits before spending tokens on context-building.
- If credits run out, leave `docs/CHECKPOINT.md` fully updated before stopping.

### Checkpoint Protocol
- Update `docs/CHECKPOINT.md` after completing any significant unit of work.
- Include: what was done, what's next, current blockers, test status.
- On "continue from last checkpoint" — resume immediately without re-analyzing from scratch.

### Review Protocol
- Either agent may review the other's work when it improves quality.
- Risk engine changes require review from Trading claude work.
- Architecture changes require review from Trading Codex.
- Security-sensitive changes require review from both agents.
