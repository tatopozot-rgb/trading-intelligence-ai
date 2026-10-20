# Registro único de pruebas de estrategia

Propuesta de Quant (2026-10-16), pedida por el líder en la lección del tema 6 (`docs/inteligencia/2026-10-16.md`).
Cada vez que se corre una prueba nueva, se agrega aquí **antes** de mirar el resultado (con "pendiente"), y el
resultado se llena después. Las pruebas decisorias de esta tabla son la N del Sharpe deflactado (líder, 2026-10-16; `docs/research/PROTOCOLO.md`).

## Regla de conteo

- Una prueba = un conjunto de reglas distinto evaluado con datos: estrategia × versión × parámetro × activo o
  universo × marco de tiempo. Los dos años de la misma regla son **una** prueba.
- Las filas de sensibilidad (otro umbral, costes ×2, espejo en corto) también cuentan, marcadas "sensibilidad",
  porque se vieron.
- Cada combinación de una rejilla (walk-forward o ajuste/prueba) cuenta como una prueba; el agregado no se cuenta
  aparte.
- No cuentan: las filas de referencia (mesa de práctica, mesa_r3, BTC comprar y mantener), las re-mediciones de la
  mesa, los análisis que no operan reglas (correlaciones) y las re-corridas de la misma regla.
- Desde el 2026-10-12, por fecha de corrida (no por la fecha que lleva el nombre del informe).

## Totales al 2026-10-19

- **Total: 369 pruebas** (288 decisorias y 81 de sensibilidad). Las últimas 10 son el cruce del MACD en BTC y ETH diario (`docs/research/macd/`) y la salida por régimen sobre la mesa (`docs/research/salida_regimen/`): pendiente. Antes, 12 son la nube de Ichimoku en BTC y ETH diario (`docs/research/ichimoku/`) y el freno por caída de la cuenta sobre la mesa (`docs/research/freno_caida/`): ninguna pasa. Ichimoku A en BTC y ETH juntas gana a la mesa en 2024-25 (2,92) pero pierde en 2025-26 (−0,34); B con frenos queda bajo la mesa en 2024-25 (0,23). El freno por caída en 1x gana a la mesa los dos años (1,92 ; 0,18) pero no pasa el Sharpe deflactado (0,005); contra la misma mesa sin freno sube 2024-25 de 1,04 a 1,92 (caída 54% → 45%) y no cambia 2025-26; en 3x sigue negativo (−0,22 ; −0,69). Sharpe deflactado de todas ≤ 0,009. Antes, 8 son el Supertrend de freqtrade en BTC y ETH (`docs/research/supertrend/`): ninguna pasa. B con frenos en ETH gana a la mesa en 2024-25 (2,29) pero pierde en 2025-26 (−0,42); el Sharpe deflactado de todas es ≤ 0,001. Antes, 10 son el bot de cuadrícula al contado en BTC y ETH (`docs/research/grid/`): ninguna pasa; lo ganado en idas y vueltas se pierde en el inventario (BTC −0,0% y −15,0%, ETH −29,4% y −29,0%). Antes, 8 son la cartera multi-mercado en XM y la ruptura de Londres en BTC con costos de XM (`docs/research/cartera_xm/`, `docs/research/cripto_xm/`): ninguna pasa (Londres BTC gana a la mesa, DSR 0,011). Antes, 4 son copiar bóvedas de Hyperliquid
  con un año ganador (`docs/research/copiar/`): pierden −65,6% en 2025-26; no pasan. Antes, 4 de spreads de XSP en
  opciones (modelo Black-Scholes con VIX): ganan en los dos años, pero su Sharpe deflactado es 0,025; no pasan. Antes, hoy: 5 de RSI-2 y 10 de
  horizonte largo (ninguna pasa), 4 de carry en BTC y ETH y 6 de oro dentro del día. Ninguna pasa.
- Sharpe deflactado de la ruptura de Londres en oro 2025-26 con N = 292: **0,21** (listón 0,95). Su Sharpe anual
  de 2,04 queda bajo el 2,84 que se esperaría por suerte de la mejor de 292 pruebas sin ventaja
  (`docs/research/deflactado/`).
- Familias de ideas distintas: 27 (23 estrategias propias y 4 grupos que solo modifican la mesa).
- Rejillas: 206 de las decisorias son combinaciones de una rejilla.
- Ninguna estrategia pasó su listón. El único "sí" es el filtro L5 del lado saturado, que mejora a la mesa de
  práctica por márgenes mínimos.

## Cómo se usa

1. Antes de correr: agregar las filas con "pendiente" en el mismo commit del preregistro.
2. Después de correr: llenar el resultado y si pasa.
3. Antes de pasar algo a práctica: calcular su Sharpe deflactado con N = las decisorias de esta tabla
   (`research_deflactado`). Listón: 0,95.
4. Los informes nuevos deben guardar el capital diario en su JSON, para poder medir el Sharpe de cada prueba.

## Pruebas

