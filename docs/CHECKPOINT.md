---
type: checkpoint
tags: [trading-intelligence, checkpoint]
status: living
---

# Checkpoint — Trading Intelligence AI

Start with `docs/ESTADO_ACTUAL.md` (the current state) and Obsidian "Estado actual". This file keeps
only the latest work blocks. The history up to 2026-10-10 (sections 1–90) is in
`docs/archivo/CHECKPOINT_historial_hasta_2026-10-10.md`.

### 91. Futures with the trading desk; risk 1–15%; cleanup (2026-10-10)

**Owner's words, three messages, ≈06:35–07:30 UTC:**
- "Los limited aprobados 1% de riesgo esta mal debe ser por lo menos 1 al 15% estaba determinado y el máximo por posición hasta el 50% ... necesito que hagas una limpieza ... como regla deben revisar obsidian y git para no revisar todo el hilo y solo donde se quedaron, el telegram no puede enviar cosas falsas debe estar verificado 2 veces al final en la cuenta, igual ya puede ver top traders de futuros en binance ... si se abren 2 posiciones cada uno tiene un bot diferente, lunes conectamos y volvemos a operar con dinero real ... debemos integrar x como bróker".
- "me gustaría un bot que este revisando 24/7 qué de alerta de operación a otro bot, esto no retira los horarios que tenemos de revisión".
- The "AI Trading Desk" design (Scout, News, Sentiment, Charts, Skeptic, Chief) "con la lógica de nuestro proyecto en cuestión a porcentajes de uso y riesgos", with this cadence: "de 7 a 10 am y de 5 a 7 ... deben trabajar sin parar y fuera de ese horario cada 5 minutos ... cuando se abra una operación revisar cada 30 segundos ... o tener un bot avisando de esa operación cada 2 minutos".

**Built:**

*Limits (`config/futures_limits.json`, approved with the quote):*
- Risk is 1–15% of equity, scaled by the signal's quality. It depends only on the market, never on past results.
- Each position is at most 50% of equity, and all positions together fit the free margin.
- Leverage 1x. The worst single loss is 7.5% of equity.

*Signals (`strategy/two_way_signals.py`):*
- The top traders' long/short position ratio is now an input.
- A quality score from 0 to 1 combines the regime confidence, the 1h trend and the top traders.
- New default variant: `tendencia_rango_1h_top`.

*Desk (`live/desk.py`):*

| Agent | Built |
|---|---|
| Scout | Flags volume ≥2x or a move of ≥1.5% in 15 min, 24/7, and triggers an immediate evaluation by the Chief. |
| News | Reads CoinDesk and Cointelegraph RSS: links only, context only. |
| Sentiment | Combines funding, top traders and Fear & Greed into a score. |
| Skeptic | Applies `config/desk_rules.json`: R:R ≥ 1.5, no stop near a round number, no crowded funding, no strongly opposed sentiment. Every veto is journaled and scored later. |
| Journal | Markdown for Obsidian. |

*Engine (`live/two_way.py`):*
- Cadence: a decision every 30 s inside the windows, every 5 min outside.
- One bot per position. It checks the position every 30 s, trails the stop and reports every 2 min.
- Opened, closed and server-closed messages go out only after two account reads agree.
- Kill switch: 3 API failures in a row stop new entries.

*Binance (`live/binance_futures.py`):*
- Reads funding (`premiumIndex`) and top traders (`topLongShortPositionRatio`).
- A free-margin cap limits new positions.

*Backtest:*
- The new sizing.
- Real top traders (daily metrics) and real funding (monthly) from data.binance.vision.
- Variant `mesa` adds the vetoes and scores each one.

*Subagents in `.claude/agents/`:* scout, news, sentiment, charts, skeptic, chief. They analyze the journal and research. They never trade.

**Cleanup:**
- `docs/ESTADO_ACTUAL.md` is the single entry point.
- The obsolete docs (Spot pilot, old handoffs, Agent City, superseded designs) and the long checkpoint moved to `docs/archivo/`.
- `AGENTS.md` now carries the reading rule.
- Obsidian: Claude local rewrote `Memoria viva` with "Estado actual" on top and a short log below; everything older is kept, untouched, in `Memoria viva - Archivo` (08:29 UTC).
- Notion: a "✅ Estado actual — 2026-10-10" block now sits at the top of the "Trading Intelligence AI — Operations Center" page and marks everything below it as history.

