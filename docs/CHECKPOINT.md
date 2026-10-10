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