| # | Fecha | Estudio (carpeta) | Estrategia | Versión/parámetro | Activo/marco | Tipo | Resultado clave | Pasa |
|---|---|---|---|---|---|---|---|---|
| 1 | 2026-10-12 | raíz (segunda_estrategia) | Funding fade | theta=0.015, hours=8 | 12 monedas, 5 min, 90 días | decisoria (rejilla ajuste/prueba) | ajuste (60%): -2.47% / caída 5.68% / 39 ops | no |
| 2 | 2026-10-12 | raíz (segunda_estrategia) | Funding fade | theta=0.015, hours=24 | 12 monedas, 5 min, 90 días | decisoria (rejilla ajuste/prueba) | ajuste (60%): -1.90% / caída 6.72% / 22 ops | no |
| 3 | 2026-10-12 | raíz (segunda_estrategia) | Funding fade | theta=0.025, hours=8 | 12 monedas, 5 min, 90 días | decisoria (rejilla ajuste/prueba) | ajuste (60%): -0.14% / caída 1.9% / 18 ops; prueba (40%): -0.35% / caída 1.08% / 14 ops (elegida) | no |
| 4 | 2026-10-12 | raíz (segunda_estrategia) | Funding fade | theta=0.025, hours=24 | 12 monedas, 5 min, 90 días | decisoria (rejilla ajuste/prueba) | ajuste (60%): +2.12% / caída 1.88% / 9 ops | no |
| 5 | 2026-10-12 | raíz (segunda_estrategia) | Funding fade | theta=0.04, hours=8 | 12 monedas, 5 min, 90 días | decisoria (rejilla ajuste/prueba) | ajuste (60%): -0.69% / caída 1.89% / 12 ops | no |
| 6 | 2026-10-12 | raíz (segunda_estrategia) | Funding fade | theta=0.04, hours=24 | 12 monedas, 5 min, 90 días | decisoria (rejilla ajuste/prueba) | ajuste (60%): +0.99% / caída 1.64% / 7 ops | no |
| 7 | 2026-10-12 | raíz (segunda_estrategia) | Ruptura Asia/Londres | stop=opuesto, k=1.0 | 12 monedas, 5 min, 90 días | decisoria (rejilla ajuste/prueba) | ajuste (60%): +7.74% / caída 4.35% / 63 ops; prueba (40%): +0.50% / caída 4.94% / 50 ops (elegida) | no |
| 8 | 2026-10-12 | raíz (segunda_estrategia) | Ruptura Asia/Londres | stop=opuesto, k=1.5 | 12 monedas, 5 min, 90 días | decisoria (rejilla ajuste/prueba) | ajuste (60%): +6.94% / caída 4.7% / 63 ops | no |
| 9 | 2026-10-12 | raíz (segunda_estrategia) | Ruptura Asia/Londres | stop=opuesto, k=2.0 | 12 monedas, 5 min, 90 días | decisoria (rejilla ajuste/prueba) | ajuste (60%): +6.05% / caída 5.38% / 63 ops | no |
| 10 | 2026-10-12 | raíz (segunda_estrategia) | Ruptura Asia/Londres | stop=medio, k=1.0 | 12 monedas, 5 min, 90 días | decisoria (rejilla ajuste/prueba) | ajuste (60%): +1.43% / caída 3.37% / 63 ops | no |
| 11 | 2026-10-12 | raíz (segunda_estrategia) | Ruptura Asia/Londres | stop=medio, k=1.5 | 12 monedas, 5 min, 90 días | decisoria (rejilla ajuste/prueba) | ajuste (60%): +1.23% / caída 4.4% / 63 ops | no |
| 12 | 2026-10-12 | raíz (segunda_estrategia) | Ruptura Asia/Londres | stop=medio, k=2.0 | 12 monedas, 5 min, 90 días | decisoria (rejilla ajuste/prueba) | ajuste (60%): +3.32% / caída 4.28% / 63 ops | no |
| 13 | 2026-10-12 | raíz (segunda_estrategia) | Scout momentum | move=1.0, vol=2.0, hours=1 | 12 monedas, 5 min, 90 días | decisoria (rejilla ajuste/prueba) | ajuste (60%): -8.32% / caída 16.24% / 396 ops | no |
| 14 | 2026-10-12 | raíz (segunda_estrategia) | Scout momentum | move=1.0, vol=2.0, hours=4 | 12 monedas, 5 min, 90 días | decisoria (rejilla ajuste/prueba) | ajuste (60%): -8.30% / caída 12.8% / 283 ops | no |
| 15 | 2026-10-12 | raíz (segunda_estrategia) | Scout momentum | move=1.0, vol=3.0, hours=1 | 12 monedas, 5 min, 90 días | decisoria (rejilla ajuste/prueba) | ajuste (60%): -4.87% / caída 13.06% / 310 ops | no |
| 16 | 2026-10-12 | raíz (segunda_estrategia) | Scout momentum | move=1.0, vol=3.0, hours=4 | 12 monedas, 5 min, 90 días | decisoria (rejilla ajuste/prueba) | ajuste (60%): -4.45% / caída 12.7% / 250 ops | no |
| 17 | 2026-10-12 | raíz (segunda_estrategia) | Scout momentum | move=1.5, vol=2.0, hours=1 | 12 monedas, 5 min, 90 días | decisoria (rejilla ajuste/prueba) | ajuste (60%): -1.47% / caída 15.82% / 155 ops | no |
| 18 | 2026-10-12 | raíz (segunda_estrategia) | Scout momentum | move=1.5, vol=2.0, hours=4 | 12 monedas, 5 min, 90 días | decisoria (rejilla ajuste/prueba) | ajuste (60%): -7.84% / caída 16.26% / 121 ops | no |
| 19 | 2026-10-12 | raíz (segunda_estrategia) | Scout momentum | move=1.5, vol=3.0, hours=1 | 12 monedas, 5 min, 90 días | decisoria (rejilla ajuste/prueba) | ajuste (60%): +3.52% / caída 12.56% / 121 ops; prueba (40%): -1.46% / caída 14.02% / 157 ops (elegida) | no |
| 20 | 2026-10-12 | raíz (segunda_estrategia) | Scout momentum | move=1.5, vol=3.0, hours=4 | 12 monedas, 5 min, 90 días | decisoria (rejilla ajuste/prueba) | ajuste (60%): -0.25% / caída 12.14% / 107 ops | no |
| 21 | 2026-10-12 | tendencia | Donchian | tf=4h, n=20, salida=canal10 sin filtro | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -43.40% / caída 50.74% / 322 ops | no (WF de la familia pierde) |
| 22 | 2026-10-12 | tendencia | Donchian | tf=4h, n=20, salida=canal20 sin filtro | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -33.02% / caída 47.57% / 182 ops | no (WF de la familia pierde) |
| 23 | 2026-10-12 | tendencia | Donchian | tf=4h, n=20, salida=atr2 sin filtro | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -62.68% / caída 64.34% / 378 ops | no (WF de la familia pierde) |
| 24 | 2026-10-12 | tendencia | Donchian | tf=4h, n=20, salida=atr3 sin filtro | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -29.12% / caída 43.64% / 236 ops | no (WF de la familia pierde) |
| 25 | 2026-10-12 | tendencia | Donchian | tf=4h, n=20, salida=atr4 sin filtro | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -46.43% / caída 54.66% / 172 ops | no (WF de la familia pierde) |
| 26 | 2026-10-12 | tendencia | Donchian | tf=4h, n=55, salida=canal10 sin filtro | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -43.05% / caída 46.47% / 223 ops | no (WF de la familia pierde) |
| 27 | 2026-10-12 | tendencia | Donchian | tf=4h, n=55, salida=canal20 sin filtro | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -37.14% / caída 43.82% / 154 ops | no (WF de la familia pierde) |
| 28 | 2026-10-12 | tendencia | Donchian | tf=4h, n=55, salida=atr2 sin filtro | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -51.43% / caída 53.54% / 264 ops | no (WF de la familia pierde) |
| 29 | 2026-10-12 | tendencia | Donchian | tf=4h, n=55, salida=atr3 sin filtro | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -42.18% / caída 45.53% / 180 ops | no (WF de la familia pierde) |
| 30 | 2026-10-12 | tendencia | Donchian | tf=4h, n=55, salida=atr4 sin filtro | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -46.39% / caída 49.65% / 130 ops | no (WF de la familia pierde) |
| 31 | 2026-10-12 | tendencia | Donchian | tf=1d, n=20, salida=canal10 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: -29.48% / caída 31.38% / 56 ops | no (WF de la familia pierde) |
| 32 | 2026-10-12 | tendencia | Donchian | tf=1d, n=20, salida=canal20 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: -1.92% / caída 18.71% / 30 ops | no (WF de la familia pierde) |
| 33 | 2026-10-12 | tendencia | Donchian | tf=1d, n=20, salida=atr2 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: -18.75% / caída 28.34% / 58 ops | no (WF de la familia pierde) |
| 34 | 2026-10-12 | tendencia | Donchian | tf=1d, n=20, salida=atr3 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +7.75% / caída 20.62% / 32 ops | no (WF de la familia pierde) |
| 35 | 2026-10-12 | tendencia | Donchian | tf=1d, n=20, salida=atr4 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +19.04% / caída 21.35% / 26 ops | no (WF de la familia pierde) |
| 36 | 2026-10-12 | tendencia | Donchian | tf=1d, n=55, salida=canal10 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +4.50% / caída 18.5% / 38 ops | no (WF de la familia pierde) |
| 37 | 2026-10-12 | tendencia | Donchian | tf=1d, n=55, salida=canal20 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +11.17% / caída 14.42% / 24 ops | no (WF de la familia pierde) |
| 38 | 2026-10-12 | tendencia | Donchian | tf=1d, n=55, salida=atr2 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +2.93% / caída 26.6% / 40 ops | no (WF de la familia pierde) |
| 39 | 2026-10-12 | tendencia | Donchian | tf=1d, n=55, salida=atr3 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +19.42% / caída 18.57% / 26 ops | no (WF de la familia pierde) |
| 40 | 2026-10-12 | tendencia | Donchian | tf=1d, n=55, salida=atr4 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +15.65% / caída 16.15% / 21 ops | no (WF de la familia pierde) |
| 41 | 2026-10-12 | tendencia | Donchian | tf=4h, n=20, salida=canal10 + filtro BTC>SMA200 | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -19.96% / caída 32.33% / 192 ops | no (WF de la familia pierde) |
| 42 | 2026-10-12 | tendencia | Donchian | tf=4h, n=20, salida=canal20 + filtro BTC>SMA200 | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -17.43% / caída 41.6% / 134 ops | no (WF de la familia pierde) |
| 43 | 2026-10-12 | tendencia | Donchian | tf=4h, n=20, salida=atr2 + filtro BTC>SMA200 | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -42.88% / caída 47.99% / 212 ops | no (WF de la familia pierde) |
| 44 | 2026-10-12 | tendencia | Donchian | tf=4h, n=20, salida=atr3 + filtro BTC>SMA200 | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -9.60% / caída 35.73% / 142 ops | no (WF de la familia pierde) |
| 45 | 2026-10-12 | tendencia | Donchian | tf=4h, n=20, salida=atr4 + filtro BTC>SMA200 | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -15.49% / caída 34.91% / 122 ops | no (WF de la familia pierde) |
| 46 | 2026-10-12 | tendencia | Donchian | tf=4h, n=55, salida=canal10 + filtro BTC>SMA200 | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -19.68% / caída 29.48% / 124 ops | no (WF de la familia pierde) |
| 47 | 2026-10-12 | tendencia | Donchian | tf=4h, n=55, salida=canal20 + filtro BTC>SMA200 | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -23.59% / caída 33.97% / 93 ops | no (WF de la familia pierde) |
| 48 | 2026-10-12 | tendencia | Donchian | tf=4h, n=55, salida=atr2 + filtro BTC>SMA200 | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -28.24% / caída 35.65% / 139 ops | no (WF de la familia pierde) |
| 49 | 2026-10-12 | tendencia | Donchian | tf=4h, n=55, salida=atr3 + filtro BTC>SMA200 | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -19.86% / caída 38.24% / 97 ops | no (WF de la familia pierde) |
| 50 | 2026-10-12 | tendencia | Donchian | tf=4h, n=55, salida=atr4 + filtro BTC>SMA200 | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -32.57% / caída 39.7% / 79 ops | no (WF de la familia pierde) |
| 51 | 2026-10-12 | tendencia | Donchian | tf=1d, n=20, salida=canal10 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +20.64% / caída 17.87% / 32 ops | no (WF de la familia pierde) |
| 52 | 2026-10-12 | tendencia | Donchian | tf=1d, n=20, salida=canal20 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +27.46% / caída 15.94% / 22 ops | no (WF de la familia pierde) |
| 53 | 2026-10-12 | tendencia | Donchian | tf=1d, n=20, salida=atr2 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: -2.70% / caída 26.21% / 36 ops | no (WF de la familia pierde) |
| 54 | 2026-10-12 | tendencia | Donchian | tf=1d, n=20, salida=atr3 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +31.98% / caída 17.54% / 23 ops | no (WF de la familia pierde) |
| 55 | 2026-10-12 | tendencia | Donchian | tf=1d, n=20, salida=atr4 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +26.80% / caída 17.77% / 20 ops | no (WF de la familia pierde) |
| 56 | 2026-10-12 | tendencia | Donchian | tf=1d, n=55, salida=canal10 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +20.73% / caída 14.49% / 24 ops | no (WF de la familia pierde) |
| 57 | 2026-10-12 | tendencia | Donchian | tf=1d, n=55, salida=canal20 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +14.78% / caída 12.45% / 17 ops | no (WF de la familia pierde) |
| 58 | 2026-10-12 | tendencia | Donchian | tf=1d, n=55, salida=atr2 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +7.35% / caída 27.22% / 28 ops | no (WF de la familia pierde) |
| 59 | 2026-10-12 | tendencia | Donchian | tf=1d, n=55, salida=atr3 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +21.25% / caída 16.61% / 17 ops | no (WF de la familia pierde) |
| 60 | 2026-10-12 | tendencia | Donchian | tf=1d, n=55, salida=atr4 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +20.39% / caída 16.56% / 14 ops | no (WF de la familia pierde) |
| 61 | 2026-10-12 | tendencia | Cruce EMA | tf=4h, rapida=20, lenta=50, atr=2 sin filtro | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -56.75% / caída 64.27% / 302 ops | no (WF de la familia pierde) |
| 62 | 2026-10-12 | tendencia | Cruce EMA | tf=4h, rapida=20, lenta=50, atr=3 sin filtro | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -40.22% / caída 50.53% / 227 ops | no (WF de la familia pierde) |
| 63 | 2026-10-12 | tendencia | Cruce EMA | tf=4h, rapida=20, lenta=50, atr=4 sin filtro | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -12.41% / caída 36.78% / 163 ops | no (WF de la familia pierde) |
| 64 | 2026-10-12 | tendencia | Cruce EMA | tf=4h, rapida=20, lenta=100, atr=2 sin filtro | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -47.69% / caída 58.84% / 222 ops | no (WF de la familia pierde) |
| 65 | 2026-10-12 | tendencia | Cruce EMA | tf=4h, rapida=20, lenta=100, atr=3 sin filtro | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -43.04% / caída 59.7% / 177 ops | no (WF de la familia pierde) |
| 66 | 2026-10-12 | tendencia | Cruce EMA | tf=4h, rapida=20, lenta=100, atr=4 sin filtro | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -33.68% / caída 42.62% / 140 ops | no (WF de la familia pierde) |
| 67 | 2026-10-12 | tendencia | Cruce EMA | tf=4h, rapida=50, lenta=200, atr=2 sin filtro | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -12.09% / caída 23.59% / 86 ops | no (WF de la familia pierde) |
| 68 | 2026-10-12 | tendencia | Cruce EMA | tf=4h, rapida=50, lenta=200, atr=3 sin filtro | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: +0.29% / caída 22.55% / 74 ops | no (WF de la familia pierde) |
| 69 | 2026-10-12 | tendencia | Cruce EMA | tf=4h, rapida=50, lenta=200, atr=4 sin filtro | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: +22.56% / caída 21.89% / 65 ops | no (WF de la familia pierde) |
| 70 | 2026-10-12 | tendencia | Cruce EMA | tf=1d, rapida=20, lenta=50, atr=2 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +64.57% / caída 24.5% / 34 ops | no (WF de la familia pierde) |
| 71 | 2026-10-12 | tendencia | Cruce EMA | tf=1d, rapida=20, lenta=50, atr=3 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +77.19% / caída 18.53% / 28 ops; 2024-25 (preregistro): -4.21% / 41.86% / 42 ops (no) | no (WF de la familia pierde) |
| 72 | 2026-10-12 | tendencia | Cruce EMA | tf=1d, rapida=20, lenta=50, atr=4 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +47.37% / caída 18.56% / 25 ops | no (WF de la familia pierde) |
| 73 | 2026-10-12 | tendencia | Cruce EMA | tf=4h, rapida=20, lenta=50, atr=2 + filtro BTC>SMA200 | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -23.28% / caída 34.9% / 164 ops | no (WF de la familia pierde) |
| 74 | 2026-10-12 | tendencia | Cruce EMA | tf=4h, rapida=20, lenta=50, atr=3 + filtro BTC>SMA200 | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: +6.31% / caída 31.94% / 141 ops | no (WF de la familia pierde) |
| 75 | 2026-10-12 | tendencia | Cruce EMA | tf=4h, rapida=20, lenta=50, atr=4 + filtro BTC>SMA200 | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: +4.49% / caída 39.42% / 120 ops | no (WF de la familia pierde) |
| 76 | 2026-10-12 | tendencia | Cruce EMA | tf=4h, rapida=20, lenta=100, atr=2 + filtro BTC>SMA200 | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: -12.42% / caída 29.57% / 114 ops | no (WF de la familia pierde) |
| 77 | 2026-10-12 | tendencia | Cruce EMA | tf=4h, rapida=20, lenta=100, atr=3 + filtro BTC>SMA200 | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: +4.84% / caída 30.71% / 101 ops | no (WF de la familia pierde) |
| 78 | 2026-10-12 | tendencia | Cruce EMA | tf=4h, rapida=20, lenta=100, atr=4 + filtro BTC>SMA200 | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: +6.02% / caída 30.7% / 90 ops | no (WF de la familia pierde) |
| 79 | 2026-10-12 | tendencia | Cruce EMA | tf=4h, rapida=50, lenta=200, atr=2 + filtro BTC>SMA200 | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: +6.93% / caída 7.98% / 40 ops | no (WF de la familia pierde) |
| 80 | 2026-10-12 | tendencia | Cruce EMA | tf=4h, rapida=50, lenta=200, atr=3 + filtro BTC>SMA200 | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: +15.81% / caída 11.06% / 36 ops | no (WF de la familia pierde) |
| 81 | 2026-10-12 | tendencia | Cruce EMA | tf=4h, rapida=50, lenta=200, atr=4 + filtro BTC>SMA200 | 12 monedas, 4h | decisoria (rejilla WF) | 2025-26: +9.97% / caída 15.45% / 34 ops | no (WF de la familia pierde) |
| 82 | 2026-10-12 | tendencia | Cruce EMA | tf=1d, rapida=20, lenta=50, atr=2 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +80.48% / caída 12.48% / 16 ops | no (WF de la familia pierde) |
| 83 | 2026-10-12 | tendencia | Cruce EMA | tf=1d, rapida=20, lenta=50, atr=3 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +68.88% / caída 13.85% / 16 ops | no (WF de la familia pierde) |
| 84 | 2026-10-12 | tendencia | Cruce EMA | tf=1d, rapida=20, lenta=50, atr=4 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +62.20% / caída 12.95% / 15 ops | no (WF de la familia pierde) |
| 85 | 2026-10-12 | tendencia | TSMOM | dias=30, vol=20, mantener=3 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +12.70% / caída 23.48% / 260 ops | no (WF de la familia pierde) |
| 86 | 2026-10-12 | tendencia | TSMOM | dias=30, vol=20, mantener=6 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: -2.68% / caída 29.07% / 107 ops | no (WF de la familia pierde) |
| 87 | 2026-10-12 | tendencia | TSMOM | dias=30, vol=60, mantener=3 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +8.20% / caída 20.75% / 210 ops | no (WF de la familia pierde) |
| 88 | 2026-10-12 | tendencia | TSMOM | dias=30, vol=60, mantener=6 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: -0.35% / caída 24.83% / 95 ops | no (WF de la familia pierde) |
| 89 | 2026-10-12 | tendencia | TSMOM | dias=60, vol=20, mantener=3 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +60.83% / caída 16.54% / 189 ops; 2024-25 (preregistro): +64.88% / 41.0% / 137 ops (no: 2 de 5 trimestres) | no (WF de la familia pierde) |
| 90 | 2026-10-12 | tendencia | TSMOM | dias=60, vol=20, mantener=6 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +52.93% / caída 22.23% / 55 ops | no (WF de la familia pierde) |
| 91 | 2026-10-12 | tendencia | TSMOM | dias=60, vol=60, mantener=3 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +18.73% / caída 16.64% / 172 ops | no (WF de la familia pierde) |
| 92 | 2026-10-12 | tendencia | TSMOM | dias=60, vol=60, mantener=6 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +22.34% / caída 20.78% / 58 ops | no (WF de la familia pierde) |
| 93 | 2026-10-12 | tendencia | TSMOM | dias=90, vol=20, mantener=3 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: -6.84% / caída 33.71% / 155 ops | no (WF de la familia pierde) |
| 94 | 2026-10-12 | tendencia | TSMOM | dias=90, vol=20, mantener=6 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +2.49% / caída 26.78% / 40 ops | no (WF de la familia pierde) |
| 95 | 2026-10-12 | tendencia | TSMOM | dias=90, vol=60, mantener=3 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: -4.66% / caída 29.83% / 152 ops | no (WF de la familia pierde) |
| 96 | 2026-10-12 | tendencia | TSMOM | dias=90, vol=60, mantener=6 sin filtro | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +0.87% / caída 27.36% / 40 ops | no (WF de la familia pierde) |
| 97 | 2026-10-12 | tendencia | TSMOM | dias=30, vol=20, mantener=3 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +7.89% / caída 25.54% / 183 ops | no (WF de la familia pierde) |
| 98 | 2026-10-12 | tendencia | TSMOM | dias=30, vol=20, mantener=6 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +6.96% / caída 24.93% / 82 ops | no (WF de la familia pierde) |
| 99 | 2026-10-12 | tendencia | TSMOM | dias=30, vol=60, mantener=3 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +30.36% / caída 18.71% / 142 ops | no (WF de la familia pierde) |
| 100 | 2026-10-12 | tendencia | TSMOM | dias=30, vol=60, mantener=6 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +22.36% / caída 20.12% / 74 ops | no (WF de la familia pierde) |
| 101 | 2026-10-12 | tendencia | TSMOM | dias=60, vol=20, mantener=3 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +50.88% / caída 17.1% / 157 ops | no (WF de la familia pierde) |
| 102 | 2026-10-12 | tendencia | TSMOM | dias=60, vol=20, mantener=6 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +52.66% / caída 22.6% / 51 ops | no (WF de la familia pierde) |
| 103 | 2026-10-12 | tendencia | TSMOM | dias=60, vol=60, mantener=3 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +24.67% / caída 21.7% / 137 ops | no (WF de la familia pierde) |
| 104 | 2026-10-12 | tendencia | TSMOM | dias=60, vol=60, mantener=6 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +30.65% / caída 21.05% / 51 ops | no (WF de la familia pierde) |
| 105 | 2026-10-12 | tendencia | TSMOM | dias=90, vol=20, mantener=3 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +1.50% / caída 29.36% / 130 ops | no (WF de la familia pierde) |
| 106 | 2026-10-12 | tendencia | TSMOM | dias=90, vol=20, mantener=6 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +15.67% / caída 30.6% / 39 ops | no (WF de la familia pierde) |
| 107 | 2026-10-12 | tendencia | TSMOM | dias=90, vol=60, mantener=3 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: -2.68% / caída 32.68% / 131 ops | no (WF de la familia pierde) |
| 108 | 2026-10-12 | tendencia | TSMOM | dias=90, vol=60, mantener=6 + filtro BTC>SMA200 | 12 monedas, 1d | decisoria (rejilla WF) | 2025-26: +13.35% / caída 28.96% / 33 ops | no (WF de la familia pierde) |
| 109 | 2026-10-13 | tendencia (btc_regimen 1-3) | Régimen BTC | btc_sma200 | BTCUSDT, señal 1d / ejecución 1h | decisoria | 2020-26: 2024-25 +20.53%/33.26%; 2025-26 +8.18%/13.0%; ×3.47 en 6 años | no |
| 110 | 2026-10-13 | tendencia (btc_regimen 1-3) | Régimen BTC | btc_sma50 | BTCUSDT, señal 1d / ejecución 1h | decisoria | 2024-25 +53.42%/21.17%; 2025-26 +14.06%/17.69%; ×9.36 en 6 años | no |
| 111 | 2026-10-13 | tendencia (btc_regimen 1-3) | Régimen BTC | btc_sma200_stop10 | BTCUSDT, señal 1d / ejecución 1h | decisoria | 2024-25 +34.05%/15.42%; 2025-26 +6.08%/14.68% (también 2020-24) | no |
| 112 | 2026-10-13 | tendencia (btc_regimen 1-3) | Régimen BTC | btc_sma50_200 | BTCUSDT, señal 1d / ejecución 1h | decisoria | 2024-25 +36.40%/18.06%; 2025-26 +16.70%/7.12%; ×9.56 en 6 años | no (cumple solo 2022-23) |
| 113 | 2026-10-13 | tendencia (btc_regimen 1-3) | Régimen BTC | btc_sma50_200_conf2 | BTCUSDT, señal 1d / ejecución 1h | decisoria | 2024-25 +38.07%/15.51%; 2025-26 +11.25%/7.12%; ×8.78 en 6 años | no |
| 114 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=7, rebalance=1, mode=largo3 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -66.05% / caída 105.75% / 352 ops | no (WF de la familia pierde) |
| 115 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=7, rebalance=1, mode=largo3_btc50 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -10.08% / caída 31.04% / 185 ops | no (WF de la familia pierde) |
| 116 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=7, rebalance=1, mode=ls | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -52.12% / caída 57.33% / 308 ops | no (WF de la familia pierde) |
| 117 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=7, rebalance=7, mode=largo3 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -36.35% / caída 56.06% / 122 ops | no (WF de la familia pierde) |
| 118 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=7, rebalance=7, mode=largo3_btc50 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: +7.72% / caída 23.03% / 61 ops | no (WF de la familia pierde) |
| 119 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=7, rebalance=7, mode=ls | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -31.88% / caída 35.1% / 95 ops | no (WF de la familia pierde) |
| 120 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=14, rebalance=1, mode=largo3 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -64.10% / caída 93.67% / 249 ops | no (WF de la familia pierde) |
| 121 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=14, rebalance=1, mode=largo3_btc50 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -6.48% / caída 29.85% / 137 ops | no (WF de la familia pierde) |
| 122 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=14, rebalance=1, mode=ls | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -10.10% / caída 26.63% / 228 ops | no (WF de la familia pierde) |
| 123 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=14, rebalance=7, mode=largo3 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -42.32% / caída 64.86% / 94 ops | no (WF de la familia pierde) |
| 124 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=14, rebalance=7, mode=largo3_btc50 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: +8.39% / caída 20.66% / 49 ops | no (WF de la familia pierde) |
| 125 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=14, rebalance=7, mode=ls | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -4.24% / caída 25.43% / 72 ops | no (WF de la familia pierde) |
| 126 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=30, rebalance=1, mode=largo3 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -89.06% / caída 110.31% / 190 ops | no (WF de la familia pierde) |
| 127 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=30, rebalance=1, mode=largo3_btc50 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -27.77% / caída 39.71% / 122 ops | no (WF de la familia pierde) |
| 128 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=30, rebalance=1, mode=ls | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -81.27% / caída 87.68% / 169 ops | no (WF de la familia pierde) |
| 129 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=30, rebalance=7, mode=largo3 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -34.65% / caída 65.89% / 81 ops | no (WF de la familia pierde) |
| 130 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=30, rebalance=7, mode=largo3_btc50 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: +10.62% / caída 22.04% / 41 ops | no (WF de la familia pierde) |
| 131 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=30, rebalance=7, mode=ls | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -29.00% / caída 49.67% / 65 ops | no (WF de la familia pierde) |
| 132 | 2026-10-12/13 | rotacion | Reversión corta (PR #46) | signal=rsi2, hold=6, stop_atr=1.5 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -140.96% / caída 143.97% / 3347 ops | no (WF de la familia pierde) |
| 133 | 2026-10-12/13 | rotacion | Reversión corta (PR #46) | signal=rsi2, hold=6, stop_atr=3.0 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -142.75% / caída 145.89% / 2929 ops | no (WF de la familia pierde) |
| 134 | 2026-10-12/13 | rotacion | Reversión corta (PR #46) | signal=rsi2, hold=24, stop_atr=1.5 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -72.85% / caída 83.47% / 2462 ops | no (WF de la familia pierde) |
| 135 | 2026-10-12/13 | rotacion | Reversión corta (PR #46) | signal=rsi2, hold=24, stop_atr=3.0 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -83.21% / caída 86.45% / 1895 ops | no (WF de la familia pierde) |
| 136 | 2026-10-12/13 | rotacion | Reversión corta (PR #46) | signal=rsi4, hold=6, stop_atr=1.5 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -84.78% / caída 88.27% / 2231 ops | no (WF de la familia pierde) |
| 137 | 2026-10-12/13 | rotacion | Reversión corta (PR #46) | signal=rsi4, hold=6, stop_atr=3.0 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -88.80% / caída 92.07% / 1947 ops | no (WF de la familia pierde) |
| 138 | 2026-10-12/13 | rotacion | Reversión corta (PR #46) | signal=rsi4, hold=24, stop_atr=1.5 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -40.87% / caída 51.0% / 1860 ops | no (WF de la familia pierde) |
| 139 | 2026-10-12/13 | rotacion | Reversión corta (PR #46) | signal=rsi4, hold=24, stop_atr=3.0 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -56.69% / caída 61.36% / 1450 ops | no (WF de la familia pierde) |
| 140 | 2026-10-12/13 | rotacion | Reversión corta (PR #46) | signal=bb2, hold=6, stop_atr=1.5 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -76.49% / caída 77.58% / 1685 ops | no (WF de la familia pierde) |
| 141 | 2026-10-12/13 | rotacion | Reversión corta (PR #46) | signal=bb2, hold=6, stop_atr=3.0 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -75.37% / caída 78.1% / 1445 ops | no (WF de la familia pierde) |
| 142 | 2026-10-12/13 | rotacion | Reversión corta (PR #46) | signal=bb2, hold=24, stop_atr=1.5 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -71.30% / caída 80.13% / 1548 ops | no (WF de la familia pierde) |
| 143 | 2026-10-12/13 | rotacion | Reversión corta (PR #46) | signal=bb2, hold=24, stop_atr=3.0 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -84.81% / caída 89.61% / 1200 ops | no (WF de la familia pierde) |
| 144 | 2026-10-12/13 | rotacion | Reversión corta (PR #46) | signal=bb2.5, hold=6, stop_atr=1.5 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -35.66% / caída 36.23% / 914 ops | no (WF de la familia pierde) |
| 145 | 2026-10-12/13 | rotacion | Reversión corta (PR #46) | signal=bb2.5, hold=6, stop_atr=3.0 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -35.40% / caída 35.7% / 802 ops | no (WF de la familia pierde) |
| 146 | 2026-10-12/13 | rotacion | Reversión corta (PR #46) | signal=bb2.5, hold=24, stop_atr=1.5 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -28.23% / caída 32.36% / 897 ops | no (WF de la familia pierde) |
| 147 | 2026-10-12/13 | rotacion | Reversión corta (PR #46) | signal=bb2.5, hold=24, stop_atr=3.0 | 12 monedas, 1h | decisoria (rejilla WF) | 2025-26: -36.29% / caída 39.18% / 749 ops | no (WF de la familia pierde) |
| 148 | 2026-10-12/13 | rotacion | Pares ETH/BTC y SOL/ETH | lookback=7, z_in=2.0, z_stop=3.5 | 2 pares, 1h | decisoria (rejilla WF) | 2025-26: -7.18% / caída 13.58% / 161 ops | no (WF de la familia pierde) |
| 149 | 2026-10-12/13 | rotacion | Pares ETH/BTC y SOL/ETH | lookback=7, z_in=2.0, z_stop=None | 2 pares, 1h | decisoria (rejilla WF) | 2025-26: -3.52% / caída 11.97% / 116 ops | no (WF de la familia pierde) |
| 150 | 2026-10-12/13 | rotacion | Pares ETH/BTC y SOL/ETH | lookback=7, z_in=2.5, z_stop=3.5 | 2 pares, 1h | decisoria (rejilla WF) | 2025-26: -1.87% / caída 8.69% / 126 ops | no (WF de la familia pierde) |
| 151 | 2026-10-12/13 | rotacion | Pares ETH/BTC y SOL/ETH | lookback=7, z_in=2.5, z_stop=None | 2 pares, 1h | decisoria (rejilla WF) | 2025-26: +0.96% / caída 9.01% / 85 ops | no (WF de la familia pierde) |
| 152 | 2026-10-12/13 | rotacion | Pares ETH/BTC y SOL/ETH | lookback=14, z_in=2.0, z_stop=3.5 | 2 pares, 1h | decisoria (rejilla WF) | 2025-26: -8.64% / caída 12.38% / 105 ops | no (WF de la familia pierde) |
| 153 | 2026-10-12/13 | rotacion | Pares ETH/BTC y SOL/ETH | lookback=14, z_in=2.0, z_stop=None | 2 pares, 1h | decisoria (rejilla WF) | 2025-26: -4.48% / caída 11.61% / 60 ops | no (WF de la familia pierde) |
| 154 | 2026-10-12/13 | rotacion | Pares ETH/BTC y SOL/ETH | lookback=14, z_in=2.5, z_stop=3.5 | 2 pares, 1h | decisoria (rejilla WF) | 2025-26: -8.81% / caída 11.55% / 88 ops | no (WF de la familia pierde) |
| 155 | 2026-10-12/13 | rotacion | Pares ETH/BTC y SOL/ETH | lookback=14, z_in=2.5, z_stop=None | 2 pares, 1h | decisoria (rejilla WF) | 2025-26: -6.54% / caída 11.36% / 43 ops | no (WF de la familia pierde) |
| 156 | 2026-10-12/13 | rotacion | Pares ETH/BTC y SOL/ETH | lookback=30, z_in=2.0, z_stop=3.5 | 2 pares, 1h | decisoria (rejilla WF) | 2025-26: -8.69% / caída 12.53% / 60 ops | no (WF de la familia pierde) |
| 157 | 2026-10-12/13 | rotacion | Pares ETH/BTC y SOL/ETH | lookback=30, z_in=2.0, z_stop=None | 2 pares, 1h | decisoria (rejilla WF) | 2025-26: -8.60% / caída 11.84% / 28 ops | no (WF de la familia pierde) |
| 158 | 2026-10-12/13 | rotacion | Pares ETH/BTC y SOL/ETH | lookback=30, z_in=2.5, z_stop=3.5 | 2 pares, 1h | decisoria (rejilla WF) | 2025-26: -5.72% / caída 9.4% / 54 ops | no (WF de la familia pierde) |
| 159 | 2026-10-12/13 | rotacion | Pares ETH/BTC y SOL/ETH | lookback=30, z_in=2.5, z_stop=None | 2 pares, 1h | decisoria (rejilla WF) | 2025-26: -5.01% / caída 9.13% / 22 ops | no (WF de la familia pierde) |
| 160 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=7, rebalance=1, mode=largo3 | top 30 de hoy (sesgo), 1h | decisoria (rejilla WF) | 2025-26: +75.90% / caída 67.9% / 343 ops | no (sesgo de supervivencia, no cuenta) |
| 161 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=7, rebalance=1, mode=largo3_btc50 | top 30 de hoy (sesgo), 1h | decisoria (rejilla WF) | 2025-26: +87.01% / caída 55.67% / 189 ops | no (sesgo de supervivencia, no cuenta) |
| 162 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=7, rebalance=1, mode=ls | top 30 de hoy (sesgo), 1h | decisoria (rejilla WF) | 2025-26: +17.65% / caída 90.19% / 327 ops | no (sesgo de supervivencia, no cuenta) |
| 163 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=7, rebalance=7, mode=largo3 | top 30 de hoy (sesgo), 1h | decisoria (rejilla WF) | 2025-26: +47.17% / caída 105.22% / 132 ops | no (sesgo de supervivencia, no cuenta) |
| 164 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=7, rebalance=7, mode=largo3_btc50 | top 30 de hoy (sesgo), 1h | decisoria (rejilla WF) | 2025-26: +82.17% / caída 36.92% / 63 ops | no (sesgo de supervivencia, no cuenta) |
| 165 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=7, rebalance=7, mode=ls | top 30 de hoy (sesgo), 1h | decisoria (rejilla WF) | 2025-26: +43.73% / caída 76.2% / 96 ops | no (sesgo de supervivencia, no cuenta) |
| 166 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=14, rebalance=1, mode=largo3 | top 30 de hoy (sesgo), 1h | decisoria (rejilla WF) | 2025-26: +119.36% / caída 100.27% / 257 ops | no (sesgo de supervivencia, no cuenta) |
| 167 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=14, rebalance=1, mode=largo3_btc50 | top 30 de hoy (sesgo), 1h | decisoria (rejilla WF) | 2025-26: +154.01% / caída 41.47% / 130 ops | no (sesgo de supervivencia, no cuenta) |
| 168 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=14, rebalance=1, mode=ls | top 30 de hoy (sesgo), 1h | decisoria (rejilla WF) | 2025-26: +44.92% / caída 68.23% / 263 ops | no (sesgo de supervivencia, no cuenta) |
| 169 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=14, rebalance=7, mode=largo3 | top 30 de hoy (sesgo), 1h | decisoria (rejilla WF) | 2025-26: +103.67% / caída 81.51% / 100 ops | no (sesgo de supervivencia, no cuenta) |
| 170 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=14, rebalance=7, mode=largo3_btc50 | top 30 de hoy (sesgo), 1h | decisoria (rejilla WF) | 2025-26: +105.78% / caída 36.42% / 50 ops | no (sesgo de supervivencia, no cuenta) |
| 171 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=14, rebalance=7, mode=ls | top 30 de hoy (sesgo), 1h | decisoria (rejilla WF) | 2025-26: +25.45% / caída 97.74% / 76 ops | no (sesgo de supervivencia, no cuenta) |
| 172 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=30, rebalance=1, mode=largo3 | top 30 de hoy (sesgo), 1h | decisoria (rejilla WF) | 2025-26: +127.72% / caída 97.91% / 161 ops | no (sesgo de supervivencia, no cuenta) |
| 173 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=30, rebalance=1, mode=largo3_btc50 | top 30 de hoy (sesgo), 1h | decisoria (rejilla WF) | 2025-26: +106.56% / caída 49.27% / 104 ops | no (sesgo de supervivencia, no cuenta) |
| 174 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=30, rebalance=1, mode=ls | top 30 de hoy (sesgo), 1h | decisoria (rejilla WF) | 2025-26: +146.36% / caída 64.69% / 181 ops | no (sesgo de supervivencia, no cuenta) |
| 175 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=30, rebalance=7, mode=largo3 | top 30 de hoy (sesgo), 1h | decisoria (rejilla WF) | 2025-26: +70.24% / caída 91.86% / 79 ops | no (sesgo de supervivencia, no cuenta) |
| 176 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=30, rebalance=7, mode=largo3_btc50 | top 30 de hoy (sesgo), 1h | decisoria (rejilla WF) | 2025-26: +69.85% / caída 35.87% / 44 ops | no (sesgo de supervivencia, no cuenta) |
| 177 | 2026-10-12/13 | rotacion | Rotación momentum | lookback=30, rebalance=7, mode=ls | top 30 de hoy (sesgo), 1h | decisoria (rejilla WF) | 2025-26: +111.22% / caída 57.92% / 66 ops | no (sesgo de supervivencia, no cuenta) |
| 178 | 2026-10-13 | rotacion (top30_dia) | Rotación momentum | lookback 14, diario, largo 3, filtro BTC>SMA50 (fija, preregistrada) | top 30 de cada día (sin sesgo), 1h | decisoria | año ciego 2024-25: +69.81% / 159.45% / 194 ops; 2025-26: -35.53% / 153.4% | no (falla 3 de 4 trimestres) |
| 179 | 2026-10-13 | rotacion (top30_dia) | Rotación momentum | misma regla sin las 2 monedas que más aportaron | top 30 de cada día menos 2, 1h | sensibilidad | 2024-25: +31.99% / 157.69%; 2025-26: -87.73% / 124.28% | no |
| 180 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 2.5R, trailing 1R→0.5R, sin salida por tiempo | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 181 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 2.5R, trailing 1R→0.5R, salida 72 h | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 182 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 2.5R, trailing 1.5R→1R, sin salida por tiempo | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 183 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 2.5R, trailing 1.5R→1R, salida 72 h | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 184 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 2.5R, trailing 2R→1R, sin salida por tiempo | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 185 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 2.5R, trailing 2R→1R, salida 72 h | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 186 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 3R, trailing 1R→0.5R, salida 72 h | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 187 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 3R, trailing 1.5R→1R, sin salida por tiempo | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 188 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 3R, trailing 1.5R→1R, salida 72 h | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 189 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 3R, trailing 2R→1R, sin salida por tiempo | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 190 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 3R, trailing 2R→1R, salida 72 h | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 191 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 4R, trailing 1R→0.5R, sin salida por tiempo | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 192 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 4R, trailing 1R→0.5R, salida 72 h | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 193 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 4R, trailing 1.5R→1R, sin salida por tiempo | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 194 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 4R, trailing 1.5R→1R, salida 72 h | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 195 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 4R, trailing 2R→1R, sin salida por tiempo | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 196 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 4R, trailing 2R→1R, salida 72 h | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 197 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 5R, trailing 1R→0.5R, sin salida por tiempo | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 198 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 5R, trailing 1R→0.5R, salida 72 h | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 199 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 5R, trailing 1.5R→1R, sin salida por tiempo | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 200 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 5R, trailing 1.5R→1R, salida 72 h | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 201 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 5R, trailing 2R→1R, sin salida por tiempo | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 202 | 2026-10-13 | mesa | Mesa: salidas (variante) | meta 5R, trailing 2R→1R, salida 72 h | 12 monedas, 5 min | decisoria (rejilla WF) | sin resultado por combinación; WF elegido: 2024-25 -37.2%/61.06% vs mesa +2.9%; 2025-26 -35.8%/47.34% vs mesa -37.5% | no |
| 203 | 2026-10-13 | mesa | Mesa: Escéptico (ablación) | sin regla beneficio/riesgo mínimo | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +17.6%/58.18% ; -65.5%/75.5% (idéntico: nunca veta) | — (informativa) |
| 204 | 2026-10-13 | mesa | Mesa: Escéptico (ablación) | sin regla stop en número redondo | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +88.4%/45.35% ; -56.5%/70.98% | — (informativa) |
| 205 | 2026-10-13 | mesa | Mesa: Escéptico (ablación) | sin regla financiación saturada | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +23.6%/56.04% ; -68.0%/76.25% | — (informativa) |
| 206 | 2026-10-13 | mesa | Mesa: Escéptico (ablación) | sin regla sentimiento en contra | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +17.6%/58.18% ; -65.5%/75.5% (idéntico) | — (informativa) |
| 207 | 2026-10-13 | mesa | Mesa: Escéptico (ablación) | sin Escéptico | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +71.4%/44.98% ; -62.2%/71.17% | — (informativa) |
| 208 | 2026-10-13 | mesa | Mesa: tamaño | fijo 2%, 1x | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +1.1%/52.32% ; -62.8%/73.15% | — (informativa) |
| 209 | 2026-10-13 | mesa | Mesa: tamaño | fijo 5%, 1x | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +30.4%/54.66% ; -65.2%/75.28% | — (informativa) |
| 210 | 2026-10-13 | mesa | Mesa: tamaño | fijo 10%, 1x | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +17.6%/58.18% ; -65.5%/75.5% | — (informativa) |
| 211 | 2026-10-13 | mesa | Mesa: tamaño | calidad 1-15%, 3x | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: -51.7%/91.87% ; -95.5%/98.49% | — (informativa) |
| 212 | 2026-10-13 | mesa | Mesa: tamaño | fijo 5%, 3x | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: -42.3%/84.43% ; -93.9%/97.71% | — (informativa) |
| 213 | 2026-10-13 | mesa | Mesa: tamaño | fijo 10%, 3x | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: -44.7%/90.29% ; -95.3%/98.4% | — (informativa) |
| 214 | 2026-10-13 | mesa | Mesa: tamaño | medio Kelly WF, 1x | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: -3.0%/36.51% ; -25.1%/44.6% | — (informativa) |
| 215 | 2026-10-13 | mesa | Mesa: tamaño | medio Kelly WF, 3x | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +16.1%/36.68% ; -20.7%/53.33% | — (informativa) |
| 216 | 2026-10-13 | mesa | Mesa: filtro de régimen | a) BTC>SMA200 solo largos | 12 monedas, 5 min | decisoria | 2024-25 ; 2025-26: +76.1%/53.25% ; -12.8%/33.87% | no |
| 217 | 2026-10-13 | mesa | Mesa: filtro de régimen | b) BTC>SMA50 solo largos (luego adoptado en práctica) | 12 monedas, 5 min | decisoria | 2024-25 ; 2025-26: +78.2%/46.89% ; -7.4%/35.75% | no |
| 218 | 2026-10-13 | mesa | Mesa: filtro de régimen | c) tendencia 4h moneda + diaria BTC | 12 monedas, 5 min | decisoria | 2024-25 ; 2025-26: +99.6%/40.39% ; -48.9%/50.26% | no (pasa solo 2024-25) |
| 219 | 2026-10-13 | mesa | Mesa: filtro de régimen | d) largos sobre SMA200 BTC, cortos debajo | 12 monedas, 5 min | decisoria | 2024-25 ; 2025-26: +74.2%/52.88% ; -40.5%/55.64% | no |
| 220 | 2026-10-13 | mesa | Mesa: filtro de régimen | e) sin operar si BTC cae en 30 d | 12 monedas, 5 min | decisoria | 2024-25 ; 2025-26: -19.0%/65.29% ; -9.3%/39.38% | no |
| 221 | 2026-10-13 | mesa | Mesa: filtro de régimen | f) sin entradas ±12 h FOMC/IPC | 12 monedas, 5 min | decisoria | 2024-25 ; 2025-26: +41.5%/47.28% ; -65.4%/75.52% | no |
| 222 | 2026-10-13 | mesa | Mesa: filtro de régimen | g1) largos solo tras purga de OI | 12 monedas, 5 min | decisoria | 2024-25 ; 2025-26: +36.0%/52.5% ; -76.2%/78.3% | no |
| 223 | 2026-10-13 | mesa | Mesa: filtro de régimen | g2) sin largos si OI +10% en 7 d con precio plano | 12 monedas, 5 min | decisoria | 2024-25 ; 2025-26: +20.1%/59.02% ; -64.5%/74.97% | no |
| 224 | 2026-10-13 | sentimiento | Mesa: umbral del Escéptico de sentimiento | umbral -0.5 | 12 monedas, 5 min | decisoria | 2024-25 ; 2025-26: +17.6%/58.18% ; -60.1%/73.15% (= apagada) | no |
| 225 | 2026-10-13 | sentimiento | Mesa: umbral del Escéptico de sentimiento | umbral -0.3 | 12 monedas, 5 min | decisoria | 2024-25 ; 2025-26: +17.6%/58.18% ; -60.1%/73.15% (= apagada) | no |
| 226 | 2026-10-13 | sentimiento | Mesa: umbral del Escéptico de sentimiento | umbral -0.2 | 12 monedas, 5 min | decisoria | 2024-25 ; 2025-26: +17.6%/58.18% ; -60.1%/73.15% (= apagada) | no |
| 227 | 2026-10-13 | sentimiento | Mesa: umbral del Escéptico de sentimiento | umbral -0.1 | 12 monedas, 5 min | decisoria | 2024-25 ; 2025-26: +3.6%/54.76% ; -59.5%/73.89% | no |
| 228 | 2026-10-14 | ewmac | EWMAC (Carver) | 4 pares EWMA, top 3, preregistrada | 12 monedas, 1d | decisoria | 2024-25 +31.5%/42.83% (0.74 vs 1.67); 2025-26 +14.4%/30.74% (0.47 vs -0.21) | no |
| 229 | 2026-10-14 | cartera | Cartera mesa práctica + EWMAC | 50/50, rebalanceo mensual | mesa 5 min + EWMAC 1d | decisoria | 2024-25 +69.9%/39.72% (1.76 vs 1.86); 2025-26 +21.1%/19.59% (1.08 vs 0.21) | no |
| 230 | 2026-10-14 | cartera | Cartera mesa práctica + EWMAC | 70/30, rebalanceo mensual | mesa 5 min + EWMAC 1d | decisoria | 2024-25 +75.5%/40.49% (1.86 vs 1.86); 2025-26 +16.7%/16.58% (1.01 vs 0.21) | no |
| 231 | 2026-10-14 | saturado | Mesa: filtro lado saturado (OI) | L5 sobre régimen b + eventos | 12 monedas, 5 min | decisoria | 2024-25 ; 2025-26: +80.1%/45.65% ; +9.2%/32.71% | sí (ayuda) |
| 232 | 2026-10-14 | saturado | Mesa: filtro lado saturado (OI) | L10 sobre régimen b + eventos | 12 monedas, 5 min | decisoria | 2024-25 ; 2025-26: +84.7%/45.84% ; +6.6%/32.33% | no |
| 233 | 2026-10-14 | saturado | Mesa: filtro lado saturado (OI) | L15 sobre régimen b + eventos | 12 monedas, 5 min | decisoria | 2024-25 ; 2025-26: +84.7%/45.84% ; +6.6%/32.33% | no |
| 234 | 2026-10-14 | saturado | Mesa: filtro lado saturado (OI) | S12 sobre régimen b + eventos | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +81.2%/46.89% ; +6.6%/32.33% (= base, sin cortos) | — (informativa) |
| 235 | 2026-10-14 | saturado | Mesa: filtro lado saturado (OI) | S24 sobre régimen b + eventos | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +81.2%/46.89% ; +6.6%/32.33% (= base) | — (informativa) |
| 236 | 2026-10-14 | saturado | Mesa: filtro lado saturado (OI) | L5 sobre solo eventos | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +51.7%/46.53% ; -59.8%/75.49% | — (informativa) |
| 237 | 2026-10-14 | saturado | Mesa: filtro lado saturado (OI) | L10 sobre solo eventos | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +40.5%/50.87% ; -62.1%/76.88% | — (informativa) |
| 238 | 2026-10-14 | saturado | Mesa: filtro lado saturado (OI) | L15 sobre solo eventos | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +25.4%/56.13% ; -62.0%/76.83% | — (informativa) |
| 239 | 2026-10-14 | saturado | Mesa: filtro lado saturado (OI) | S12 sobre solo eventos | 12 monedas, 5 min | decisoria | 2024-25 ; 2025-26: +111.8%/46.23% ; -62.6%/76.44% | no |
| 240 | 2026-10-14 | saturado | Mesa: filtro lado saturado (OI) | S24 sobre solo eventos | 12 monedas, 5 min | decisoria | 2024-25 ; 2025-26: +79.8%/44.93% ; -61.0%/75.46% | no |
| 241 | 2026-10-15 | volatilidad | Mesa: freno de volatilidad BTC 7d | V80 sobre régimen b + eventos | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +34.9%/43.95% ; -21.3%/28.14% | — (informativa) |
| 242 | 2026-10-15 | volatilidad | Mesa: freno de volatilidad BTC 7d | V90 sobre régimen b + eventos | 12 monedas, 5 min | decisoria | 2024-25 ; 2025-26: +66.9%/44.02% ; -9.5%/31.44% | no |
| 243 | 2026-10-15 | volatilidad | Mesa: freno de volatilidad BTC 7d | V95 sobre régimen b + eventos | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +87.1%/45.14% ; +6.6%/32.33% | — (informativa) |
| 244 | 2026-10-15 | volatilidad | Mesa: freno de volatilidad BTC 7d | V80 sobre solo eventos | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +15.8%/50.04% ; -53.0%/61.63% | — (informativa) |
| 245 | 2026-10-15 | volatilidad | Mesa: freno de volatilidad BTC 7d | V90 sobre solo eventos | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +26.9%/55.06% ; -50.0%/67.76% | — (informativa) |
| 246 | 2026-10-15 | volatilidad | Mesa: freno de volatilidad BTC 7d | V95 sobre solo eventos | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +21.4%/57.53% ; -63.3%/78.08% | — (informativa) |
| 247 | 2026-10-15 | breakout | Ruptura de volatilidad (Larry Williams) | A pura, k=0.5 | 12 monedas, 1d | decisoria | 2024-25 ; 2025-26: -55.7%/72.54% ; -64.7%/66.27% | no |
| 248 | 2026-10-15 | breakout | Ruptura de volatilidad (Larry Williams) | A pura, k=0.25 | 12 monedas, 1d | sensibilidad | 2024-25 ; 2025-26: -89.9%/91.98% ; -88.9%/88.88% | — (informativa) |
| 249 | 2026-10-15 | breakout | Ruptura de volatilidad (Larry Williams) | A pura, k=0.75 | 12 monedas, 1d | sensibilidad | 2024-25 ; 2025-26: -14.4%/58.77% ; -46.2%/52.82% | — (informativa) |
| 250 | 2026-10-15 | breakout | Ruptura de volatilidad (Larry Williams) | B con frenos, k=0.5 | 12 monedas, 1d | decisoria | 2024-25 ; 2025-26: -59.5%/73.04% ; -21.2%/24.73% | no |
| 251 | 2026-10-15 | breakout | Ruptura de volatilidad (Larry Williams) | B con frenos, k=0.25 | 12 monedas, 1d | sensibilidad | 2024-25 ; 2025-26: -74.0%/81.38% ; -35.8%/35.84% | — (informativa) |
| 252 | 2026-10-15 | breakout | Ruptura de volatilidad (Larry Williams) | B con frenos, k=0.75 | 12 monedas, 1d | sensibilidad | 2024-25 ; 2025-26: -4.5%/49.54% ; -10.3%/20.35% | — (informativa) |
| 253 | 2026-10-15 | rango | Rebote a la media (Bollinger+ADX) | A pura, base | 12 monedas, 1d | decisoria | 2024-25 ; 2025-26: -34.3%/45.55% ; -27.0%/28.15% | no |
| 254 | 2026-10-15 | rango | Rebote a la media (Bollinger+ADX) | A pura, ADX<25 | 12 monedas, 1d | sensibilidad | 2024-25 ; 2025-26: -25.9%/44.88% ; -37.9%/37.87% | — (informativa) |
| 255 | 2026-10-15 | rango | Rebote a la media (Bollinger+ADX) | A pura, 2,5 desv. | 12 monedas, 1d | sensibilidad | 2024-25 ; 2025-26: -24.1%/27.96% ; -15.4%/18.71% | — (informativa) |
| 256 | 2026-10-15 | rango | Rebote a la media (Bollinger+ADX) | B con frenos, base | 12 monedas, 1d | decisoria | 2024-25 ; 2025-26: +15.8%/8.91% ; -1.6%/7.63% | no (2024-25 sí, 2025-26 no) |
| 257 | 2026-10-15 | rango | Rebote a la media (Bollinger+ADX) | B con frenos, ADX<25 | 12 monedas, 1d | sensibilidad | 2024-25 ; 2025-26: +10.9%/12.39% ; +0.2%/7.63% | — (informativa) |
| 258 | 2026-10-15 | rango | Rebote a la media (Bollinger+ADX) | B con frenos, 2,5 desv. | 12 monedas, 1d | sensibilidad | 2024-25 ; 2025-26: +6.0%/5.15% ; -1.9%/5.84% | — (informativa) |
| 259 | 2026-10-15 | rango | Rebote a la media (Bollinger+ADX) | A pura, base | 12 monedas, 4h | decisoria | 2024-25 ; 2025-26: -53.0%/53.1% ; -27.8%/36.45% | no |
| 260 | 2026-10-15 | rango | Rebote a la media (Bollinger+ADX) | A pura, ADX<25 | 12 monedas, 4h | sensibilidad | 2024-25 ; 2025-26: -69.5%/69.63% ; -32.2%/42.57% | — (informativa) |
| 261 | 2026-10-15 | rango | Rebote a la media (Bollinger+ADX) | A pura, 2,5 desv. | 12 monedas, 4h | sensibilidad | 2024-25 ; 2025-26: -51.2%/51.27% ; +5.5%/14.82% | — (informativa) |
| 262 | 2026-10-15 | rango | Rebote a la media (Bollinger+ADX) | B con frenos, base | 12 monedas, 4h | decisoria | 2024-25 ; 2025-26: -19.8%/21.9% ; -6.9%/11.67% | no |
| 263 | 2026-10-15 | rango | Rebote a la media (Bollinger+ADX) | B con frenos, ADX<25 | 12 monedas, 4h | sensibilidad | 2024-25 ; 2025-26: -18.8%/25.09% ; -2.1%/10.73% | — (informativa) |
| 264 | 2026-10-15 | rango | Rebote a la media (Bollinger+ADX) | B con frenos, 2,5 desv. | 12 monedas, 4h | sensibilidad | 2024-25 ; 2025-26: -24.9%/26.09% ; -2.4%/6.71% | — (informativa) |
| 265 | 2026-10-15 | oro | Ruptura de Londres | costes base | PAXGUSDT (oro), 1h | decisoria | 2024-25 ; 2025-26: -7.7%/13.3% ; +26.6%/7.14% | no (solo 2025-26) |
| 266 | 2026-10-15 | oro | Ruptura de Londres | costes ×2 | PAXGUSDT (oro), 1h | sensibilidad | 2024-25 ; 2025-26: -13.4%/15.62% ; +23.1%/7.67% | — (informativa) |
| 267 | 2026-10-15 | oro | Tortugas (sistema 1) | costes base | PAXGUSDT (oro), 1d | decisoria | 2024-25 ; 2025-26: -0.4%/6.25% ; +1.2%/8.13% | no |
| 268 | 2026-10-15 | oro | Tortugas (sistema 1) | costes ×2 | PAXGUSDT (oro), 1d | sensibilidad | 2024-25 ; 2025-26: -1.6%/6.6% ; +0.7%/8.28% | — (informativa) |
| 269 | 2026-10-15 | oro | Reversión tras noticia | costes base | PAXGUSDT (oro), 1h | decisoria | 2024-25 ; 2025-26: -1.0%/1.69% ; +0.2%/2.43% | no |
| 270 | 2026-10-15 | oro | Reversión tras noticia | costes ×2 | PAXGUSDT (oro), 1h | sensibilidad | 2024-25 ; 2025-26: -1.6%/2.05% ; -0.3%/2.58% | — (informativa) |
| 271 | 2026-10-15 | oro | Ruptura de Londres | costes base | BTCUSDT, 1h | decisoria | 2024-25 ; 2025-26: -14.8%/25.49% ; -17.8%/22.35% | no |
| 272 | 2026-10-15 | oro | Ruptura de Londres | costes ×2 | BTCUSDT, 1h | sensibilidad | 2024-25 ; 2025-26: -45.0%/47.1% ; -48.1%/49.12% | — (informativa) |
| 273 | 2026-10-15 | oro | Tortugas (sistema 1) | costes base | BTCUSDT, 1d | decisoria | 2024-25 ; 2025-26: -4.8%/10.61% ; +9.2%/3.25% | no (solo 2025-26) |
| 274 | 2026-10-15 | oro | Tortugas (sistema 1) | costes ×2 | BTCUSDT, 1d | sensibilidad | 2024-25 ; 2025-26: -5.5%/11.32% ; +8.7%/3.58% | — (informativa) |
| 275 | 2026-10-15 | oro | Reversión tras noticia | costes base | BTCUSDT, 1h | decisoria | 2024-25 ; 2025-26: -5.5%/5.79% ; -6.4%/6.49% | no |
| 276 | 2026-10-15 | oro | Reversión tras noticia | costes ×2 | BTCUSDT, 1h | sensibilidad | 2024-25 ; 2025-26: -9.9%/9.87% ; -10.1%/10.12% | — (informativa) |
| 277 | 2026-10-13 | carry | Carry de financiación neutral | media de 3 pagos > 0.005%/8h | 4 monedas, 8 h, 2020-2026 | decisoria (rejilla WF) | +14.1%/14.87% (todo el periodo) | no (fuera de la regla de los dos años; ver informe) |
| 278 | 2026-10-13 | carry | Carry de financiación neutral | media de 3 pagos > 0.01%/8h | 4 monedas, 8 h, 2020-2026 | decisoria (rejilla WF) | +45.0%/1.68% (todo el periodo) | no (fuera de la regla de los dos años; ver informe) |
| 279 | 2026-10-13 | carry | Carry de financiación neutral | media de 3 pagos > 0.02%/8h | 4 monedas, 8 h, 2020-2026 | decisoria (rejilla WF) | +44.1%/1.65% (todo el periodo) | no (fuera de la regla de los dos años; ver informe) |
| 280 | 2026-10-13 | carry | Carry de financiación neutral | media de 9 pagos > 0.005%/8h | 4 monedas, 8 h, 2020-2026 | decisoria (rejilla WF) | +44.6%/3.4% (todo el periodo) | no (fuera de la regla de los dos años; ver informe) |
| 281 | 2026-10-13 | carry | Carry de financiación neutral | media de 9 pagos > 0.01%/8h | 4 monedas, 8 h, 2020-2026 | decisoria (rejilla WF) | +48.0%/1.47% (todo el periodo) | no (fuera de la regla de los dos años; ver informe) |
| 282 | 2026-10-13 | carry | Carry de financiación neutral | media de 9 pagos > 0.02%/8h | 4 monedas, 8 h, 2020-2026 | decisoria (rejilla WF) | +44.5%/1.24% (todo el periodo) | no (fuera de la regla de los dos años; ver informe) |
| 283 | 2026-10-13 | carry | Carry de financiación neutral | media de 21 pagos > 0.005%/8h | 4 monedas, 8 h, 2020-2026 | decisoria (rejilla WF) | +53.4%/3.27% (todo el periodo) | no (fuera de la regla de los dos años; ver informe) |
| 284 | 2026-10-13 | carry | Carry de financiación neutral | media de 21 pagos > 0.01%/8h | 4 monedas, 8 h, 2020-2026 | decisoria (rejilla WF) | +50.1%/1.53% (todo el periodo) | no (fuera de la regla de los dos años; ver informe) |
| 285 | 2026-10-13 | carry | Carry de financiación neutral | media de 21 pagos > 0.02%/8h | 4 monedas, 8 h, 2020-2026 | decisoria (rejilla WF) | +44.5%/1.34% (todo el periodo) | no (fuera de la regla de los dos años; ver informe) |
| 286 | 2026-10-13 | carry | Carry de financiación neutral | siempre dentro, todas las monedas | 4 monedas, 8 h, 2020-2026 | decisoria (rejilla WF) | +26.1%/1.15% (todo el periodo) | no (fuera de la regla de los dos años; ver informe) |
| 287 | 2026-10-13 | carry | Carry de financiación neutral | siempre dentro, BTCUSDT | 4 monedas, 8 h, 2020-2026 | decisoria (rejilla WF) | +39.6%/1.6% (todo el periodo) | no (fuera de la regla de los dos años; ver informe) |
| 288 | 2026-10-16 | rsi2 | RSI-2 de Connors | A pura, umbral 10 | 12 monedas, 1d | decisoria | 2024-25 ; 2025-26: +2.6%/24.67% ; +3.1%/10.5% (neto/caída 0,11 ; 0,29) | no |
| 289 | 2026-10-16 | rsi2 | RSI-2 de Connors | B con frenos, umbral 10 | 12 monedas, 1d | decisoria | 2024-25 ; 2025-26: -11.4%/24.0% ; +1.9%/3.85% (−0,47 ; 0,49) | no |
| 290 | 2026-10-16 | rsi2 | RSI-2 de Connors | A pura, umbral 5 | 12 monedas, 1d | sensibilidad | 2024-25 ; 2025-26: +36.9%/15.17% ; -2.1%/7.88% (2,43 ; −0,26) | — (informativa) |
| 291 | 2026-10-16 | rsi2 | RSI-2 de Connors | B con frenos, umbral 5 | 12 monedas, 1d | sensibilidad | 2024-25 ; 2025-26: +10.9%/12.93% ; -0.6%/2.86% (0,84 ; −0,20) | — (informativa) |
| 292 | 2026-10-16 | rsi2 | RSI-2 de Connors | Espejo en corto (A), umbral 10 | 12 monedas, 1d | sensibilidad | 2024-25 ; 2025-26: -32.4%/46.13% ; -3.0%/39.03% (−0,70 ; −0,08) | — (informativa) |
| 293 | 2026-10-16 | largo | Media de 10 meses (Faber) | costes base | PAXGUSDT (oro), mensual | decisoria | 2024-25 ; 2025-26: +38.1%/8.69% ; -6.2%/30.54% (DSR 0.002) | no |
| 294 | 2026-10-16 | largo | Media de 10 meses (Faber) | costes base | BTCUSDT, mensual | decisoria | 2024-25 ; 2025-26: +65.3%/30.36% ; -19.5%/26.88% (DSR 0.0) | no |
| 295 | 2026-10-16 | largo | Momento de 12 meses (MOP) | costes base | PAXGUSDT (oro), mensual | decisoria | 2024-25 ; 2025-26: +38.1%/8.69% ; -4.2%/31.15% (DSR 0.002) | no |
| 296 | 2026-10-16 | largo | Momento de 12 meses (MOP) | costes base | BTCUSDT, mensual | decisoria | 2024-25 ; 2025-26: +65.3%/30.36% ; -12.8%/27.33% (DSR 0.001) | no |
| 297 | 2026-10-16 | largo | Momento dual (Antonacci) | costes base | BTC u oro, mensual | decisoria | 2024-25 ; 2025-26: +65.0%/22.47% ; -28.1%/30.91% (DSR 0.0) | no |
| 298 | 2026-10-16 | largo | Media de 10 meses (Faber) | costes ×2 | PAXGUSDT (oro), mensual | sensibilidad | 2024-25 ; 2025-26: +26.7%/11.17% ; -11.7%/33.44% (DSR 0.001) | — (informativa) |
| 299 | 2026-10-16 | largo | Media de 10 meses (Faber) | costes ×2 | BTCUSDT, mensual | sensibilidad | 2024-25 ; 2025-26: +53.6%/32.76% ; -20.9%/27.37% (DSR 0.0) | — (informativa) |
| 300 | 2026-10-16 | largo | Momento de 12 meses (MOP) | costes ×2 | PAXGUSDT (oro), mensual | sensibilidad | 2024-25 ; 2025-26: +26.7%/11.17% ; -11.8%/34.44% (DSR 0.001) | — (informativa) |
| 301 | 2026-10-16 | largo | Momento de 12 meses (MOP) | costes ×2 | BTCUSDT, mensual | sensibilidad | 2024-25 ; 2025-26: +53.6%/32.76% ; -14.0%/27.93% (DSR 0.001) | — (informativa) |
| 302 | 2026-10-16 | largo | Momento dual (Antonacci) | costes ×2 | BTC u oro, mensual | sensibilidad | 2024-25 ; 2025-26: +49.9%/24.49% ; -33.5%/34.42% (DSR 0.0) | — (informativa) |
| 303 | 2026-10-16 | carry_btceth | Carry de financiación (spot + perpetuo corto) | media de 21 pagos ≥ 0,0042%/8h, salir < 0 | BTCUSDT, 8 h | decisoria | 2024-25 ; 2025-26: +3.47%/0.27% ; +0.95%/0.24% (DSR 0.788) | no |
| 304 | 2026-10-16 | carry_btceth | Carry de financiación (spot + perpetuo corto) | media de 21 pagos ≥ 0,0042%/8h, salir < 0 | ETHUSDT, 8 h | decisoria | 2024-25 ; 2025-26: +2.56%/0.39% ; +0.66%/0.25% (DSR 0.405) | no |
| 305 | 2026-10-16 | carry_btceth | Carry de financiación (spot + perpetuo corto) | siempre dentro | BTCUSDT, 8 h | sensibilidad | 2024-25 ; 2025-26: +3.14%/0.22% ; +1.02%/0.14% (DSR 1.0) | — (informativa) |
| 306 | 2026-10-16 | carry_btceth | Carry de financiación (spot + perpetuo corto) | siempre dentro | ETHUSDT, 8 h | sensibilidad | 2024-25 ; 2025-26: +2.39%/0.13% ; +0.62%/0.13% (DSR 1.0) | — (informativa) |
| 307 | 2026-10-16 | oro_dia | Ruptura del rango de apertura de NY (Crabel) | rango 30 min | PAXGUSDT (oro), 15 min | decisoria | 2024-25 ; 2025-26: -7.7%/34.64% ; -6.1%/21.06% (DSR 0.001) | no |
| 308 | 2026-10-16 | oro_dia | Ruptura del rango de apertura de NY (Crabel) | rango 60 min | PAXGUSDT (oro), 15 min | decisoria | 2024-25 ; 2025-26: -21.7%/35.08% ; +8.9%/11.46% (DSR 0.014) | no |
| 309 | 2026-10-16 | oro_dia | Impulso dentro del día (Gao y otros) | 19:00-20:00 UTC | PAXGUSDT (oro), 15 min | decisoria | 2024-25 ; 2025-26: -5.3%/5.55% ; +0.2%/5.34% (DSR 0.003) | no |
| 310 | 2026-10-16 | oro_dia | Ruptura del rango de apertura de NY (Crabel) | rango 30 min, costes ×2 | PAXGUSDT (oro), 15 min | sensibilidad | 2024-25 ; 2025-26: -19.7%/38.66% ; -12.3%/24.69% (DSR 0.0) | — (informativa) |
| 311 | 2026-10-16 | oro_dia | Ruptura del rango de apertura de NY (Crabel) | rango 60 min, costes ×2 | PAXGUSDT (oro), 15 min | sensibilidad | 2024-25 ; 2025-26: -29.2%/39.39% ; +4.0%/11.94% (DSR 0.006) | — (informativa) |
| 312 | 2026-10-16 | oro_dia | Impulso dentro del día (Gao y otros) | 19:00-20:00 UTC, costes ×2 | PAXGUSDT (oro), 15 min | sensibilidad | 2024-25 ; 2025-26: -9.1%/9.35% ; -2.7%/6.0% (DSR 0.0) | — (informativa) |
| 313 | 2026-10-16 | real | Bot real de futuros (mesa con frenos) | riesgo fijo 2%, 31,69 USDT, mínimos de Binance | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +13.3%/51.26% ; +13.1%/28.43% (DSR 0.01) | — (informativa) |
| 314 | 2026-10-16 | opciones_xsp | Spread alcista XSP 1 USD (Black-Scholes con VIX) | mensual siempre, 30 días, ATM/+1 | XSP (S&P 500), diario | decisoria | 2024-25 ; 2025-26: +72.2%/52.75% ; +51.2%/73.14% (DSR 0.025) | no |
| 315 | 2026-10-16 | opciones_xsp | Spread alcista XSP 1 USD (Black-Scholes con VIX) | solo sobre la media de 200 días | XSP (S&P 500), diario | decisoria | 2024-25 ; 2025-26: +79.7%/35.17% ; +51.2%/73.14% (DSR 0.025) | no |
| 316 | 2026-10-16 | opciones_xsp | Spread alcista XSP 1 USD (Black-Scholes con VIX) | mensual siempre, costes ×2 | XSP (S&P 500), diario | sensibilidad | 2024-25 ; 2025-26: +24.6%/70.64% ; +3.5%/90.63% (DSR 0.015) | — (informativa) |
| 317 | 2026-10-16 | opciones_xsp | Spread alcista XSP 1 USD (Black-Scholes con VIX) | media de 200 días, costes ×2 | XSP (S&P 500), diario | sensibilidad | 2024-25 ; 2025-26: +39.9%/48.78% ; +3.5%/90.63% (DSR 0.015) | — (informativa) |
| 318 | 2026-10-16 | copiar | Copiar bóvedas de Hyperliquid con un año ganador | A: top 10 por rentabilidad del año previo, 10% al líder | bóvedas de usuarios, diario | decisoria | 2024-25 ; 2025-26: +14.7%/17.3% ; -65.6%/73.7% (DSR 0.0; 2024-25 muestra corta: 1 bóveda elegible) | no |
| 319 | 2026-10-16 | copiar | Copiar bóvedas de Hyperliquid con un año ganador | B: top 10 por rentabilidad/caída del año previo, 10% al líder | bóvedas de usuarios, diario | decisoria | 2024-25 ; 2025-26: +14.7%/17.3% ; -51.7%/58.9% (DSR 0.0; 2024-25 muestra corta) | no |
| 320 | 2026-10-16 | copiar | Copiar bóvedas de Hyperliquid con un año ganador | A con 30% al líder | bóvedas de usuarios, diario | sensibilidad | 2024-25 ; 2025-26: +11.5%/14.3% ; -65.9%/73.7% (DSR 0.0) | — (informativa) |
| 321 | 2026-10-16 | copiar | Copiar bóvedas de Hyperliquid con un año ganador | A, top 30 | bóvedas de usuarios, diario | sensibilidad | 2024-25 ; 2025-26: +14.7%/17.3% ; -35.4%/47.1% (DSR 0.0) | — (informativa) |
| 322 | 2026-10-16 | cartera_xm | Cartera multi-mercado EWMAC (Carver), riesgo igual | 200 USD, lotes de XM, spread y swap de XM | 15 mercados de XM (forex, índices, metales, petróleo, BTC, ETH), 1d | decisoria | 2024-25 ; 2025-26: -3.5%/7.33% ; -4.6%/10.94% (DSR 0.0); con 200 USD solo cabe 1 de 15 mercados | no |
| 323 | 2026-10-16 | cartera_xm | Cartera multi-mercado EWMAC (Carver), riesgo igual | 100.000 USD (sin efecto del lote mínimo) | 15 mercados de XM, 1d | sensibilidad | 2024-25 ; 2025-26: +9.7%/17.24% ; -13.6%/33.02% (DSR 0.0) | — (informativa) |
| 324 | 2026-10-16 | cartera_xm | Cartera multi-mercado EWMAC (Carver), riesgo igual | 200 USD, spread y swap ×2 | 15 mercados de XM, 1d | sensibilidad | 2024-25 ; 2025-26: -4.0%/7.44% ; -3.1%/10.62% (DSR 0.001) | — (informativa) |
| 325 | 2026-10-16 | cartera_xm | Cartera multi-mercado EWMAC (Carver), riesgo igual | 1.000 USD, lotes de XM | 15 mercados de XM, 1d | sensibilidad | 2024-25 ; 2025-26: -17.3%/24.14% ; -7.1%/11.98% (DSR 0.0) | — (informativa) |
| 326 | 2026-10-16 | cartera_xm | Cartera multi-mercado EWMAC (Carver), riesgo igual | 5.000 USD, lotes de XM | 15 mercados de XM, 1d | sensibilidad | 2024-25 ; 2025-26: +13.6%/17.63% ; -26.5%/32.51% (DSR 0.0) | — (informativa) |
| 327 | 2026-10-16 | cripto_xm | Ruptura de Londres (re-prueba con costos de XM) | spread 40 USD por BTC, sin comisión, lotes 0,01, 1.000 USD | BTCUSDT, 1h | decisoria | 2024-25 ; 2025-26: +31.2%/13.32% ; +8.1%/13.29% (DSR 0.011); gana a la mesa los dos años, no pasa el DSR | no |
| 328 | 2026-10-16 | cripto_xm | Ruptura de Londres (re-prueba con costos de XM) | spread ×2 | BTCUSDT, 1h | sensibilidad | 2024-25 ; 2025-26: +14.0%/16.55% ; -7.4%/18.53% (DSR 0.001) | — (informativa) |
| 329 | 2026-10-16 | cripto_xm | Ruptura de Londres (re-prueba con costos de XM) | 200 USD (efecto del lote mínimo) | BTCUSDT, 1h | sensibilidad | 2024-25 ; 2025-26: +3.6%/1.77% ; +0.8%/6.19% (4 y 28 ops: el lote mínimo impide casi todo) | — (informativa) |
| 330 | 2026-10-17 | grid | Cuadrícula semanal al contado (Spot Grid), 20 escalones geométricos | BTC ±10%, 0,1% por lado | BTCUSDT, 1h | decisoria | 2024-25 ; 2025-26: -0.0%/9.62% ; -15.0%/18.85% (DSR 0.0); idas y vueltas +314 ; +254 USDT, inventario -314 ; -404 USDT | no |
| 331 | 2026-10-17 | grid | Cuadrícula semanal al contado (Spot Grid), 20 escalones geométricos | ETH ±10%, 0,1% por lado | ETHUSDT, 1h | decisoria | 2024-25 ; 2025-26: -29.4%/33.13% ; -29.0%/34.68% (DSR 0.0); idas y vueltas +499 ; +375 USDT, inventario -793 ; -665 USDT | no |
| 332 | 2026-10-17 | grid | Cuadrícula semanal al contado (Spot Grid), 20 escalones geométricos | BTC y ETH a mitades ±10%, 0,1% por lado | BTCUSDT + ETHUSDT, 1h | decisoria | 2024-25 ; 2025-26: -15.8%/20.09% ; -22.2%/26.78% (DSR 0.0); idas y vueltas +420 ; +318 USDT, inventario -578 ; -540 USDT | no |
| 333 | 2026-10-17 | grid | Cuadrícula semanal al contado (Spot Grid), 20 escalones geométricos | BTC ±10%, mejor caso maker | BTCUSDT, 1h | sensibilidad | 2024-25 ; 2025-26: +8.0%/7.73% ; -8.6%/14.71% (DSR 0.0); idas y vueltas +399 ; +322 USDT, inventario -319 ; -408 USDT | — (informativa) |
| 334 | 2026-10-17 | grid | Cuadrícula semanal al contado (Spot Grid), 20 escalones geométricos | ETH ±10%, mejor caso maker | ETHUSDT, 1h | sensibilidad | 2024-25 ; 2025-26: -18.2%/28.37% ; -20.2%/29.24% (DSR 0.0); idas y vueltas +654 ; +485 USDT, inventario -836 ; -687 USDT | — (informativa) |
| 335 | 2026-10-17 | grid | Cuadrícula semanal al contado (Spot Grid), 20 escalones geométricos | mitades ±10%, mejor caso maker | BTCUSDT + ETHUSDT, 1h | sensibilidad | 2024-25 ; 2025-26: -5.7%/16.66% ; -14.4%/21.81% (DSR 0.0); idas y vueltas +543 ; +407 USDT, inventario -600 ; -552 USDT | — (informativa) |
| 336 | 2026-10-17 | grid | Cuadrícula semanal al contado (Spot Grid), 20 escalones geométricos | BTC ±5% | BTCUSDT, 1h | sensibilidad | 2024-25 ; 2025-26: -19.0%/22.85% ; -31.7%/34.9% (DSR 0.0); idas y vueltas +276 ; +227 USDT, inventario -466 ; -544 USDT | — (informativa) |
| 337 | 2026-10-17 | grid | Cuadrícula semanal al contado (Spot Grid), 20 escalones geométricos | ETH ±5% | ETHUSDT, 1h | sensibilidad | 2024-25 ; 2025-26: -56.8%/57.35% ; -43.8%/46.75% (DSR 0.0); idas y vueltas +323 ; +280 USDT, inventario -891 ; -717 USDT | — (informativa) |
| 338 | 2026-10-17 | grid | Cuadrícula semanal al contado (Spot Grid), 20 escalones geométricos | BTC ±20% | BTCUSDT, 1h | sensibilidad | 2024-25 ; 2025-26: +5.2%/5.15% ; -5.0%/9.5% (DSR 0.001); idas y vueltas +231 ; +177 USDT, inventario -179 ; -227 USDT | — (informativa) |
| 339 | 2026-10-17 | grid | Cuadrícula semanal al contado (Spot Grid), 20 escalones geométricos | ETH ±20% | ETHUSDT, 1h | sensibilidad | 2024-25 ; 2025-26: -4.9%/13.32% ; -9.7%/18.62% (DSR 0.0); idas y vueltas +466 ; +326 USDT, inventario -514 ; -423 USDT | — (informativa) |
| 340 | 2026-10-18 | supertrend | Supertrend de freqtrade (FSupertrendStrategy, 3+3 Supertrend, largo y corto) | A tal cual (stop −26,5%) | BTCUSDT, 1h | decisoria | 2024-25 ; 2025-26: -19.5%/53.26% ; -33.2%/45.23% (DSR 0.0; 198 y 217 ops) | no |
| 341 | 2026-10-18 | supertrend | Supertrend de freqtrade (FSupertrendStrategy, 3+3 Supertrend, largo y corto) | A tal cual (stop −26,5%) | ETHUSDT, 1h | decisoria | 2024-25 ; 2025-26: -6.2%/60.54% ; -50.1%/60.54% (DSR 0.0; 265 y 249 ops) | no |
| 342 | 2026-10-18 | supertrend | Supertrend de freqtrade (FSupertrendStrategy, 3+3 Supertrend, largo y corto) | A tal cual (stop −26,5%) | BTCUSDT + ETHUSDT, 1h | decisoria | 2024-25 ; 2025-26: -12.8%/53.69% ; -41.6%/52.51% (DSR 0.0; 463 y 466 ops) | no |
| 343 | 2026-10-18 | supertrend | Supertrend de freqtrade (FSupertrendStrategy, 3+3 Supertrend, largo y corto) | B con frenos de la mesa (stop 1R, régimen b, eventos) | BTCUSDT, 1h | decisoria | 2024-25 ; 2025-26: +7.0%/11.88% ; -7.5%/11.47% (DSR 0.0; 97 y 64 ops) | no |
| 344 | 2026-10-18 | supertrend | Supertrend de freqtrade (FSupertrendStrategy, 3+3 Supertrend, largo y corto) | B con frenos de la mesa (stop 1R, régimen b, eventos) | ETHUSDT, 1h | decisoria | 2024-25 ; 2025-26: +26.9%/11.74% ; -6.3%/15.19% (DSR 0.001; 134 y 77 ops) | no |
| 345 | 2026-10-18 | supertrend | Supertrend de freqtrade (FSupertrendStrategy, 3+3 Supertrend, largo y corto) | B con frenos de la mesa (stop 1R, régimen b, eventos) | BTCUSDT + ETHUSDT, 1h | decisoria | 2024-25 ; 2025-26: +16.9%/11.06% ; -6.9%/12.43% (DSR 0.001; 231 y 141 ops) | no |
| 346 | 2026-10-18 | supertrend | Supertrend de freqtrade (FSupertrendStrategy, 3+3 Supertrend, largo y corto) | A juntas, costos ×2 | BTCUSDT + ETHUSDT, 1h | sensibilidad | 2024-25 ; 2025-26: -35.6%/60.99% ; -58.1%/64.15% (DSR 0.0; 461 y 463 ops) | — (informativa) |
| 347 | 2026-10-18 | supertrend | Supertrend de freqtrade (FSupertrendStrategy, 3+3 Supertrend, largo y corto) | B juntas, costos ×2 | BTCUSDT + ETHUSDT, 1h | sensibilidad | 2024-25 ; 2025-26: +6.7%/13.15% ; -12.7%/14.24% (DSR 0.0; 230 y 139 ops) | — (informativa) |
| 348 | 2026-10-19 | ichimoku | Nube de Ichimoku 9/26/52, solo compras | A tal cual (100%, 1x) | BTCUSDT, 1d | decisoria | 2024-25 ; 2025-26: +26.0%/17.38% ; +8.6%/10.51% (neto/caída 1.5 ; 0.82; DSR 0.009; 8 y 3 ops) | no |
| 349 | 2026-10-19 | ichimoku | Nube de Ichimoku 9/26/52, solo compras | A tal cual (100%, 1x) | ETHUSDT, 1d | decisoria | 2024-25 ; 2025-26: +55.0%/20.22% ; -14.7%/18.14% (neto/caída 2.72 ; -0.81; DSR 0.0; 7 y 8 ops) | no |
| 350 | 2026-10-19 | ichimoku | Nube de Ichimoku 9/26/52, solo compras | A tal cual (100%, 1x) | BTCUSDT + ETHUSDT, 1d | decisoria | 2024-25 ; 2025-26: +40.5%/13.88% ; -3.0%/8.78% (neto/caída 2.92 ; -0.34; DSR 0.002; 15 y 11 ops) | no |
| 351 | 2026-10-19 | ichimoku | Nube de Ichimoku 9/26/52, solo compras | B con frenos (stop en la Kijun, 2%, régimen b, eventos) | BTCUSDT, 1d | decisoria | 2024-25 ; 2025-26: +2.4%/10.1% ; +2.5%/5.66% (neto/caída 0.24 ; 0.45; DSR 0.006; 13 y 4 ops) | no |
| 352 | 2026-10-19 | ichimoku | Nube de Ichimoku 9/26/52, solo compras | B con frenos (stop en la Kijun, 2%, régimen b, eventos) | ETHUSDT, 1d | decisoria | 2024-25 ; 2025-26: +1.5%/8.17% ; -9.4%/10.4% (neto/caída 0.18 ; -0.9; DSR 0.0; 10 y 14 ops) | no |
| 353 | 2026-10-19 | ichimoku | Nube de Ichimoku 9/26/52, solo compras | B con frenos (stop en la Kijun, 2%, régimen b, eventos) | BTCUSDT + ETHUSDT, 1d | decisoria | 2024-25 ; 2025-26: +2.0%/8.66% ; -3.4%/5.18% (neto/caída 0.23 ; -0.66; DSR 0.0; 23 y 18 ops) | no |
| 354 | 2026-10-19 | ichimoku | Nube de Ichimoku 9/26/52, solo compras | A juntas, costos ×2 | BTCUSDT + ETHUSDT, 1d | sensibilidad | 2024-25 ; 2025-26: +39.1%/14.08% ; -3.7%/8.98% (neto/caída 2.77 ; -0.41; DSR 0.001; 15 y 11 ops) | — (informativa) |
| 355 | 2026-10-19 | ichimoku | Nube de Ichimoku 9/26/52, solo compras | B juntas, costos ×2 | BTCUSDT + ETHUSDT, 1d | sensibilidad | 2024-25 ; 2025-26: +1.1%/9.17% ; -4.2%/5.54% (neto/caída 0.12 ; -0.76; DSR 0.0; 23 y 18 ops) | — (informativa) |
| 356 | 2026-10-19 | freno_caida | Mesa actual (freno b y eventos) con freno por caída de la cuenta | 1x con freno (riesgo ×0,5 al −10%, pausa al −20% hasta el bloque siguiente) | 12 monedas, 5 min | decisoria | 2024-25 ; 2025-26: +86.2%/44.95% ; +5.9%/32.51% (neto/caída 1.92 ; 0.18; DSR 0.005; 350 y 203 ops) | no |
| 357 | 2026-10-19 | freno_caida | Mesa actual (freno b y eventos) con freno por caída de la cuenta | 3x con freno (riesgo ×0,5 al −10%, pausa al −20% hasta el bloque siguiente) | 12 monedas, 5 min | decisoria | 2024-25 ; 2025-26: -13.7%/61.52% ; -45.5%/65.59% (neto/caída -0.22 ; -0.69; DSR 0.001; 113 y 94 ops) | no |
| 358 | 2026-10-19 | freno_caida | Mesa actual (freno b y eventos) con freno por caída de la cuenta | 1x, pausa sin reinicio | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +56.4%/21.66% ; -18.5%/21.66% (neto/caída 2.6 ; -0.85; DSR 0.0; 117 y 47 ops) | — (informativa) |
| 359 | 2026-10-19 | freno_caida | Mesa actual (freno b y eventos) con freno por caída de la cuenta | 3x, pausa sin reinicio | 12 monedas, 5 min | sensibilidad | 2024-25 ; 2025-26: +6.4%/20.3% ; -10.5%/20.91% (neto/caída 0.31 ; -0.5; DSR 0.0; 18 y 5 ops) | — (informativa) |
| 360 | 2026-10-20 | macd | Cruce del MACD 12/26/9, solo compras | A tal cual (100%, 1x, sin stop) | BTCUSDT, 1d | decisoria | pendiente | pendiente |
| 361 | 2026-10-20 | macd | Cruce del MACD 12/26/9, solo compras | A tal cual (100%, 1x, sin stop) | ETHUSDT, 1d | decisoria | pendiente | pendiente |
| 362 | 2026-10-20 | macd | Cruce del MACD 12/26/9, solo compras | A tal cual (100%, 1x, sin stop) | BTCUSDT + ETHUSDT, 1d | decisoria | pendiente | pendiente |
| 363 | 2026-10-20 | macd | Cruce del MACD 12/26/9, solo compras | B con frenos (stop de la mesa, 2%, régimen b, eventos) | BTCUSDT, 1d | decisoria | pendiente | pendiente |
| 364 | 2026-10-20 | macd | Cruce del MACD 12/26/9, solo compras | B con frenos (stop de la mesa, 2%, régimen b, eventos) | ETHUSDT, 1d | decisoria | pendiente | pendiente |
| 365 | 2026-10-20 | macd | Cruce del MACD 12/26/9, solo compras | B con frenos (stop de la mesa, 2%, régimen b, eventos) | BTCUSDT + ETHUSDT, 1d | decisoria | pendiente | pendiente |
| 366 | 2026-10-20 | macd | Cruce del MACD 12/26/9, solo compras | A juntas, costos ×2 | BTCUSDT + ETHUSDT, 1d | sensibilidad | pendiente | — (informativa) |
| 367 | 2026-10-20 | macd | Cruce del MACD 12/26/9, solo compras | B juntas, costos ×2 | BTCUSDT + ETHUSDT, 1d | sensibilidad | pendiente | — (informativa) |
| 368 | 2026-10-20 | salida_regimen | Mesa actual (freno b y eventos) con salida por régimen | 1x: cierra los largos al día siguiente del cierre de BTC bajo su media de 50 días | 12 monedas, 5 min | decisoria | pendiente | pendiente |
| 369 | 2026-10-20 | salida_regimen | Mesa actual (freno b y eventos) con salida por régimen | 3x: cierra los largos al día siguiente del cierre de BTC bajo su media de 50 días | 12 monedas, 5 min | decisoria | pendiente | pendiente |

Formato del resultado: neto % / caída máx. %; "2024-25 ; 2025-26" cuando hay dos años.

## Excluidas o fuera del conteo

| Qué | Por qué | Si se incluyera |
|---|---|---|
| `tendencia/preregistro_2025-10-12` (ema 1d 20/50 atr3, tsmom 60d) | Son las mismas reglas que dos combinaciones de la rejilla de tendencia; por la regla de "dos años = una prueba" se juntan en esas filas (se anota el resultado 2024-25) | +2 si se cuentan aparte |
| Corrida inicial de tendencia, `mesa_2026-10-12` y `rotacion_2026-10-12` (borradas) | Las mismas reglas, re-corridas y reemplazadas por los informes actuales | 0 |
| `tendencia/minimos_mesa*` | Re-medición de la mesa (rechazos por mínimo); no es regla nueva | 0 |
| Filas de referencia: mesa_r3, mesa de práctica (base régimen b + eventos), base "solo eventos", "apagada", BTC comprar y mantener, la combinación de la rejilla de salidas igual a mesa_r3 (3R, 1R→0,5R, sin tiempo) | Regla de conteo | 0 |
| Resultados WF agregados (familias de tendencia/rotación, salidas WF de la mesa, filtro elegido WF, Kelly ya contado) | Se cuentan las combinaciones de la rejilla, no el agregado | +6 tendencia, +4 rotación, +2 mesa, +1 segunda si se contaran |
| Spearman/correlaciones de `sentimiento` (partes A y B) | Análisis estadístico, no un conjunto de reglas operado | 0 |
| `docs/experimento_horarios/` | Prueba hacia adelante (PAPER), preregistrada antes (2026-10-10 → 10-23), aún abierta | 0 |
| WF de las 18 combinaciones sobre el top 30 de cada día (mencionado en `rotacion/PREREGISTRO.md`) | No aparece en el informe ni en el JSON: no se corrió | 0 |
| `BOTS_PUBLICOS.md` "bajar el riesgo de las dos patas" (cartera) | Razonamiento, sin corrida informada | 0 |
| `docs/research/real/` filas "real tal cual" (31,69 USDT) y "real con 1.000 USDT" | Re-mediciones de la mesa con frenos (la estrategia del bot real), 2026-10-16: real tal cual +19.9%/57.54% ; -11.4%/34.09% (DSR 0.001), no pasa; con 1.000 USDT +56.0%/53.95% ; +6.0%/32.49% | 0 |
