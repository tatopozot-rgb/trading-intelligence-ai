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


### 98. One year of data: the desk only wins in a bull market (2026-10-12/13)

**Owner's words:** "tú eres el líder, si no ganamos pues no tiene sentido, busca estrategias y olvida lo que yo dije y mis marcas, vamos mejorándolas con la práctica".

**What the leader did:**
- The live desk is now exactly `mesa_r3`: no 3% floor and no bull-run mode (PR #43).
- One research workflow (`research-run.yml`) and a shared protocol (`docs/research/PROTOCOLO.md`): 365+ days, walk-forward, real costs, results per quarter, and a comparison against `mesa_r3`.
- Three researchers: Quant (`research_mesa`), Tendencia (branch `research-tendencia`, PR #44) and Rotación (branch `research-rotacion`).

**Result.** Three independent replays of `mesa_r3` over 2025-10 → 2026-10 (1000 USDT per 30-day block, fees, slippage 0.02%, real funding) agree:

| Replay | Year | Max DD | Trades | Bear quarters | Bull quarter (jul–oct 2026) |
|---|---|---|---|---|---|
| Quant `research_mesa` (proven identical to `two_way_backtest`) | −53.2% | 73.7% | 715 | −39.7% / −40.9% / −13.8% | +52.5% |
| Tendencia | −53.1% | 70.3% | 743 | −45.7% / −36.3% / −11.9% | +49.8% |
| Rotación | −49.6% | — | 703 | −44.6% / −45.1% / −17.1% | +58.6% |

- BTC buy-and-hold over the same period: −17% to −24%.
- The desk loses more than BTC in every falling quarter. Its shorts lose too.
- Every earlier gain (the 30/60-day checks, the second-strategy window) sat inside the one bull quarter.
- Trade counts are higher than in the 37-USDT checks because, at 1000 USDT, minimum notionals no longer block entries.

**What does not fix it** (Quant):
- Exits: target 2.5–5R, other trailing settings and time exits all made it worse out of sample.
- Skeptic rules: the round-number rule subtracts in net (−43.2% without it, −53.2% with it).
- Sizing: fixed 2/5/10% gives the same result.
- 3x loses −92% to −94%. **3x is discarded, and practice 2 (3x) is cancelled.**

**Other strategies, out of sample over the year:**
- Trend (Donchian, EMA, TS momentum): all lose. The best, TS momentum, made −3.5%.
- Rotation over 12 coins: −75%.
- 1h mean reversion: −38.6%.
- Pairs: −3.2% (short sample).
- Top-30 rotation showed +108%, but it is not counted: the list was chosen with hindsight (survivorship bias).

**Leader decisions:**
- **No real-money futures** until a strategy passes the protocol: positive in 3 of 4 quarters, out of sample.
- Practice 1 (fictitious money) keeps running, for learning only.
- Next:
  - Quant tests a regime gate: trade only when BTC is in an uptrend (200/50-day mean), flat otherwise.
  - Tendencia tests two fixed setups, pre-registered on 2026-10-12, on the year before (2024-10 → 2025-10).
- The +58%/month goal is not supported by any evidence we have.

### 99. Practice gets a risk brake, a core BTC bot, an alarm and Telegram orders; carry and trend measured (2026-10-13)

**Owner's orders:**
- "busca estrategias ... estúdialo en la teoría".
- "si el mercado va a explotar ... me notifiques como loco hasta yo atender y aceptar la operación".
- "manejes esto como una empresa de trading".
- "detén en tal ganancia o que detenga ya".

**Evidence:**
- **Regime gates on the desk** (Quant, two years, `docs/research/mesa/`): no gate makes `mesa_r3` a winner. BTC above its 50-day mean, longs only, is the best brake:

  | Year | Without brake | With brake |
  |---|---|---|
  | 2025-26 | −65.5% | −7.4% |
  | 2024-25 (blind) | +17.6% | +78% |

- **BTC régimen** (Tendencia, pre-registered, 2020-26, `docs/research/tendencia/`): `btc_sma50` compounded ×9.4 against ×7.4 for holding BTC, with lower drawdown in 4 of 6 years. It lost −49% in 2022. A better way to hold BTC, not a bear-market earner.
- **Trend families, rotation, reversion, pairs:** nothing holds out of sample. The top-30 rotation result is survivorship bias; a point-in-time test is running.
- **Funding carry** (Quant, 2020-26, `docs/research/carry/`): +5.5% a year with a 1.6% max drawdown, but about 0% in the last 12 months. Below cash at a 3.75–4% Fed rate. Kept as a tool for when funding is high again.

**Built (practice only):**
- `regime_btc_sma: 50` in the desk rules, wired into the engine.
- `live/core_btc.py`, the Núcleo BTC bot.
- `live/alarma.py`: shock alarm, repeated until the owner answers, trades only on `ACEPTO <code>`.
- `live/ordenes.py`: `CIERRA <coin>` and `META <coin> <%|PRECIO p>` by Telegram.
- `docs/EMPRESA.md`: company plan, with the gated path to third-party money (legal advice first; COIP art. 323).
- Daily market intelligence and theory routine, written to `docs/inteligencia/`.

**Still no real money:** no strategy passes the protocol in every regime.

### 100. Trend Preregistro 3 measured; its rule joins the core BTC practice (2026-10-13)
- PR #49: "BTC above both its 50- and 200-day means" **does not pass** (−4.8% in 2021-22; single losing quarters in bull years).
- Still, it had the smallest drawdowns of the five variants, and the best growth from 2020 to 2026 (×9.56, against ×7.37 for holding BTC).
- It is the best of 5 variants on data already seen, so there will be no more history re-tests. It runs forward on paper only: `core_btc --medias 50,200 --estado live_runs/core_btc/paper_50_200.json`, next to the 50-day rule.
- Open (desk owner): why 105 entries were skipped for minimum notional in the 2025-10-12 window, and 190 in 2025-08-08.

### 101. Núcleo BTC can run with real money on Binance Spot (2026-10-13)
- The owner, 2026-10-13: "mañana ya conecto las claves de binance y xm y pues a darle lider".
- The leader's decision: the desk (`mesa_r3`) stays in practice. It lost −53% over 2025-26 and works only in bull markets.
- The only rule that may touch real money is the Núcleo BTC (BTC above its 50-day mean, otherwise cash). It runs on Spot, without leverage, inside the limits the owner already approved in `config/live_limits.json`:
  - One position is at most 40% of the session capital.
  - At a 35% loss the session sells and stops.
  - It warns 2 USD before that.
- `core_btc --real --capital N` uses the Spot transport in `live/binance_live.py`:
  - The key must have IP restriction and no withdrawals.
  - Every order is journalled, and an unclear order is never resent.
  - A STOP_LOSS sell rests on Binance 15% under the entry.
- Only Claude local starts it, after the owner's written phrase. XM stays DEMO.

### 102. Sentiment measured: no useful prediction; the size tilt is removed (2026-10-13)
- Quant (`docs/research/sentimiento/`):
  - The Skeptic's sentiment rule (−0.5) never fires: the top-traders ratio is almost always above 1, so the score leans bullish.
  - Agreement and the 24 h result are slightly *negatively* related (Spearman −0.04/−0.05).
  - Funding alone has no direction (0.003, 2020-26).
  - The saturated-funding veto is a separate rule and stays.
- The leader's decision: the +0.2 × sentiment tilt on the trade size is removed, in live practice and in the backtest. The mood still feeds the Skeptic and the journal. The inert rule stays until a normalized top-traders ratio is researched (not started).

### 103. Real money: Binance Futures in USDT and XM; no coins held on Spot; Compliance agent (2026-10-13)
- **Owner's decision on real futures:** "futuros reales es la única forma de llegar a saberlo ... de acabarse el dinero o perderlo sigues alimentándote".
  - Real Binance USDⓈ-M Futures starts with his phrase and amount written to Claude local.
  - It runs with the approved `config/futures_limits.json`: 1x, isolated margin, max 50% per position, loss limit 45%.
  - The regime brake stays on. The leader advised against it, citing the −53% of 2025-26.
- **Owner's rule on Spot:** "debes dejar todo como usdt xq btc no puedo no vender".
  - Small Spot leftovers fall below Binance's minimum and can't be sold.
  - So **every real-money result ends in USDT**: no coins held on Spot.
  - `core_btc --real` (Spot) is not used. The Núcleo BTC keeps running in practice only.
- **XM:** the bot is DEMO-only by design: it refuses a real account. Real XM needs three things:
  - the demo working on the owner's account first;
  - an XM real-money transport;
  - XM limits approved by the owner.
- **New agent:** `.claude/agents/compliance.md` reviews the technical and legal traps before any real-money plan: minimums and dust, settlement in USDT, account modes, costs, keys, Ecuadorian law, and the owner's understanding.

### 104. Owner's capital plan; XM sizing trap; practice at 50 USDT (2026-10-13)
- **Owner's plan:**
  - Start real money with 50-100 USD and let it compound; he will rarely withdraw.
  - If results show within a year, add about 1,000 USD.
  - He prefers XM over Binance because of Binance's fees, and XM sometimes offers deposit promotions.
- **The XM trap (Compliance), why XM real waits:**
  - XM's minimum is 0.01 lot of a 100,000-unit contract: about 1,170 USD notional on EURUSD and over 2,000 USD on gold.
  - With 50-100 USD, that is 12-40× the account, against the bot's cap of 2× effective leverage per position (`xm_mt5.EntryCaps`). Every entry would be refused unless leverage is accepted.
  - The spread on that forced size (about 0.16 USD per EURUSD trade) is also about 0.3% of a 50 USD account per trade. Binance's 0.05% per side on a right-sized position costs less.
  - XM becomes viable at 1x near 1,000 USD, which fits his one-year plan, or sooner with a micro-lot account type if XM offers one to him. Not verified.
  - Deposit bonuses carry conditions and are not counted as capital.
- **Practice:** practice 1 moves to 50 USDT fictitious, mirroring the plan. An XM MT5 DEMO ("Demo Bot", 1:1, 1,000 USD virtual) is being created for connection and learning.

### 105. XM demo live; regime brake fixed on XM; GPT audit ordered via Notion (2026-10-13)

- **XM DEMO:** Local connected the hedging demo account (1,000 USD virtual). A test order on ETHUSD opened and closed (cost 0.21 USD virtual). `xm_auto` runs every 10 min (Windows task TradingIntelligence-XMDemo) on ETHUSD and OILCash, the only two of 23 symbols that pass the unchanged caps. The rest fail on minimum-lot margin, effective leverage above 2x, or spread above 0.15%. It needs MT5 open with Algo Trading on.
- **Fix:** the regime brake asked XM for `BTCUSDT`. XM calls it `BTCUSD`, so the brake read nothing and never acted. `XmBroker.candles` now maps the name (`XM_NAMES`). Test: `test_the_regime_brake_reads_btc_under_xms_own_name`.
- **Hedging account:** works as is. Closes and stop moves go by position ticket, and only this bot's MAGIC is touched.
- **GPT:** given a one-pass, read-only audit of the futures limits, `two_way.py` and `binance_futures.py` on the Notion Task Board (agent "Trading Codex"). No code, no keys, no real money.

### 106. More XM demo agents on the same account (2026-10-13)

- **Owner, 2026-10-13:** "me gustaria mas agentes que hagan mas operaciones en XM". He has also said the demo money may be lost while learning.
- **What changed:** `xm_auto --agente NAME` runs another agent on the same DEMO account. Each agent has:
  - its own MT5 magic number (`agent_magic`), so it sees and closes only its own positions;
  - its own state folder (`live_runs/xm_auto_<name>`);
  - its own Telegram name ("🧪 XM DEMO · NAME (dinero virtual)").
- **New options:** `--margen-max` and `--spread-max` set that agent's entry caps.
  - The defaults are unchanged (20% of free margin, 0.15% spread, 2x effective leverage), and so are `config/*_limits.json`.
  - The looser values are for DEMO learning only. XmDemoTrader still refuses a real account.
- **Agents ordered:**
  - **Operador XM:** ETHUSD and OILCash on the default caps.
  - **Cripto:** XM's other crypto symbols, spread up to 1.5% and margin up to 40%. The wide spreads are part of the lesson: they show what costs eat.
  - **Índices:** US500Cash, AUDUSD and BTCUSD, margin up to 90%. In practice that allows one position at a time on a 1:1 account.
- **Unchanged:** the regime brake (longs only while BTC is above its mean), the event brake, the loss limit of 45% and the 3-position cap apply to every agent.

### 107. Two new agents; Agent City becomes a live star map (2026-10-13)

- **Owner, 2026-10-13:** "tienes la libertad de crear agentes… contrata… que la ciudad no este estatica tenga logica… media espacial".
- **`verificador`:** checks that each Telegram notice matches the journals and state files. That covers the bot's name, real or fictitious money, the numbers, the reason given, and anything missing. It reads files only.
- **`maestro-xm`:** reviews the three XM demo agents each day. It reports activity, what spread and swap cost, whether the brakes acted, and one lesson. It reads files only.
- **Who runs them:** Claude local runs both daily, because the journals live on the owner's PC.
- **Agent City artifact:** now an animated star map.
  - Stations are bots; ships are agents.
  - Each ship flies only the route of the work it really does.
  - Ships turn back at the real-money shield.
  - The data is still a snapshot that the leader republishes when something changes.
- **Artifact review:** the earlier version had stale facts, now fixed:
  - the practice desk was still shown with 30 USDT, though it moved to 50;
  - the futures key was still shown as pending;
  - the 3x practice was missing;
  - the XM agents and their events were missing.
