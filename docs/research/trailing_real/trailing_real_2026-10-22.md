# El bot real con trailing desde 2R y sin cierre por señal opuesta

Preregistro: `docs/research/trailing_real/PREREGISTRO.md`, escrito antes de correr. El bot real (31,69 USDT, 1x, riesgo 1-15% por calidad, régimen b con salida, eventos ±2 h), costos de Binance Futuros (0,05% por lado, 0,02% de deslizamiento, financiación real) y mínimos por orden; bloques de 30 días encadenados. Cambia solo la salida: el trailing arranca en +2R (a R/2, meta 3R) y la señal contraria ya no cierra. Sharpe deflactado con N = 297 decisorias.

## Veredicto

- **Real con trailing desde 2R y sin cierre por señal: no pasa.** Neto/caída 1.77 ; -0.01 contra la mesa 1,67 ; −0,21; Sharpe deflactado 2025-26 0.003 (listón 0.95). Tal cual: neto/caída 0.35 ; -0.33.

## 2024-10-12 → 2025-10-12

| Fila | Tipo | Neto % | Máx. caída | Neto/caída | Cambio contra tal cual (neto, caída) | Ops | Salidas | Acierto | Peor op. | Sharpe anual | Sharpe deflactado | Trimestres (neto %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Real con trailing desde 2R y sin cierre por señal | decisoria | +84.1% | 47.53% | 1.77 | +64.2 pts, -10.0 pts | 145 | fin de sesión 3, fin del bloque 13, meta 10, régimen 15, stop 104 | 45.5% | -7.0% | 1.45 | 0.066 | +83.2 / -16.2 / -15.1 / +41.3 |
| Real tal cual (referencia) | referencia | +19.9% | 57.54% | 0.35 | — | 265 | fin del bloque 13, meta 2, régimen 14, señal contraria 26, stop 210 | 49.1% | -6.3% | 0.62 | 0.011 | +33.3 / -22.3 / -26.1 / +56.7 |

## 2025-10-13 → 2026-10-13

| Fila | Tipo | Neto % | Máx. caída | Neto/caída | Cambio contra tal cual (neto, caída) | Ops | Salidas | Acierto | Peor op. | Sharpe anual | Sharpe deflactado | Trimestres (neto %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Real con trailing desde 2R y sin cierre por señal | decisoria | -0.2% | 31.22% | -0.01 | +11.1 pts, -2.9 pts | 89 | fin del bloque 12, meta 5, régimen 17, stop 55 | 37.1% | -8.2% | 0.14 | 0.003 | -5.5 / -14.4 / +2.7 / +20.1 |
| Real tal cual (referencia) | referencia | -11.4% | 34.09% | -0.33 | — | 145 | fin del bloque 11, meta 3, régimen 16, señal contraria 11, stop 104 | 48.3% | -8.8% | -0.23 | 0.001 | -8.1 / -15.8 / +3.3 / +10.8 |

"stop" incluye el trailing (el stop movido). La peor operación es sobre el capital del bloque. El capital diario está en el JSON. Un resultado pasado no promete uno futuro. El dinero real no cambia por este estudio: si pasa, decide el líder.
