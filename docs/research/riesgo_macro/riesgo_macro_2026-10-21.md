# Riesgo a la mitad cuando suben el bono a 10 años y el dólar

Preregistro: `docs/research/riesgo_macro/PREREGISTRO.md`, escrito antes de correr. La mesa con régimen b (con salida) y eventos ±2 h, costos de Binance Futuros y mínimos por orden; bloques de 30 días encadenados, 1.000 USDT. Mientras el bono y el dólar están los dos sobre su media de 50 datos, cada entrada nueva arriesga la mitad. Fuentes: bono Yahoo ^TNX (desde D+1), dólar Yahoo DX-Y.NYB (desde D+1). Sharpe deflactado con N = 296 decisorias.

## Veredicto

- **1x con riesgo a la mitad por bono y dólar: no pasa.** Neto/caída 1.01 ; 0.18 contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 0.005 (listón 0.95). Sin la regla: neto/caída 1.04 ; 0.18.
- **3x con riesgo a la mitad por bono y dólar: no pasa.** Neto/caída -0.21 ; -0.59 contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 0.001 (listón 0.95). Sin la regla: neto/caída -0.25 ; -0.28.

## 2024-10-12 → 2025-10-12 (regla activa 115 de 365 días)

| Fila | Tipo | Neto % | Máx. caída | Neto/caída | Cambio contra sin la regla (neto, caída) | Ops | Acierto | Peor op. | Sharpe anual | Sharpe deflactado | Trimestres (neto %) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x con riesgo a la mitad por bono y dólar | decisoria | +54.5% | 53.89% | 1.01 | -1.4 pts, -0.1 pts | 363 | 49.9% | -7.4% | 1.16 | 0.038 | +65.4 / -22.7 / -25.7 / +62.6 |
| 3x con riesgo a la mitad por bono y dólar | decisoria | -18.5% | 87.88% | -0.21 | +3.3 pts, -1.0 pts | 294 | 48.6% | -11.1% | 0.39 | 0.006 | +88.0 / -45.2 / -60.6 / +100.7 |
| 1x sin la regla (referencia) | referencia | +56.0% | 53.95% | 1.04 | — | 363 | 49.9% | -7.4% | 1.18 | 0.04 | +66.0 / -22.3 / -25.7 / +62.6 |
| 3x sin la regla (referencia) | referencia | -21.8% | 88.92% | -0.25 | — | 289 | 48.4% | -14.6% | 0.42 | 0.006 | +80.9 / -45.3 / -60.6 / +100.7 |

## 2025-10-13 → 2026-10-13 (regla activa 162 de 365 días)

| Fila | Tipo | Neto % | Máx. caída | Neto/caída | Cambio contra sin la regla (neto, caída) | Ops | Acierto | Peor op. | Sharpe anual | Sharpe deflactado | Trimestres (neto %) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x con riesgo a la mitad por bono y dólar | decisoria | +6.0% | 32.49% | 0.18 | +0.0 pts, +0.0 pts | 218 | 46.3% | -3.3% | 0.34 | 0.005 | -8.5 / -10.9 / -3.1 / +34.2 |
| 3x con riesgo a la mitad por bono y dólar | decisoria | -42.3% | 72.33% | -0.59 | -21.7 pts, -1.6 pts | 202 | 46.0% | -8.8% | -0.27 | 0.001 | -24.5 / -28.4 / -18.8 / +31.3 |
| 1x sin la regla (referencia) | referencia | +6.0% | 32.49% | 0.18 | — | 218 | 46.3% | -3.3% | 0.34 | 0.005 | -8.5 / -10.9 / -3.1 / +34.2 |
| 3x sin la regla (referencia) | referencia | -20.6% | 73.89% | -0.28 | — | 194 | 46.9% | -9.8% | 0.13 | 0.003 | -24.5 / -31.5 / -18.9 / +89.4 |

La peor operación es sobre el capital del bloque. El capital diario está en el JSON. Un resultado pasado no promete uno futuro. El dinero real no cambia por este estudio.
