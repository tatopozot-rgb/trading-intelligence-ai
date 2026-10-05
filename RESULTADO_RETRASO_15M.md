# H5h — sensibilidad de entrada a una vela de retraso

25-09-2026. Diagnóstico offline terminado sobre los mismos 392 casos H5f y los datos ya guardados, sin descargar ni recalcular el replay de 90 días. No representa una cartera ni modifica el programa operativo.

## Resultado pareado

| Activo | Comparables / originales | Objetivo primero, base → retraso | Stop primero, base → retraso | Sin salida, base → retraso | Casos que cambian categoría |
| --- | --- | --- | --- | --- | --- |
| BTCUSDT | 164 / 164 | 41 → 41 | 123 → 123 | 0 → 0 | 2 |
| ETHUSDT | 228 / 228 | 71 → 75 | 151 → 147 | 6 → 6 | 10 |

No hubo exclusiones ni ambigüedades en esta muestra. BTC: un objetivo pasa a stop y un stop a objetivo; mirar sólo totales habría ocultado ambos cambios. ETH: tres objetivos pasan a stop y siete stops a objetivo. La matriz conserva también los casos sin cambio. Estos conteos no son ganancias, ni justifican añadir retrasos al sistema. Igual categoría tampoco implica igual precio, duración o resultado económico.

## Comparación mensual por fecha de señal UTC

Cada celda contiene objetivo / stop / sin salida. Junio y septiembre tienen cobertura parcial; los desenlaces pueden ocurrir después del mes de la señal.

| Período cubierto | BTC base | BTC retraso | ETH base | ETH retraso |
| --- | --- | --- | --- | --- |
| 25–30 junio | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| Julio | 17 / 62 / 0 | 17 / 62 / 0 | 33 / 57 / 0 | 35 / 55 / 0 |
| Agosto | 14 / 42 / 0 | 14 / 42 / 0 | 27 / 56 / 0 | 30 / 53 / 0 |
| 1–22 septiembre | 10 / 19 / 0 | 10 / 19 / 0 | 11 / 38 / 6 | 10 / 39 / 6 |

Los JSON incluyen los 4 meses intersectados, 14 semanas ISO y 90 días de cada activo, incluso períodos sin casos; conteos y transiciones concilian con el total en las tres frecuencias.

## Contrato y límites

- Entrada hipotética desplazada exactamente 900000 ms, al precio de apertura de la nueva vela 15m. Es estrés elegido explícitamente, no latencia medida ni precio de ejecución demostrado.
- Misma señal original y evidencia, incluido ATR porcentual. Mismas fórmulas de niveles/tamaño, capital 100 por caso aislado y comisión 0,1% por lado ya usados en H5f. No se revalida la señal posterior ni se decide con información futura; el nuevo open sólo determina la entrada hipotética. Tamaño monetario y cantidad de activo no son la misma medida.
- Mismo final absoluto: también se acorta una vela el horizonte observado. No se afirma aislar exclusivamente el efecto del precio.
- Barreras tocadas antes de la nueva entrada no cierran ni excluyen una posición que aún no existía. La trayectoria comienza en la entrada retrasada.
- Entrada igual/posterior al fin o sin apertura se registra como EXCLUIDA con índice y razón; no como stop ni como caso abierto. Base total y base comparable se publican por separado. Otros defectos de continuidad/integridad invalidan el conjunto; no se ocultan truncándolo.
- Sin spread/deslizamiento calibrados, cartera compartida, límite global de posiciones, pérdidas diarias agregadas, reinversión ni selección histórica del radar. No sumar P&L de los casos solapados. No reproduce la caducidad/tolerancia del runner.
- Hashes comprueban integridad y compatibilidad local, no autenticidad del mercado. Indicadores H4 guardados se validan y reutilizan; no se recalcularon todos.

## Pruebas y correcciones

10 pruebas nuevas aprobadas en 6,544 s. Suite completa: 419 aprobadas en 46,236 s; los errores impresos son fallos simulados esperados. Incluyen paridad con evaluador individual, no red/SQLite, no mutación ni recálculo, fin exacto, falta de apertura, cambios de reglas/hash/precio, matriz diagonal y cruces, ceros/denominadores, no sobrescritura y dos pruebas de barreras anteriores a la entrada (una integrada).

Corregida una fixture que terminaba justo en su primera señal: se añadieron dos velas sintéticas futuras para que las pruebas de comparación no fueran vacías. El primer intento tuvo una aserción fallida; quedó corregido antes de evaluar los archivos históricos. Sin cambios a datos originales.

Contraste independiente, igualdad campo a campo con H5e individual en ocho casos retrasados: BTC índices 0/82/108/163; ETH 0/10/114/227. Incluye cambios de categoría y sin salida. Mes/semana/día concilian categorías, exclusiones y matrices. Hashes de casos/replay originales siguen coincidiendo con RESULTADO_HISTORICO_CASOS.md.

Claude revisó contrato antes de implementar (mensajes49/50) y cierre/siguiente paso (51/52) en el chat existente. No leyó archivos ni ejecutó pruebas locales. Se adoptó su advertencia sobre horizonte menor; se corrigieron sus sugerencias de matriz vacía y de excluir barreras previas, incompatibles con el contrato fijado.

## Archivos y reproducción

Código: historical_delay.py. Pruebas: test_historical_delay.py. Informes nuevos: datasets/20260625_20260923/{BTCUSDT,ETHUSDT}/retraso_15m.json. El CLI exige manifiesto, replay, casos, hashes externos, escenario y destino nuevo; rechaza sobrescritura. No regenerar informes completados.

SHA256 de salidas:

- BTC: 15d682c7036a42bb2962432a98d12f4c8878499d0c1e41bf34e55acf771d307b
- ETH: 755a6730ab7f9e3f748d31a041900c164c18c5cad0f1b252160d73e3df236fbb

Próximo bloque H6a: inventario cronológico conjunto BTC/ETH de intervalos/solapes de los casos originales H5f, sin adjudicar fondos, rechazar señales por conveniencia ni calcular cartera. Documentar incertidumbre intravela y casos sin salida al final; mantener todos los índices. El estrés H5h permanece como comparación separada, no se convierte en estrategia. Este mapa identifica entradas competidoras antes de implementar capital/riesgo compartidos; no basta por sí solo para decidir aceptaciones.
