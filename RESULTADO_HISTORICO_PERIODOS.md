# Diagnóstico por mes, semana y día — 25-09-2026

Los informes guardados ahora se desglosan por fecha de **señal UTC**, no por fecha de salida ni por ganancias de una cuenta. Un caso que comienza en julio puede terminar en agosto y permanece en el grupo de julio.

Cobertura: 25-06-2026 inclusive a 23-09-2026 exclusivo. Cada activo tiene 4 meses calendario intersectados, 14 semanas ISO (lunes UTC) y 90 días. Se incluyen períodos sin episodios. Junio y septiembre son parciales; no extrapolar esos recuentos a meses completos.

| Mes de señal | BTC casos | BTC objetivo / stop / sin salida | ETH casos | ETH objetivo / stop / sin salida |
| --- | ---: | --- | ---: | --- |
| Junio, desde el 25 | 0 | 0 / 0 / 0 | 0 | 0 / 0 / 0 |
| Julio | 79 | 17 / 62 / 0 | 90 | 33 / 57 / 0 |
| Agosto | 56 | 14 / 42 / 0 | 83 | 27 / 56 / 0 |
| Septiembre, hasta el 22 | 29 | 10 / 19 / 0 | 55 | 11 / 38 / 6 |
| Total | 164 | 41 / 123 / 0 | 228 | 71 / 151 / 6 |

No hubo casos ambiguos en esta selección; el informe mantiene esa categoría y las pruebas sintéticas la verifican. Cero episodios en los días cubiertos de junio no significa falta de datos. La cobertura se registra por separado del número de casos.

Los conteos cambian entre períodos, pero no acreditan rentabilidad, adaptación de la estrategia ni rendimiento futuro. No se agregan P&L de casos solapados, no hay cartera compartida y no se atribuye beneficio a casos sin salida. Se mantienen los supuestos de RESULTADO_HISTORICO_CASOS.md: primera señal por episodio, entrada simultánea hipotética sin latencia/deslizamiento, costos aportados y reglas existentes.

## Archivos y validación

- `historical_periods.py`: lector y generador sin red, base de datos, recálculo de indicadores ni simulación nueva. Requiere SHA256 externos de ambos archivos y comprueba enlaces, huellas internas, conteos, fechas, malla y alineación señal/caso/resultado. No verifica OHLC ni autenticidad de los datos originales.
- `test_historical_periods.py`: 10 pruebas aprobadas (2,669s), incluyendo cambio de año ISO, medianoche UTC, final exclusivo, períodos parciales y vacíos, alteraciones, no finitos y no sobrescritura.
- Suite completa del proyecto: 409 pruebas aprobadas (34,063s), incluyendo las dos nuevas de HTTP451. Los errores impresos son escenarios simulados esperados.
- Nuevos informes: `datasets/20260625_20260923/BTCUSDT/periodos_senales.json` y `datasets/20260625_20260923/ETHUSDT/periodos_senales.json`.
- Los totales de las tres frecuencias se concilian con164/228casos. Recuento mensual contrastado por una lectura independiente de los informes originales. No se reescribieron casos ni replay y no se redescargaron datos.

SHA256 salidas: BTC `cb03456404f52e0a7ae24776b32df5ccea4169cf1c7e580e65de6f3cfd01d25b`; ETH `3811ca36e00822ba8d37b5d5657af882491061abe0929bcdf1869cd9bc8c1d7a`.

## Siguiente paso

Evaluar entrada retrasada una vela15m como estrés explícito, no como latencia real medida. Conservar señal/ATR/capital/comisión originales; contabilizar casos sin cobertura, sin truncarlos. Comparar transiciones y desgloses por períodos sin seleccionar umbrales para mejorar retrospectivamente esta muestra. No cambiar marcos operativos15m/1h/4h por el desglose mensual/semanal/diario.