**Found by Local at 08:28 UTC:**
- Spot has no USDT left: the owner moved it to Futures. Only dust remains (BTC ≈5.8 USDT, ETH/SOL/AVAX ≈0.4).
- The Spot operator still runs, but any BUY would be refused for lack of balance. Local stops it when the owner writes "para".

**Monday:**
- The owner connects the new futures key (`BINANCE_FUTURES_API_KEY` / `SECRET`) and XM.
- Local runs `--una-vez` and then real, with his phrase.

**Tests:** desk 9, engine 17, futures 20, backtest 5, XM 11 and 9. Full suite in CI.

### 92. The new model measured on real data; PR #35 merged (2026-10-10)

- PR #35 merged (desk, risk 1–15%, bots, cleanup). CI timeout raised from 10 to 25 min: the suite passed in 9:42 but the job hit the cap.
- 30-day run (2026-09-10 → 10-10, 37 USDT, fees and real funding): `mesa` (what runs live) +6.39 USDT (+17.3%) in 25 trades, 64% hits, max drawdown 12.7%, average risk 12.9%, all longs. `tendencia_rango_1h_top` +8.8% in 19. `tendencia_rango_1h` −6.3% in 138; `tendencia_rango` −24%; `regimen` −45%.
- Small sample: both positive variants have fewer than 30 trades. The report's verdict now names them instead of saying "none won".
- Skeptic: 1040 vetoes avoided a loss, 1565 blocked a gain, 5124 had no result in 24 h. Its rules are kept for now and reviewed with more data.
- Local told: update to main; Monday steps unchanged.

### 93. Owner's reminders (2026-10-10)

- Notion trading board: build it once Futures runs stable for a few days, from 2026-10-15. The leader must bring it up: "tienes que recordarlo porque si no yo me olvido". A reminder is scheduled.
- Risk: the owner keeps his numbers: "1% no es nada, debe ser 15% y los porcentajes que yo ya puse". The config already says 1–15% by signal quality; nothing changes. "lunes con todo".

### 94. Stopped by the owner (reported by Local, 2026-10-10)

- Spot operator: stopped with "Para" at 08:44 UTC. Nothing was sold or moved; the session is STOPPED.
- Market watcher: the owner wrote "Deten vigilante". Task `TradingIntelligence-Vigilante` is disabled, not deleted, so there are no market or brutal-bull alerts.
- Neither comes back without the owner's word to Local. Reports, Memory and Reanudar stay active.

### 95. Learning to manage futures: practice 30 + 30, risk scenarios, daily loop (2026-10-11)

**Owner's words:** "tu última tarea con dinero en las dos cuentas es aprender a manejar el mercado futuros ... en un futuro puedas arriesgar por operación hasta el 15-30% ... Eres el gerente ... empezar con el valor que tenemos Binance 30 y XM 30 ... Después de conectar XM, empezamos con dinero real al 100%, con lo aprendido."

**Built:**
- **Backtest:**
  - Reports the *real* risk per trade (the loss at the stop after the caps) next to the risk the signal asks for.
  - New risk scenarios for the desk: 1x/50% (live), 3x/150%, and 5x/250% with 15–30% risk.
  - A stop beyond the liquidation price is refused.
- **Practice account:**
  - Paper trades record their R multiple.
  - Telegram labels them "🧪 SIMULADO (dinero ficticio)".
  - The status report comes every 30 min, not every 2.
- **`live/shadow_report.py`:** the daily practice report (win rate, net, expectancy in R, profit factor, drawdown, by symbol/side/exit, vetoes).
- **Docs and agents:**
  - `docs/APRENDIZAJE_FUTUROS.md`: roles, the daily loop, and the evidence gate for raising risk toward 15–30%, which needs the owner's written approval.
  - `docs/prompts/GPT_WORK_FUTUROS.md`: GPT Work's analysis prompt.
  - `.claude/skills/revision-futuros`: the leader's daily review.

**Finding the owner must know:**
- At 1x with a 50% position cap, "risk 15%" is nominal: one trade loses at most 7.5% of the account, usually 1.5–4%.
- Real 15–30% needs 3–5x leverage.
- Two losses in a row at 30% leave 49%, already past the 45% session limit. With 64% hits, P(two losses in a row within 25 trades) = 93%.

**Then the owner added:** "si algún día alguna moneda se va en alza debe dejar el trade de largo ... arriesgar algo no todo ... en cada operación intente tener un profit del 3% al 5% ... después lo controles tu".

