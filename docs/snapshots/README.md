# Capturas de líderes de Copy Trading (fuente: app de Binance, a mano)

1. Llena una copia de `docs/templates/copy_trading_capture.template.csv`: una fila por líder, tal
   como lo muestra la app. Incluye también los que **dejaron de liderar** (`active = no`).
2. Conviértela: `python -m trading_intelligence.copy_trading.capture captura.csv --captured-at
   2026-10-08T15:00:00-05:00 --out docs/snapshots/binance_app_2026-10-08.json`.
3. Súbela al repo. El workflow "Trader review" la evalúa solo y publica el ranking en Actions.
4. `followed.json` lista a quién copias de verdad en la app: `{"followed": ["<trader_id>"]}`.
   La revisión te dice si mantenerlos o dejar de copiarlos (en rojo si es urgente).

Nunca pongas aquí claves, contraseñas ni datos de la cuenta. Captura una vez por semana: el
aprendizaje necesita varias capturas para decir si la selección acierta.
