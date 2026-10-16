# Sharpe deflactado de la ruptura de Londres en oro, 2025-10-13 → 2026-10-13

Método preregistrado en `docs/research/rsi2/PREREGISTRO.md` (parte 2) antes de correr; número de pruebas de `docs/research/REGISTRO_PRUEBAS.md`. Bailey y López de Prado (2014).

## Veredicto

- **No pasa el segundo listón:** con N = 292 pruebas, el Sharpe deflactado es 0.21 (listón 0.95).
- Sharpe anual de Londres en oro: 2.04, sobre 261 días hábiles (neto +26.6%, asimetría -0.21, curtosis 1.8).

## Casos

| N | Qué cuenta | V | Mejor Sharpe anual esperado por suerte | Sharpe deflactado | Pasa |
|---|---|---|---|---|---|
| 1 | sin deflactar | V = 1/T | 0.00 | 0.979 | sí |
| 247 | solo decisorias | V = 1/T | 2.78 | 0.228 | no |
| 247 | solo decisorias | V medida en research_oro | 4.55 | 0.006 | no |
| 292 | todas las pruebas | V = 1/T | 2.84 | 0.213 | no |
| 292 | todas las pruebas | V medida en research_oro | 4.64 | 0.005 | no |

## Las 12 filas de research_oro en 2025-26 (para V medida)

| Fila | Días | Sharpe anual | Neto % | Asimetría | Curtosis |
|---|---|---|---|---|---|
| oro · londres | 261 | 2.04 | +26.6% | -0.21 | 1.8 |
| oro · tortugas | 261 | 0.21 | +1.2% | -1.84 | 23.9 |
| oro · noticia | 261 | 0.07 | +0.2% | 7.39 | 120.6 |
| oro · londres, costes ×2 | 261 | 1.81 | +23.1% | -0.22 | 1.8 |
| oro · tortugas, costes ×2 | 261 | 0.13 | +0.7% | -1.85 | 23.5 |
| oro · noticia, costes ×2 | 261 | -0.10 | -0.3% | 6.55 | 112.1 |
| btc · londres | 365 | -1.01 | -17.8% | -0.19 | 1.6 |
| btc · tortugas | 365 | 1.10 | +9.2% | 1.69 | 12.7 |
| btc · noticia | 365 | -1.50 | -6.4% | -4.92 | 55.1 |
| btc · londres, costes ×2 | 365 | -3.45 | -48.1% | -0.28 | 1.8 |
| btc · tortugas, costes ×2 | 365 | 1.04 | +8.7% | 1.63 | 12.4 |
| btc · noticia, costes ×2 | 365 | -1.89 | -10.1% | -7.39 | 60.7 |

Cómo leerlo: el Sharpe deflactado es la probabilidad de que el Sharpe real sea mayor que el mejor que saldría por pura suerte después de tantas pruebas. Con 0,95 o más se cree; por debajo, el resultado puede ser suerte. Las 12 filas de oro y BTC son pocas y muy distintas entre sí, así que la V medida es solo orientativa.
