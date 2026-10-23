# Tope al riesgo abierto total en la mesa de futuros

Preregistro: `docs/research/tope_riesgo/PREREGISTRO.md`, escrito antes de correr. La mesa de práctica 1x con freno de régimen b y de eventos ±2 h, costos de Binance Futuros (0,05% por lado, 0,02% de deslizamiento, financiación real) y mínimos por orden; bloques de 30 días encadenados, 1.000 USDT. El tope: no se abre una posición nueva si las abiertas del mismo lado perderían más del 2% del saldo si saltan todos sus stops. Sharpe deflactado con N = 301 decisorias.

## Veredicto

- **1x con tope de 2% al riesgo abierto del mismo lado: no pasa.** Neto/caída 0.58 ; 0.74 contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 0.013 (listón 0.95). Sin tope: neto/caída 1.04 ; 0.18.

## 2024-10-12 → 2025-10-12

| Fila | Tipo | Neto % | Máx. caída | Neto/caída | Cambio contra sin tope (neto, caída) | Ops | Señales frenadas por el tope | Salidas | Acierto | Peor op. | Sharpe anual | Sharpe deflactado | Trimestres (neto %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x con tope de 2% al riesgo abierto del mismo lado | decisoria | +20.3% | 34.88% | 0.58 | -35.7 pts, -19.1 pts | 237 | 15807 | fin del bloque 12, meta 5, régimen 12, señal contraria 22, stop 186 | 46.0% | -7.0% | 0.68 | 0.012 | +20.4 / -5.7 / -19.5 / +31.7 |
| 1x sin tope (referencia) | referencia | +56.0% | 53.95% | 1.04 | — | 363 | 0 | fin de sesión 3, fin del bloque 18, meta 5, régimen 23, señal contraria 35, stop 279 | 49.9% | -7.4% | 1.18 | 0.039 | +66.0 / -22.3 / -25.7 / +62.6 |

## 2025-10-13 → 2026-10-13

| Fila | Tipo | Neto % | Máx. caída | Neto/caída | Cambio contra sin tope (neto, caída) | Ops | Señales frenadas por el tope | Salidas | Acierto | Peor op. | Sharpe anual | Sharpe deflactado | Trimestres (neto %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x con tope de 2% al riesgo abierto del mismo lado | decisoria | +18.5% | 24.85% | 0.74 | +12.5 pts, -7.6 pts | 159 | 7943 | fin del bloque 14, meta 1, régimen 14, señal contraria 18, stop 112 | 49.7% | -3.4% | 0.75 | 0.013 | -5.0 / -7.2 / -0.2 / +34.7 |
| 1x sin tope (referencia) | referencia | +6.0% | 32.49% | 0.18 | — | 218 | 0 | fin del bloque 16, meta 3, régimen 22, señal contraria 23, stop 154 | 46.3% | -3.3% | 0.34 | 0.004 | -8.5 / -10.9 / -3.1 / +34.2 |

Una señal frenada cuenta una vez por racha de velas seguidas en la misma moneda. La peor operación es sobre el capital del bloque. El capital diario está en el JSON. Un resultado pasado no promete uno futuro. El dinero real no cambia por este estudio.
