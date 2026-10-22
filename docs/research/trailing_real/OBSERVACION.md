# Observación en práctica: trailing desde 2R y sin cierre por señal

Preregistro escrito el 2026-10-22, antes de arrancar. Lo decidió el Líder el 22-10.

## Arranque

Arrancó el 2026-10-22 a las 02:07:56 UTC (21:07:56 de Ecuador) desde londres-wt (main 07b3045). La tarea es TradingIntelligence-Practica2R, cada 10 minutos, y el estado queda en `xm-wt\live_runs\futures_auto_2r\shadow`. Sus avisos dicen "PRÁCTICA SIMULADO · trailing 2R · sin cierre por señal".

## Por qué

En las dos prácticas de futuros y en el bot real, ninguna operación ganadora llegó a su meta, desde el inicio hasta el 21-10. Las ganadoras salen por el stop que sigue la ganancia (desde +1R, a R/2 del precio) o por una señal contraria. Las perdedoras salen enteras (−1R). Eso va contra el estilo que eligió el dueño: pérdida chica, ganancia grande.

## Lo que ya se probó

Quant corrió el backtest de futuros del bot real (PR #127, fila 380 de `docs/research/REGISTRO_PRUEBAS.md`, N=297). La prueba fue un trailing desde 2R, sin cierre por señal contraria.

- **NO PASA.** Le gana a la mesa en los dos años, pero el Sharpe deflactado 2025-26 es 0,003 y el listón es 0,95.
- Mejora al real tal como está: +64 y +11 puntos de neto, y 10 y 3 puntos menos de caída.

Por eso el bot real no cambia. Esto es solo una observación en práctica.

## Qué corre

- **Una práctica nueva y paralela.** No reemplaza la práctica 1x actual, para no perder su historia.
  - Cuenta simulada de 50 USDT, igual que la práctica 1x. Precios reales de Binance.
  - Mismas monedas, señal, riesgo y límites que la práctica 1x (`config/futures_limits.json`, sin cambios).
- **Solo cambian dos reglas de salida:**
  1. El stop empieza a seguir la ganancia en +2R, no en +1R. Sigue a R/2 del precio.
  2. Una señal contraria no cierra la posición: sale por stop, meta o freno de régimen.
- Comando: `python -m trading_intelligence.live.binance_futures --dir live_runs/futures_auto_2r --capital 50 --trailing-desde 2 --sin-cierre-por-senal`.
- `--modo real` rechaza estas dos opciones: el bot real no puede usarlas.

## Cómo se lee

- Se compara contra la práctica 1x en el mismo periodo, con la misma regla de 30 operaciones: antes de 30 cerradas es ruido y no se saca ninguna conclusión.
- A las 30 cerradas se mira:
  - el neto en % de la cuenta;
  - la caída máxima;
  - la esperanza en R;
  - cuántas ganadoras salieron por meta.
- Pasar a dinero real exige la prueba completa: ganarle a la mesa en los dos años con costos y pasar el Sharpe deflactado. Si sale bien, esta observación no basta para cambiar el real.
- Esta observación no suma a la N: no es una variante nueva, es la misma regla de la fila 380 en vivo.

- 2026-10-22: desde el PR #131 el simulador cobra la financiación de 8 h a las posiciones abiertas. Rige igual para
  la práctica 1x y la de 2R desde el mismo momento, así que la comparación sigue siendo justa.
