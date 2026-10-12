# Seguir la tendencia en futuros (largos y cortos), fuera de muestra (2025-10-12 a 2026-10-12)

Investigación con datos públicos de Binance (sin cuenta, sin claves, sin órdenes). Monedas: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT, DOGEUSDT, ADAUSDT, LINKUSDT, AVAXUSDT, LTCUSDT, TRXUSDT, DOTUSDT. Velas de 1 hora (precio Spot como aproximación del perpetuo).

**Cómo se midió.** Cada combinación de parámetros corre todo el periodo. Cada 30 días, cada familia elige la combinación con mejor neto/caída en los 90 días anteriores y la usa los 30 siguientes; solo cuentan esos 30 días (13 ventanas). Capital 1.000 USDT, 1x, posición máx. 50%, 3 posiciones, riesgo 5% al stop (familias con stop) o tamaño por volatilidad (tsmom). Comisión 0,05% y deslizamiento 0,02% por lado, financiación real cada 8 h. Un stop que se salta con hueco se llena en la apertura. La mesa (mesa_r3, velas de 5 min, empieza cada ventana con 1.000 USDT como una sesión) y comprar y mantener BTC se miden en las mismas ventanas. Caída máxima medida con el cierre de cada día.

## Resultado fuera de muestra

| Estrategia | Operaciones | Neto % | Máx. caída | Neto/caída | Acierto | Ganancia media | Pérdida media | Comisiones | Financiación | Correlación con la mesa | Trimestres positivos | Veredicto |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mesa_r3 | — | — | — | — | — | — | — | — | — | — | — | no se midió en esta corrida |
| BTC comprar y mantener | — | -24.29% | 49.1% | -0.49 | — | — | — | — | — | — | 2 de 5 | referencia |
| donchian | 79 | -9.94% | 27.49% | -0.36 | 43.0% | +28.87 | -14.78 | 33.96 | +17.91 | — | 1 de 5 | muestra corta (79 operaciones < 100) |
| donchian_filtro | 89 | -35.48% | 41.08% | -0.86 | 40.4% | +18.21 | -13.38 | 30.53 | +12.14 | — | 2 de 5 | muestra corta (89 operaciones < 100) |
| ema | 112 | -12.02% | 26.69% | -0.45 | 35.7% | +29.37 | -10.05 | 46.16 | +8.93 | — | 2 de 5 | pierde fuera de muestra |
| ema_filtro | 72 | -11.87% | 22.5% | -0.53 | 31.9% | +25.91 | -8.55 | 31.11 | +10.62 | — | 2 de 5 | muestra corta (72 operaciones < 100) |
| tsmom | 122 | -3.53% | 29.74% | -0.12 | 49.2% | +20.05 | -15.10 | 51.96 | +1.91 | — | 3 de 5 | pierde fuera de muestra |
| tsmom_filtro | 81 | -5.98% | 30.6% | -0.2 | 56.8% | +22.66 | -19.19 | 33.94 | +10.59 | — | 2 de 5 | muestra corta (81 operaciones < 100) |

## Por trimestre (neto %, fuera de muestra)

| Estrategia | 2025-T4 | 2026-T1 | 2026-T2 | 2026-T3 | 2026-T4 |
|---|---|---|---|---|---|
| BTC | -20.78% | -22.09% | -14.15% | +42.64% | +0.18% |
| donchian | -6.36% (46 ops) | -2.23% (13 ops) | -2.72% (9 ops) | +5.86% (8 ops) | -4.48% (3 ops) |
| donchian_filtro | -17.75% (38 ops) | +6.54% (6 ops) | +7.79% (4 ops) | -18.91% (35 ops) | -15.76% (6 ops) |
| ema | -10.55% (58 ops) | +4.61% (12 ops) | +12.95% (7 ops) | -7.87% (30 ops) | -9.64% (5 ops) |
| ema_filtro | -13.73% (28 ops) | +13.33% (12 ops) | -7.44% (13 ops) | +5.05% (16 ops) | -7.30% (3 ops) |
| tsmom | +5.58% (45 ops) | +8.45% (14 ops) | +15.99% (28 ops) | -22.69% (28 ops) | -6.05% (7 ops) |
| tsmom_filtro | -3.27% (31 ops) | +10.69% (18 ops) | +17.80% (17 ops) | -21.19% (10 ops) | -5.41% (5 ops) |

## Combinaciones fijas en todo el periodo de prueba (en retrospectiva: NO cuenta, solo muestra si la idea es robusta o depende de un parámetro)

- **donchian**: 7 de 20 combinaciones ganan; mediana -29.30%; mejor {'tf': '1d', 'n': 55, 'salida': 'atr3'} +19.42% (caída 18.57%, 26 ops); peor {'tf': '4h', 'n': 20, 'salida': 'atr2'} -62.68%.
- **ema**: 5 de 12 combinaciones ganan; mediana -12.25%; mejor {'tf': '1d', 'rapida': 20, 'lenta': 50, 'atr': 3} +77.19% (caída 18.53%, 28 ops); peor {'tf': '4h', 'rapida': 20, 'lenta': 50, 'atr': 2} -56.75%.
- **tsmom**: 8 de 12 combinaciones ganan; mediana +5.34%; mejor {'dias': 60, 'vol': 20, 'mantener': 3} +60.83% (caída 16.54%, 189 ops); peor {'dias': 90, 'vol': 20, 'mantener': 3} -6.84%.

## Veredicto

**Ninguna estrategia de tendencia gana a la mesa** con las reglas del protocolo. La mejor fue **tsmom**: neto -3.53%, caída 29.74%, neto/caída -0.12 (mesa: —), 122 operaciones, 3 de 5 trimestres positivos. Veredicto: pierde fuera de muestra.

Advertencias: el precio Spot aproxima al perpetuo; un año es una sola historia de mercado; la mesa se mide con sus propias reglas de sesión (límite de pérdida y meta) reiniciadas cada 30 días; elegir parámetros con el pasado (walk-forward) es honesto pero no garantiza el futuro.
