---
name: revision-futuros
description: Daily review of the futures desk (practice and real). Use when asked to review how the futures bots traded, or by the leader's daily routine.
---

# Daily futures review (Claude Leader)

1. `git fetch origin local/practica main`. Read the newest `docs/shadow_futures/<date>.md|json` on `local/practica`.
   From Monday on, also read the real account's report (percentages only).
2. Read Claude local's transcript for errors, crashes, uncertain orders, kill-switch events and owner orders.
3. Check, in order:
   - **Bugs:** a trade the engine should not have opened, a missing stop, a duplicate order, a Telegram message that does not match the account. Fix with a test, open a PR, and tell Local to pull.
   - **Limits:** the real loss per trade, positions and loss limit stay within `config/futures_limits.json`.
   - **Learning:** add one line to this week's note `docs/aprendizaje_futuros/<YYYY>-W<week>.md`, as a hypothesis or as evidence. With fewer than 30 trades in a group, write "ruido".
4. If GPT Work left an analysis (issue `Análisis futuros ...` or `docs/aprendizaje_futuros/gpt-*.md`), take the useful parts into the week's note, and into the code only after the Monday backtest confirms them.
5. Message the owner (Spanish, ≤ 8 lines) only if something is material: a real trade, a warning, a stop, an error, a proven improvement, or a decision only he can make.
6. Never change `config/futures_limits.json` or `config/live_limits.json` without his written approval. No martingale.
