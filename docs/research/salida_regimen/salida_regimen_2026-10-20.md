# Salida por régimen sobre la mesa actual

Preregistro: `docs/research/salida_regimen/PREREGISTRO.md`, escrito antes de correr. La mesa con freno de régimen b para entrar y de eventos ±2 h, costos de Binance Futuros (0,05% por lado, 0,02% de deslizamiento, financiación real) y mínimos por orden; bloques de 30 días encadenados, 1.000 USDT. La salida por régimen cierra los largos abiertos en la primera vela de 5 minutos del día siguiente al cierre de BTC bajo su media de 50 días; la referencia los deja hasta su stop o su meta. Sharpe deflactado con N = 288 decisorias.

## Veredicto

- **1x con salida por régimen: no pasa.** Neto/caída 1.04 ; 0.18 contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 0.005 (listón 0.95). Sin salida por régimen: neto/caída 1.58 ; -0.29.
- **3x con salida por régimen: no pasa.** Neto/caída -0.25 ; -0.28 contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 0.003 (listón 0.95). Sin salida por régimen: neto/caída 0.34 ; -0.58.

## 2024-10-12 → 2025-10-12

| Fila | Tipo | Neto % | Máx. caída | Neto/caída | Cambio contra sin salida (neto, caída) | Ops | Cerradas por régimen | Resultado de esas (% del bloque) | Stops | Acierto | Peor op. | Sharpe anual | Sharpe deflactado | Trimestres (neto %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x con salida por régimen | decisoria | +56.0% | 53.95% | 1.04 | -25.5 pts, +2.4 pts | 363 | 23 | -12.3% | 279 | 49.9% | -7.4% | 1.18 | 0.041 | +66.0 / -22.3 / -25.7 / +62.6 |
| 3x con salida por régimen | decisoria | -21.8% | 88.92% | -0.25 | -51.5 pts, +2.8 pts | 289 | 20 | -18.8% | 215 | 48.4% | -14.6% | 0.42 | 0.007 | +80.9 / -45.3 / -60.6 / +100.7 |
| 1x sin salida por régimen (referencia) | referencia | +81.5% | 51.59% | 1.58 | — | 361 | 0 | +0.0% | 297 | 51.8% | -7.4% | 1.46 | 0.072 | +89.0 / -28.9 / -23.4 / +76.3 |
| 3x sin salida por régimen (referencia) | referencia | +29.7% | 86.17% | 0.34 | — | 287 | 0 | +0.0% | 231 | 50.9% | -14.6% | 0.84 | 0.019 | +123.4 / -45.3 / -57.7 / +150.8 |

## 2025-10-13 → 2026-10-13

| Fila | Tipo | Neto % | Máx. caída | Neto/caída | Cambio contra sin salida (neto, caída) | Ops | Cerradas por régimen | Resultado de esas (% del bloque) | Stops | Acierto | Peor op. | Sharpe anual | Sharpe deflactado | Trimestres (neto %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x con salida por régimen | decisoria | +6.0% | 32.49% | 0.18 | +18.1 pts, -9.9 pts | 218 | 22 | -9.2% | 154 | 46.3% | -3.3% | 0.34 | 0.005 | -8.5 / -10.9 / -3.1 / +34.2 |
| 3x con salida por régimen | decisoria | -20.6% | 73.89% | -0.28 | +27.0 pts, -8.8 pts | 194 | 21 | -22.8% | 131 | 46.9% | -9.8% | 0.13 | 0.003 | -24.5 / -31.5 / -18.9 / +89.4 |
| 1x sin salida por régimen (referencia) | referencia | -12.2% | 42.35% | -0.29 | — | 207 | 0 | +0.0% | 168 | 46.4% | -3.3% | -0.3 | 0.001 | -16.5 / -11.3 / -7.0 / +27.5 |
| 3x sin salida por régimen (referencia) | referencia | -47.6% | 82.69% | -0.58 | — | 183 | 0 | +0.0% | 141 | 47.0% | -10.2% | -0.44 | 0.001 | -43.4 / -32.6 / -22.6 / +77.5 |

La peor operación y el resultado de las cerradas por régimen son sobre el capital del bloque. El capital diario está en el JSON. Un resultado pasado no promete uno futuro. El dinero real no cambia por este estudio.