**Built for it:**
- `desk.shape_target`: keeps the take profit within 3–5% of the entry.
- `desk.rally`: flags a coin up ≥25% in 14 days, above its 20-day mean and still rising.
- The engine keeps a bull-run long open:
  - its target is +50%, so only the trailing stop closes it;
  - a 5-minute flip does not close it;
  - it takes the usual risk.
- The backtest compares `mesa` (live), `mesa_sin_alcista` and `mesa_libre` (the 2026-10-10 desk).
- **Caveat:** with the Skeptic's 1.5:1 rule, a 5% cap leaves room only for stops of 3.3% or less. The Monday run decides whether the band stays.

**Tests:** shadow report 2, backtest 8, futures 20, engine 20, desk 10.

### 96. Monthly goal, Telegram only verified, watcher back (2026-10-11)

**Owner's words:**
- "Si 5% máximo por operación estaria mejor a gran escala, pero que si intente ganar sin parar no por operación si no diariamente hasta cumplir una meta me dual de que se yo 5k dependiendo el valor después depositado".
- "activa vigilante para futuros nuevamente y que el bot de telegram envíe solo cosas ciertas revisadas, suele enviarme cosas no revisadas en los brokers".

**Built:**
- **Monthly goal:**
  - `profit_target_pct` (58) now counts from each month's starting equity.
  - At the goal everything closes; trading resumes on the 1st of the next month.
  - `monthly_goal_usd` lets the owner set the goal in dollars after a deposit.
  - Recorded in `config/futures_limits.json` with his quote.
- **Telegram only verified:**
  - The engine has `notify` (Telegram) and `chatter` (console and journal).
  - Scout alerts, Skeptic vetoes and stop moves are chatter.
  - Each position's status report goes out only after two account reads.
  - Warnings, the loss stop and the goal need a second equity read that agrees.
- **5% max per trade:** read as the take profit, which keeps the 3–5% band. Risk stays 1–15%.
- **Market watcher:** reactivation asked of Claude local with his words.

**30-day real-data check, 2026-10-11** (22–25 trades per desk variant, so noise-level):

| Variant | Result | Max drawdown |
|---|---|---|
| no band (mesa_libre) | +18.7% | 12.7% |
| 3–5% band | +6.1% | 11.8% |
| band + bull-run mode | +4.2% | 15.3% |

- **Real risk:** about 2% average, about 5% max.
- **Risk scenarios:** 3x gave +57.8% (goal reached, 18% drawdown); 5x at 15–30% risk gave +59% (28.7% drawdown).
- **Leader decision:** `target_max_pct` is off and the 3% floor stays. The bull-run mode stays, for rare big runs; it had only 4 entries in this window. The band keeps being measured as `mesa_meta_3_5`.

### 97. Reward that pays the risk: target at 3R; a 3x practice account (2026-10-12)

**Owner's words:** "replantea la ganancia que recompense el riesgo con tus cálculos analizados y empieza a operar así ... aprender como operar con más riesgo".

**Measured** (fees, real funding, 37 USDT, 1x):

| Variant | 60 days | Max DD | Trades | 30 days | Max DD |
|---|---|---|---|---|---|
| mesa_r3 (target 3R) | +50.6% | 9.1% | 50 | +29.9% | 6.7% |
| mesa_libre (market target) | +57.8% (hit the monthly goal) | 18.0% | 47 | +25.0% | 12.7% |
| mesa (3% floor + bull-run) | +48.8% | 17.0% | 45 | +16.1% | 16.3% |
| mesa_r2 / mesa_r1_5 | +25.5% / +32.1% | 13.4% / 9.1% | 45 / 31 | +14.6% / +8.1% | 8.5% / 8.9% |

**Decision:**
- `config/desk_rules.json` `target_r: 3`. About the same gain as the market target with half the drawdown, and more in the last 30 days.
- It also ends the practice account's 1.20:1 vetoes: no trade on its first day (report 2026-10-12: 0 trades, 11 vetoes that blocked a gain).
- The 3% floor and the bull-run mode stay. The bull-run mode cost about 9 points in both windows, but with only 2–4 entries.
- A second practice account at 3x, position max 150%, with its own diary and report (`docs/shadow_futures_3x/`). Practice only; real money stays at 1x.

**Also:**
- Quant: the first weekly two-way PAPER run is green: 11 longs and 2 shorts, starting 2026-10-12.
- Local: no new messages since 2026-10-11 16:10 UTC. The owner confirmed that Telegram works.

