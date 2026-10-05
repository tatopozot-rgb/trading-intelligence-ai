# H6a — Inventario conjunto de intervalos y solapes

28 de septiembre de 2026. H6a reúne los 392 casos H5f originales en un eje temporal BTC/ETH de 25-06-2026 00:00 UTC a 23-09-2026 00:00 UTC, fin exclusivo. No es una cartera, una asignación de fondos ni un resultado de rentabilidad.

## Resultado

| Medida | Cantidad |
| --- | ---: |
| Casos conservados | 392: BTC 164 / ETH 228 |
| Salidas con instante intravela incierto | 386 |
| Salidas hipotéticas en apertura | 0 |
| Casos sin salida, censurados al fin | 6 ETH |
| Casos con resultado stop/objetivo ambiguo | 0 |
| Pares con solape temporal cierto de duración positiva | 3.509 |
| Pares con solape posible, no confirmado por las cotas | 21 |
| Total de pares con algún solape posible | 3.530 |
| Pares del mismo símbolo / entre símbolos | 1.794 / 1.736 |
| Contactos entrada dentro del intervalo de salida de otro caso | 21 |
| Grupos de entradas simultáneas / casos de esos grupos | 34 / 68 |
| Cota inferior / superior del pico de casos concurrentes | 51 / 51 |
| Grupos cronológicos / tramos contiguos | 639 / 638 |

Se conservan los desenlaces H5f: BTC 41 objetivo y 123 stop; ETH 71 objetivo, 151 stop y 6 sin salida. Los 21 pares posibles reflejan incertidumbre temporal conservadora; no son 21 desenlaces stop/objetivo ambiguos. La ausencia de estos últimos en la muestra no elimina el problema: ambos escenarios están cubiertos por fixtures.

Los 3.530 pares son relaciones entre casos a lo largo de toda la cobertura, no operaciones adicionales. Las cotas 51/51 describen concurrencia de casos hipotéticos; no acreditan capacidad para financiar 51 posiciones ni asignan capital a ninguna.

## Contrato temporal

- Cada caso conserva `simbolo`, `indice_original` base cero e `id_caso`. `indice_global` sólo identifica su lugar en almacenamiento cronológico. Los empates se serializan de forma determinista, sin prioridad entre símbolos ni orden de ejecución.
- Para toques intravela, la salida se acota inclusivamente por apertura y cierre de la primera vela con evento. Se incluye la apertura conservadoramente, sin asignar la hora exacta del toque. Aperturas con salto tendrían un instante exacto dentro del modelo hipotético original; tampoco serían fills confirmados.
- La permanencia se trata como `[entrada,salida)`. Un par es cierto si conserva duración positiva incluso con las salidas más tempranas de las cotas; es posible no confirmado si sólo aparece con salidas más tardías. Un contacto en el mismo instante se registra por separado: no demuestra que fondos estén libres antes de la entrada.
- Los límites inferior/superior de salida presentes en `cronologia` son límites de incertidumbre, no dos salidas ejecutadas. Cada grupo simultáneo contiene listas sin orden operativo. `tramos` incluye incluso los períodos sin casos y expresa cotas mínima/máxima de permanencia observada.
- Los seis casos sin salida conservan `salida_hipotetica: null` y `censurado_derecha: true`. El fin de observación no se convierte en cierre. Se conoce su permanencia hasta ese fin exclusivo; no se infiere su trayectoria posterior.
- Una salida stop/objetivo ambigua conservaría ambas etiquetas de escenario, sin selección, probabilidades o promedio. Incertidumbre de resultado y de tiempo son dimensiones diferentes.

## Validación y alcance

25 pruebas aprobadas en 4,686 s: 15 nuevas de H6a y las 10 de `historical_periods`, cuyo validador de evidencia guardada se reutiliza. Cubren límites de primera/última vela, fin exclusivo, salidas exactas que contactan entradas, intervalos inciertos y vacíos, dos casos censurados, empates, conservación de índices, ausencia de campos económicos, hashes externos, JSON no finito/duplicado, desalineación, omisiones, fuente repetida, coberturas distintas, rechazo de estrés H5h, fills inventados y sobrescritura.

Revisión independiente de sólo lectura sin fallos confirmados: enumeró 400 pares sintéticos y todos sus instantes de salida posibles, contrastando existencia/clasificación de solape, duración mínima/máxima y cotas de pico. La sugerencia de conservar un test explícito de intervalos vacíos quedó incorporada.

