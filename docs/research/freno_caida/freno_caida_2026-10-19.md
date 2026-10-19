# Freno por caída de la cuenta sobre la mesa actual

Preregistro: `docs/research/freno_caida/PREREGISTRO.md`, escrito antes de correr. La mesa con freno de régimen b y de eventos ±2 h, costos de Binance Futuros (0,05% por lado, 0,02% de deslizamiento, financiación real) y mínimos por orden; bloques de 30 días encadenados, 1.000 USDT. Freno: riesgo a la mitad desde 10% de caída, sin entradas nuevas desde 20%; la pausa dura hasta el bloque siguiente. Sharpe deflactado con N = 280 decisorias.

## Veredicto

- **1x con freno por caída: no pasa.** Neto/caída 1.92 ; 0.18 contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 0.005 (listón 0.95). Sin freno: neto/caída 1.04 ; 0.18.
- **3x con freno por caída: no pasa.** Neto/caída -0.22 ; -0.69 contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 0.001 (listón 0.95). Sin freno: neto/caída -0.25 ; -0.28.

## 2024-10-12 → 2025-10-12

| Fila | Tipo | Neto % | Máx. caída | Neto/caída | Cambio contra sin freno (neto, caída) | Ops | Entradas a medio riesgo | Pausas | Acierto | Peor op. | Sharpe anual | Sharpe deflactado | Trimestres (neto %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x con freno por caída | decisoria | +86.2% | 44.95% | 1.92 | +30.2 pts, -9.0 pts | 350 | 104 | 2 | 50.6% | -7.4% | 1.6 | 0.092 | +65.9 / -5.7 / -26.8 / +62.6 |
| 3x con freno por caída | decisoria | -13.7% | 61.52% | -0.22 | +8.1 pts, -27.4 pts | 113 | 29 | 9 | 53.1% | -13.3% | 0.17 | 0.004 | -20.1 / -16.9 / -19.3 / +61.1 |
| 1x, pausa sin reinicio | sensibilidad | +56.4% | 21.66% | 2.6 | +0.4 pts, -32.3 pts | 117 | 40 | 1 | 54.7% | -7.4% | 1.49 | 0.067 | +65.9 / -5.7 / +0.0 / +0.0 |
| 3x, pausa sin reinicio | sensibilidad | +6.4% | 20.3% | 0.31 | +28.2 pts, -68.6 pts | 18 | 6 | 1 | 55.6% | -8.3% | 0.41 | 0.006 | +6.4 / +0.0 / +0.0 / +0.0 |
| 1x sin freno (referencia) | referencia | +56.0% | 53.95% | 1.04 | — | 363 | 0 | 0 | 49.9% | -7.4% | 1.18 | 0.041 | +66.0 / -22.3 / -25.7 / +62.6 |
| 3x sin freno (referencia) | referencia | -21.8% | 88.92% | -0.25 | — | 289 | 0 | 0 | 48.4% | -14.6% | 0.42 | 0.007 | +80.9 / -45.3 / -60.6 / +100.7 |

## 2025-10-13 → 2026-10-13

| Fila | Tipo | Neto % | Máx. caída | Neto/caída | Cambio contra sin freno (neto, caída) | Ops | Entradas a medio riesgo | Pausas | Acierto | Peor op. | Sharpe anual | Sharpe deflactado | Trimestres (neto %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1x con freno por caída | decisoria | +5.9% | 32.51% | 0.18 | -0.0 pts, +0.0 pts | 203 | 57 | 1 | 47.3% | -3.3% | 0.34 | 0.005 | -8.5 / -10.9 / -3.1 / +34.2 |
| 3x con freno por caída | decisoria | -45.5% | 65.59% | -0.69 | -24.9 pts, -8.3 pts | 94 | 24 | 8 | 44.7% | -8.8% | -0.59 | 0.001 | -21.3 / -21.4 / -22.1 / +13.1 |
| 1x, pausa sin reinicio | sensibilidad | -18.5% | 21.66% | -0.85 | -24.5 pts, -10.8 pts | 47 | 23 | 1 | 36.2% | -2.9% | -1.45 | 0.0 | -8.5 / -10.9 / +0.0 / +0.0 |
| 3x, pausa sin reinicio | sensibilidad | -10.5% | 20.91% | -0.5 | +10.1 pts, -53.0 pts | 5 | 1 | 1 | 40.0% | -8.8% | -0.51 | 0.0 | -10.5 / +0.0 / +0.0 / +0.0 |
| 1x sin freno (referencia) | referencia | +6.0% | 32.49% | 0.18 | — | 218 | 0 | 0 | 46.3% | -3.3% | 0.34 | 0.005 | -8.5 / -10.9 / -3.1 / +34.2 |
| 3x sin freno (referencia) | referencia | -20.6% | 73.89% | -0.28 | — | 194 | 0 | 0 | 46.9% | -9.8% | 0.13 | 0.003 | -24.5 / -31.5 / -18.9 / +89.4 |

La peor operación es sobre el capital del bloque. El capital diario está en el JSON. Un resultado pasado no promete uno futuro. El dinero real no cambia por este estudio.
