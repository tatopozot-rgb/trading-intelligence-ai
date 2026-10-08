# Reproducción técnica de90 días — 23-09-2026

Completada sobre BTCUSDT y ETHUSDT del25junio al22septiembre2026 UTC. Se reutilizaron los datos descargados, sin red ni sesión operativa. Cada evaluación sólo ve velas cerradas conocidas en ese instante.

| Resultado | Bitcoin | Ethereum |
| --- | ---: | ---: |
| Momentos evaluados, cada15min | 8640 | 8640 |
| Momentos con condición alcista/momentum sano | 808 | 1156 |
| Episodios consecutivos de esa condición | 164 | 228 |
| Puntos contrastados con análisis de referencia H1 | 25 | 25 |

Un episodio agrupa momentos consecutivos que cumplen la condición. **No representa una compra ni una oportunidad rentable demostrada.** El programa real también comprueba selección del radar, capital disponible, posiciones, riesgo, precio y otros controles. Este estudio no simula esos controles ni fills/comisiones/P&L. No permite afirmar cuánto habríamos ganado.

La malla15min es diagnóstica: el scanner real espera15min después de terminar su análisis, así que sus instantes no serían idénticos. Los dos pares no representan todo el radar dinámico. No se ha declarado esta historia una muestra independiente ni se ha afinado la estrategia con sus resultados.

Verificaciones: seis pruebas nuevas H4; suite329 OK. Igualdad de indicadores y ventanas con H1 en25puntos distribuidos por par. Integridad de todas las filas comprobada por hash. Sólo los tests sintéticos verifican ejecución repetida completa; no se afirma haber repetido dos veces el replay real completo.

Informes completos: datasets/20260625_20260923/BTCUSDT/replay_senales.json y ETHUSDT/replay_senales.json, con ventanas/indicadores por punto y huellas de código/datos. Hash de filas BTC:c10fe09d20a527af15e5184256cb8293ecdb42a6bf27aff67ef43cd334a336e9. ETH:c02e14840b023b1e7d8bd28c22d52b7668f628fe1034a5e2812d84c83e198a6b.

Siguiente: simulación económica separada reutilizando reglas/riesgo/comisiones PAPER existentes, con supuestos de ejecución explícitos y tratamiento de ambigüedad intravela. Sin escribir a trading.db ni iniciar programa operativo. Si un supuesto requiere decidir riesgo/capital/ejecución nuevos, consultar al usuario, no inventarlo.