Conciliación independiente de sólo lectura desde los JSON H5f originales: identidades de los 392 casos coinciden exactamente y se reproducen 3.509 pares ciertos, 21 posibles, 1.794 del mismo símbolo y 1.736 entre símbolos. Las sumas de categorías y tipos de salida concilian. Los cuatro archivos fuente conservaron sus hashes antes y después de generar el informe.

No se recalculó H4, ningún indicador o trayectoria ni se descargaron datos. Los fixes posteriores de código operativo no se aplican retroactivamente a H5f: éste conserva su evidencia histórica versionada. Se comprueban hashes externos y coherencia del esquema guardado; no se certifican autenticidad del proveedor, validez de la estrategia o capacidad real de ejecución.

No se usó el estrés H5h como nueva estrategia, se sumó P&L, se aceptaron/rechazaron señales ni se asignaron fondos. No hubo acceso a cuentas, red, órdenes o sesión operativa. La suite global y las auditorías operativas paralelas se documentan en el checkpoint general, sin atribuirlas a este módulo.

## Archivos y huellas

Nuevos: `historical_overlap.py`, `test_historical_overlap.py`, este documento y `datasets/20260625_20260923/solapes_casos.json`. El JSON conjunto tiene 1.426.953 bytes y se creó con apertura exclusiva: una ruta ya existente se rechaza.

SHA256 de salida:

`052d0d9f87589ae89300077e671bddb36b0e5762e8c8d998398b56beb091acdd`

SHA256 de código usado, también almacenado dentro del JSON:

- `historical_overlap.py`: `e5c5a8efc6cecf29dd9a805aa70c698dc22ffa2a233f5ea9cf461c6f610cbb10`
- `historical_periods.py`: `9021935cad107b2ac696568a687b798f56278c8854f0600348a80f7d92fc6dfa`

SHA256 de fuentes fijados externamente en `RESULTADO_HISTORICO_CASOS.md` y verificados sin modificaciones:

- BTC casos: `9aee522f66b165b886d421f797634bcdffa50f6ab86d949de6340b03433c5ea1`
- ETH casos: `bdc040c05be46f3dd4ad6b2b594003ab63f2af14a1c10ec03847f2848e17f9d1`
- BTC replay: `fc5f2f27ee73ea67531db18f68d044fed6aa31105f0dcd54b05c3df898a37447`
- ETH replay: `86f31797ab317edae1607963d043cbc771b493df8d8d7d5e1a0fd3c606086223`

## Reproducción local

Desde `C:\Users\tatop\trading-ai`, pruebas:

```powershell
& .\.venv\Scripts\python.exe -m unittest test_historical_overlap test_historical_periods -v
```

Comando usado para crear la salida. Ya existe: repetirlo la rechazará, sin sobrescribir; una futura reproducción necesita otra ruta de salida explícita.

```powershell
& .\.venv\Scripts\python.exe historical_overlap.py --btc-casos datasets/20260625_20260923/BTCUSDT/casos_episodios.json --btc-replay datasets/20260625_20260923/BTCUSDT/replay_senales.json --btc-sha256-casos-esperado 9aee522f66b165b886d421f797634bcdffa50f6ab86d949de6340b03433c5ea1 --btc-sha256-replay-esperado fc5f2f27ee73ea67531db18f68d044fed6aa31105f0dcd54b05c3df898a37447 --eth-casos datasets/20260625_20260923/ETHUSDT/casos_episodios.json --eth-replay datasets/20260625_20260923/ETHUSDT/replay_senales.json --eth-sha256-casos-esperado bdc040c05be46f3dd4ad6b2b594003ab63f2af14a1c10ec03847f2848e17f9d1 --eth-sha256-replay-esperado 86f31797ab317edae1607963d043cbc771b493df8d8d7d5e1a0fd3c606086223 --salida datasets/20260625_20260923/solapes_casos.json
```

## Siguiente dependencia

Este inventario prepara el trabajo de cartera con capital/riesgo compartidos. Todavía faltan su contrato de decisión simultánea y tratamiento de incertidumbre, implementación y pruebas. H6a no decide esas políticas ni convierte la selección de primera señal de episodio en reentrada operativa. Testnet/privada y calibración de costes/fills siguen siendo trabajos separados; iniciar una sesión o acceder a una cuenta continúa reservado al usuario.
