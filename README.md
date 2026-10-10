# TRADING INTELLIGENCE — operación local

## Continuidad compartida — 5 de octubre de 2026

La fuente técnica compartida es [trading-intelligence-ai](https://github.com/tatopozot-rgb/trading-intelligence-ai).
Leer primero [checkpoint vigente](docs/CHECKPOINT.md), [coordinación](docs/AGENT_COORDINATION.md)
y [mapa documental](docs/INDEX.md). Las notas fechadas inferiores conservan el historial local.
Esta importación conserva los módulos existentes; no es un sistema reconstruido ni una versión final validada.

Para comprobar el código en una copia limpia de Windows con Python 3.13:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-paper.txt
$tests = @(Get-ChildItem -File -Filter 'test_*.py' | Select-Object -ExpandProperty BaseName)
if ($tests.Count -eq 0) { throw 'No PAPER test modules found' }
& .\.venv\Scripts\python.exe -B -m unittest @tests -q
```

Las pruebas usan fixtures temporales, no necesitan cuenta, claves, base de datos ni históricos privados.
Tkinter debe estar instalado (componente de Python en Windows). Usar un entorno virtual real:
hay una prueba del launcher de Windows que lo requiere. La integración continua inicial es manual;
no se declara validada hasta observar un run remoto terminado. Ver [importación y límites](docs/archivo/IMPORTACION_2026-10-05.md).

La simulación por reglas funciona como programa Python local, no como un chat haciendo clic por operación.
Claude y Codex se reservan para desarrollo/revisión; no hay consumo de un modelo por cada tick del modo por reglas.
No se ha demostrado ventaja económica: los diagnósticos históricos de cartera existentes fueron negativos.


Cierre30sep2026: suite547OK48,411s tras aislar contexto numérico de fills/cierres/filtros/lectores. No cambian configuración ni fórmulas habituales; evidencia persistida válida se conserva al recalcular. Checkpoint con siguiente bloque exacto en `ESTADO_PROYECTO.md`.

Actualización30-09-2026: H6c cartera compartida completado,392identidades conservadas, cuatro sensibilidades explícitas y540pruebasOK. Resultados realizados negativos en ambos tiempos, con posición abierta sin valorar a mercado: NO rentabilidad validada ni réplica exacta del runner. Ver `RESULTADO_CARTERA_PAPER.md`. No cambia estrategia, configuración ni sesiones.

Actualización29-09-2026: modelo de profundidad optativo integrado y conservado tras reinicio; controles de selección en panel, cantidad/fees verificables y conciliación antes del arranque. Ver `MODELO_FILLS_PAPER.md`. Diagnóstico técnico sin iniciar operaciones: `.\.venv\Scripts\python.exe -B paper_doctor.py`; ver `ENTORNO_Y_DIAGNOSTICO.md`. Integraciones Spot y XM/MT5 separadas: `PLATAFORMAS_BINANCE_XM.md`. Estado y pruebas actuales en `ESTADO_PROYECTO.md`; los conteos fechados inferiores son históricos.

Este MVP simula operaciones (PAPER). No envía órdenes a Binance ni utiliza claves del exchange. La meta de crecimiento no es una promesa de rentabilidad. Las pruebas de software no demuestran una estrategia rentable.

Meta de piloto técnico al7octubre2026: ver PLAN_PILOTO.md. Historia de90d significa analizar el pasado ahora, no esperar tres meses. Dinero real sigue bloqueado y requiere evidencia y autorización posterior.

## Qué está automatizado

Actualización autorizada el 22-09-2026: nuevo modo `--reglas-paper` para simulación autónoma por la estrategia existente, sin revisión IA por entrada. `paper_rules.py` consume candidatos del scanner y obtiene una cotización antes de abrir; `paper_store.py` conserva límites de riesgo/capital/posiciones, pausa, hash, caducidad y consumo único. La aprobación del desarrollo NO autoriza iniciar sesiones: el usuario pidió confirmar antes de empezar el programa. No requiere iniciar sesión en Binance para PAPER.

Modo nuevo y circuito asistido son excluyentes. El nuevo no exporta paquetes ni consume archivos Claude, y no fabrica confianza/respuestas de IA. Su origen REGLAS_PAPER_V1 queda dentro del plan hasheado y el evento APERTURA indica SESION_REGLAS_PAPER. Claude sigue disponible para desarrollo/auditoría por chat, sin API de pago. Cada sesión sigue limitada a ocho horas; no existe servicio 24/7 ni reinicio automático autorizado. El monitor deja de vigilar al terminar o apagar; las posiciones no se cierran por detener.

Comando reservado para un inicio que el usuario autorice posteriormente, **no ejecutado durante el desarrollo**:

```powershell
.\.venv\Scripts\python.exe system_runner.py --continuo --reglas-paper --horas 8 --reanudar
```

El motor nuevo pasó pruebas aisladas de apertura/cierre/ciclo continuo y la integración desde respuestas HTTP ficticias hasta scanner, indicadores, estrategia, apertura/cierre y conciliación reales del programa. R2 añadió siete pruebas con red/Claude bloqueados y bases temporales (258 tests en esa etapa). La pantalla local ya está implementada y una sesión autorizada30min con mercado actual finalizó correctamente el23-09-2026. Estas pruebas no demuestran rentabilidad ni equivalen a trading real.

Datos públicos Binance → indicadores de velas cerradas → propuestas → exportación para Claude. El ciclo continuo escanea cada 15 minutos después de terminar el escaneo anterior y vigila posiciones cada 60 segundos por separado. Registra en SQLite las solicitudes, aperturas, cierres y movimientos de capital simulado.

Claude web todavía requiere intercambio asistido: enviar `claude_request.txt` al chat existente y guardar el JSON de respuesta. No hay conexión automática de pago a Claude. `--auto-paper` solo consume respuestas recibidas, NO obtiene revisiones de Claude.

Decisión del 20-09-2026: mantener chat asistido y aplazar la API Claude. El 22-09-2026 se autorizó además el modo PAPER autónomo por reglas descrito arriba; no se cambian límites financieros ni se habilita la API. La intención de usar su cuenta Binance no habilita dinero real ni acceso a esa cuenta. Capital y pérdida máxima de una futura sesión real requieren definición explícita previa.

## Panel local PAPER — R3b.3

`paper_dashboard.py` abre el panel sin iniciar trading ni consultar mercado. La consulta de saldo/posiciones/solicitudes/eventos es sólo lectura. Tablas con desplazamiento y detalle por selección, últimos100 registros; se actualizan con «Actualizar lectura». No usa Claude por operación ni se conecta a tu cuenta Binance.

Ahora incluye controles explícitos: indica duración en horas (0,5 = 30 minutos; máximo8) y pulsa «Iniciar PAPER». El diálogo exige confirmar y por defecto responde NO. No empieza al abrir ni al actualizar. «Pausar entradas» conserva el monitor; «Reanudar entradas» exige confirmación y no inicia otro proceso ni quita STOP. «Detener sesión» solicita parada cooperativa, no liquida. Cerrar/X advierte si el proceso propio sigue vivo o incierto y nunca lo detiene implícitamente. Otros procesos no se verifican desde el handle propio: el bloqueo SO del runner impide dos sesiones simultáneas.

Estado propio actualizado cada segundo sin consultas de mercado. Un registro ACTIVO no garantiza salud; revisar monitor/scanner y conciliación. Fallos visibles sin reintentos automáticos. Revisión visual y primera sesión30min autorizada completadas; cada nueva sesión exige inicio explícito.

```powershell
.\.venv\Scripts\python.exe paper_dashboard.py
# Lectura sin ventana:
.\.venv\Scripts\python.exe paper_dashboard.py --json
```

No interpreta ACTIVO guardado como prueba de proceso vivo ni señales de pausa/parada como confirmación de aceptación. Muestra heartbeat_utc cuando está guardado como ACTIVO y fecha del estado final; una lectura fallida sustituye cifras y filas anteriores. No calcula valoración actual ni rentabilidad futura y no reemplaza la conciliación de paper_report.py. Probado con ventana oculta y BD temporales: trece pruebas de panel; suite total271 OK. Sin revisión visual en pantalla ni sesión operativa durante desarrollo.

## Controlador y pruebas

Actualización23-09-2026: corregida identificación de Windows venv (PID o parent_pid coincidente con handle propio, más ID/modo). Suite297 OK previa. Reintento autorizado de246d5ef0a94b56b1ce0f80212fec77 completó30min:10:31:56–11:01:56 Guayaquil, parada automática y trabajadores cerrados. Dos scanner de5símbolos/0errores/0entradas y30monitor/0errores; saldo simulado100/P&L0/conciliaciónOK. No relanzar automáticamente. Objetivo continuo eliminado; el seguimiento5h también fue eliminado el24sep, no queda programado. No demuestra rentabilidad.

R3b.2 añade `paper_control.py`: confirmación y duración explícitas (máximo ocho horas), proceso oculto Windows con argumentos fijos/sin shell, log por intento, observación del proceso propio y protección frente doble inicio. El runner publica un ID de sesión en latido y apagado; no confundir registro ACTIVO con salud de mercado.

Pausa no detiene monitor; reanudar entradas requiere confirmación y nunca quita STOP ni inicia un proceso. Parada escribe STOP global y una cancelación por intento que evita perder la petición durante el arranque. Esas señales no se limpian automáticamente. No mata procesos ni liquida posiciones. R3b.3 conecta los botones: nueve tests nuevos de controles UI, suite completa295 OK con launcher falso/Tk oculto. BD de trabajo intacta y ninguna sesión operativa iniciada. --json conserva sólo lectura sin crear controlador ni ventana.

## Uso en PowerShell

Desde `C:\Users\tatop\trading-ai`, sin necesidad de activar el entorno:

```powershell
# Un ciclo sin abrir operaciones por sí mismo
.\.venv\Scripts\python.exe system_runner.py

# Sesión de hasta 8 horas; autorización manual predeterminada
.\.venv\Scripts\python.exe system_runner.py --continuo --horas 8 --reanudar

# Detener desde otra ventana; espera a que terminen consultas en curso
.\.venv\Scripts\python.exe system_runner.py --detener

# Importar JSON de Claude. Si aprueba, solicita OK <ID> en esta consola
.\.venv\Scripts\python.exe claude_authorizer.py --archivo .\claude_response.json

# Ver saldo y posiciones simuladas
.\.venv\Scripts\python.exe paper_account.py
.\.venv\Scripts\python.exe paper_trader.py

# Pruebas aisladas; no tocan el saldo de trabajo
.\.venv\Scripts\python.exe -m unittest discover -v

# Diagnóstico y conciliación sin modificar SQLite
.\.venv\Scripts\python.exe paper_report.py
```

La sesión automática PAPER es optativa: agregar `--auto-paper` a la sesión continua. Consume JSON depositados en `respuestas/`, exige revisión válida y sesión vigente, y los mueve a `respuestas/procesadas/`. Sin revisión válida no abre nada. El modo manual no consume esos archivos automáticamente.

Los fallos de bandeja generan `BANDEJA_FALLO` con archivo, marca temporal/tamaño, clase de error y etapa (metadatos, importación, auditoría o archivado), sin copiar el contenido. La salud `bandeja` conserva fallos pendientes y contador acumulado; procesar otro archivo no los oculta. No se reintenta la misma marca durante esa sesión. Modificar un archivo o reiniciar permite otra validación completa, no autoriza operaciones ni elude caducidad/consumo único. Un fallo de archivado puede ocurrir DESPUÉS de registrar una operación: comprueba la base antes de interpretar el error. Si la auditoría también falla, se indica en salud y registro; no se afirma que el evento quedó guardado. Salud OK significa importación resuelta, incluso si la respuesta fue rechazada; no significa aprobación de trading. Los pendientes en salud son de la sesión, los eventos SQLite persisten; borrar/mover manualmente un archivo no resuelve automáticamente su advertencia de esa sesión.

## Controles y límites

Conexión y restricciones Binance: ver `CONEXION_BINANCE.md`. El cliente público respeta bloqueos403/418/429; HTTP451 exige revisión local sin vencimiento automático. No se debe reutilizar el reintento de GET para enviar órdenes. Claude/Cowork se usan para desarrollo/revisión, no como navegador operador por cada transacción.

- ID único, hash del plan, símbolo, caducidad de 15 minutos y consumo único. Confianza debe ser entero 0–100; no representa probabilidad de ganar.
- Riesgo presupuestado 1% por operación, máximo 3 abiertas; pérdidas realizadas del día más riesgo abierto/nuevo no pueden superar 3% del saldo base diario. Las ganancias no borran pérdidas del día.
- Capital disponible, sin símbolo duplicado; nueva cotización antes de abrir, desviación máxima 0,25%. Comisiones simuladas estimadas 0,1% por lado, no tarifa real verificada.
- La comisión queda fijada en cada propuesta/operación: cambios posteriores no reescriben resultados. Tarifas históricas desconocidas no se inventan. Solicitudes vencidas se marcan CADUCADA; importaciones inválidas quedan auditadas.
- El diagnóstico de solo lectura devuelve OK, DISCREPANCIA o NO_VERIFICADO. No corrige registros y un OK no demuestra rentabilidad ni aptitud para dinero real.
- Archivo `PAUSA_ENTRADAS` bloquea nuevas aperturas sin detener el monitor. `DETENER_RUNNER` detiene todo el ciclo. `--reanudar` retira esta última señal explícitamente.
- Al detenerse o apagarse la PC, las posiciones PAPER permanecen abiertas y dejan de vigilarse hasta otro inicio. NO existen stops enviados al exchange. Saltos de precio pueden superar el riesgo presupuestado.
- El saldo actual se usa al dimensionar propuestas; los aportes/retiros simulados se registran aparte del P&L. No confundirlos con transferencias reales.

## Evidencia y continuidad

29-09: suite527pruebasOK. `historical_portfolio.py` añade motor puro de cartera compartida, únicamente con escenarios explícitos, no conectado al runner ni aplicado aún a392casos; `CONTRATO_CARTERA_PAPER.md` explica reconocimiento de fees, incertidumbre y diferencias contables.16pruebas incluyen200escenarios sintéticos/6000candidatos. No confundir métricas realizadas sin MTM con equity/rentabilidad demostrada.

Para retomar con poco contexto: `CONTINUAR_CON_CLAUDE.md`; estado completo vigente en `ESTADO_PROYECTO.md`. El seguimiento5h fue eliminado, no está pausado ni se reanuda solo. Cowork disponible no implica acceso automático a archivos locales.

Las demostraciones `market_data.py` y `technical_analysis.py` usan el transporte público y el análisis validados. Solo consultan datos al ejecutarlas explícitamente, no al importarlas. El radar demo muestra hasta 15 resultados; no cambia los 5 del scanner. El análisis demo ahora usa exclusivamente velas cerradas y rechaza datos inválidos igual que el motor principal; no ejecuta órdenes.

`runner_status.json`: estado y hora del último latido; verificar también que el proceso siga vivo. `logs/runner.log`: actividad y errores. `trading.db`: registro persistente. `solicitudes/`: paquetes históricos. `ESTADO_PROYECTO.md`: índice de estado, decisiones y siguiente acción.

El estado incluye salud separada de monitor/scanner (ciclos, errores y resultados). ACTIVO no significa que las consultas funcionen. Durante el apagado se conserva DETENIENDO y el bloqueo de instancia hasta terminar ambos trabajadores, sin matarlos. El estado muestra tiempo de espera y fallos de escritura cuando puede guardarse. Un segundo Ctrl+C se ignora durante esa limpieza en el hilo principal. Si un trabajador no termina, el apagado espera y no permite otra instancia; no promete una duración máxima. Si falla el disco, el archivo puede quedar desactualizado: comprueba el proceso y el registro antes de interpretar el último estado. Las posiciones PAPER no se liquidan por apagar.

El scanner continuo comprueba parada/vencimiento antes de consultar, generar y comenzar la publicación de solicitudes. La transacción de una solicitud vuelve a comprobarlo antes de insertar y antes de confirmar; si detecta el fin, revierte solicitud/evento. Salud muestra CANCELADO, no éxito. Es cancelación cooperativa, no interrupción instantánea: una publicación o confirmación ya iniciada puede terminar entre comprobaciones. Se conservan registros previamente confirmados con su caducidad normal; generar/exportar una solicitud nunca autoriza abrir una operación. El ciclo único manual mantiene su funcionamiento.

## Lo pendiente antes de dinero real

H5h: `historical_delay.py` compara entrada hipotética+una vela15m en los mismos casos/señales H5f, con nuevo precio de apertura y fin absoluto sin ampliar. Conserva evidencia/ATR porcentual/capital/comisión/reglas, explicita exclusiones y matrices por señalUTC. No toca el runner ni recalcula90d.419pruebas aprobadas al25sep2026; resultados y límites en `RESULTADO_RETRASO_15M.md`. BTC2/164 y ETH10/228 cambian categoría, cero excluidos. Esto no recomienda retrasar entradas ni valida cartera/rentabilidad. Próximo H6a: inventario conjunto BTC/ETH de solapes, antes de adjudicar capital/riesgo compartidos.

H5g: `historical_periods.py` resume los informes H5f existentes por mes, semanaISO y día UTC de la señal, incluyendo ceros y cobertura parcial. No recalcula indicadores/salidas ni suma P&L. Los desenlaces pueden ocurrir fuera del período de señal. Requiere hashes externos de casos/replay y salida nueva; resultados en `RESULTADO_HISTORICO_PERIODOS.md`. No se confunde desglose temporal con una estrategia nueva. El estrés de retraso posterior ya está completado en H5h.

H5f: `historical_batch.evaluar_lote` consume casos explícitos reutilizando H4 validado (hash externo de archivo, huella de filas/manifiesto/código, estructura, símbolo, malla, ventanas, cierre/precio y coherencia de indicadores/contadores). No recalcula todos los indicadores ni certifica autenticidad. Comparte constructores H5c/H5e y mantiene cada resultado independiente, no ejecutable. `historical_batch_report.py` exige parámetros y selección/modelo explícitos, no sobrescribe salidas. Diagnóstico completo por episodios deBTC/ETH ya generado:392casos; informe humano RESULTADO_HISTORICO_CASOS.md. No es cartera ni permite sumar ganancias de posiciones solapadas. No volver a ejecutar estos informes con los mismos destinos; conservar evidencia.

H5e: `historical_case.evaluar_caso` une propuesta H5c y trayectoria H5d para un caso aislado. Exige capital/comisión, instante de señal, entrada no anterior y alineada15m, fin, precio de entrada aportado y modelos explícitos. No infiere entrada desde cierre1h; este sigue siendo referencia separada. Usa ATR/señal cerrados al instante de análisis y recalcula niveles con precio hipotético aportado. Si las reglas indican ESPERAR no inventa operación. No reproduce caducidad, tolerancia de cotización o cartera del runner; no se suman casos simultáneos como P&L de cuenta. Entradas/planes/resultados quedan no ejecutables y no son consumidos por el modo PAPER operativo. Probado con fixtures; todavía no evaluado económicamente sobre todo el historial.

H5d: `historical_path.evaluar_trayectoria` evalúa una posición LONG hipotética ya abierta en una secuencia15m completa y explícita. Requiere entrada/tamaño/stop/objetivo/comisión, rango y modelo `BARRERA_TOQUE_APERTURA_SALTO_SIN_DESLIZAMIENTO_V1`; no hay modelo por defecto ni conexión al runner. El modelo de prueba supone salida en barrera al toque o apertura OHLC al salto: no acredita fills, liquidez, deslizamiento ni monitor60s. Se detiene ante el primer evento; conserva ambos resultados si es ambiguo. Sin evento no liquida al final. Valida toda la cobertura y no usa velas posteriores para elegir el resultado. Es pieza offline aislada: no integra aún cartera, entradas por señales, reinversión ni riesgo diario; no se ha aplicado al historial completo ni cambia política operativa.

H5c: `trade_planner.crear_plan_con_datos` comparte reglas y aritmética con el wrapper vivo, pero exige capital, referencia y comisión explícitos; no consulta red/BD. Rechaza datos financieros inválidos y niveles no positivos. `historical_proposal.proponer_instante` reutiliza H1 a reloj UTC explícito: cierre1h conocido es sólo referencia, nunca cotización contemporánea ni fill. Declara capital aportado sin evolución de cartera, salida no ejecutable y decisión separada PROPUESTA HISTORICA; el consumidor PAPER por reglas no la acepta. No controla saldo libre, posiciones simultáneas ni pérdidas diarias de una cartera histórica: esa integración sigue pendiente. Las velas abiertas ocupan ventana pero sus precios no se usan. Pruebas de paridad, capital variable, datos futuros y rechazo de consumo aprobadas.

H5a comparte `paper_store.calcular_resultado_cierre` entre cierre PAPER e hipótesis offline: misma fórmula de comisiones de entrada/salida, sin precios elegidos automáticamente. `historical_economics.py` diagnostica niveles en OHLC y distingue apertura fuera de niveles, toque único, ninguno o ambos (ambiguo). No confirma fills ni elige orden intravela; `resultado_hipotetico` exige entrada/salida/tamaño/comisión explícitos. Es base aritmética, no cartera histórica ni pronóstico. H5b añade escenarios_ambiguedad: conserva STOP_PRIMERO y OBJETIVO_PRIMERO como hipótesis separadas, con comisiones y sin selección, promedio ni probabilidades inventadas. Requiere posición LONG ya abierta antes de la vela y declara salida exacta en cada barrera sin deslizamiento como supuesto, no como fill. Los saltos de apertura quedan diagnosticados sin resultados inventados. No se generó P&L histórico de cartera.

H4: `historical_replay.py` reproduce indicadores y condiciones técnicas sobre los manifiestos existentes. Rango explícito [inicio,fin), malla diagnóstica15m, sin consultas ni trading.db. Conserva análisis/ventanas por instante, conteos de estados/condiciones y episodios consecutivos, huellas de datos/código/filas y limitaciones. Usa caché por ventana cerrada, contrastada punto a punto con H1 en tests. No estima órdenes/P&L ni replica las demoras del scanner real (15m después de cada análisis). Una condición sostenida en diez puntos no equivale a diez compras. CLI exige manifest/inicio/fin-exclusivo/salida y no sobrescribe informes.

H3: `historical_download.py` descarga únicamente `/api/v3/klines` público con rangos UTC explícitos, paginación de hasta1000, rechazo de huecos y sin sobrescribir destinos. Reutiliza restricciones HTTP del transporte existente. CLI exige símbolo/inicio/fin-exclusivo/destino; agrega200velas previas por marco para indicadores. Manifiesto se publica tras tres series completas; un fallo conserva solicitud/parciales sin declararlos terminados. Fuente: https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market . BTCUSDT/ETHUSDT25jun–22sep2026 descargados, validación H2 y muestra temporal reproducible; no backtest económico aún.

### Base de análisis histórico offline — H1

`historical_analysis.analizar_instante(simbolo, series, instante_ms)` recibe un diccionario de DataFrames15m/1h/4h y reloj UTC explícito en milisegundos. Reutiliza indicadores y consenso del motor actual; no consulta red, cotizaciones actuales ni saldo, y no genera órdenes. Selecciona hasta200 velas iniciadas al instante y excluye precios de la vela aún abierta; exige60 cerradas por marco y rechaza huecos, duplicados, desorden y datos obsoletos. Estado histórico de H1: entonces no existían cargador ni descarga; H2/H3 posteriores, descritos arriba, ya los incorporan.

Es una reconstrucción de indicadores, NO un backtest de ganancias: no representa selección histórica del radar, fills, costos ni cartera. No demuestra rentabilidad ni independencia fuera de muestra. Universo, período, procedencia y supuestos de ejecución deberán quedar explícitos antes de evaluar resultados económicos. Pruebas sintéticas con red/SQLite bloqueados verifican ausencia de anticipación, límites de cierre y equivalencia de ventana con el motor actual.

H2 añade `historical_dataset.cargar_dataset(ruta)` y `analizar_dataset(ruta, instante_ms)`, sólo lectura local. Manifiesto JSONv1 exige `version`, `simbolo`, `origen_declarado` y `series` con exactamente15m/1h/4h; cada marco declara `archivo`, `sha256`, `filas`, `inicio_ms` (primera apertura) y `fin_ms` (último cierre incluido). Cada serie JSON es una lista de objetos con `tiempo_apertura`, `tiempo_cierre`, `apertura`, `maximo`, `minimo`, `cierre`, `volumen`. Sólo archivos hermanos, máximo8MiB por serie/64KiB manifiesto; rechaza huellas/rangos falsos, claves duplicadas y defectos en toda la serie, no sólo la ventana. Las huellas comprueban integridad, NO autenticidad: `procedencia_verificada` permanece false. Las pruebas de H2 utilizan datos sintéticos; la descarga posterior H3 está descrita arriba.

Primer componente de ejecución preparado: `execution_filters.py` valida únicamente filtros estáticos sobre fixtures LIMIT y siempre devuelve `enviable: false`. No firma, envía ni consulta órdenes; tampoco verifica saldo, autorización o vigencia del snapshot. Filtros desconocidos bloquean la validación. El contrato y las etapas restantes se detallan en `CONTRATO_EJECUCION_OFFLINE.md`. Esto no habilita testnet operativo ni dinero real.

El ledger `execution_ledger.py` conserva fills de pruebas offline y detecta duplicados/conflictos en bases separadas. Compara acumulados proporcionados y mantiene comisiones por activo, sin conversión ni cambios a PAPER. `execution_orders.py` añade intenciones inmutables, snapshots de prueba ordenados, conflictos persistentes e incertidumbre tras reinicio sin reenvío. La coincidencia de totales no demuestra que una orden haya terminado ni que una posición esté cerrada. No existe transporte ni liberación automática del ámbito bloqueado.

`execution_context.py` verifica explícitamente hashes de plan/snapshot, correspondencia con intención y vigencia con reloj/umbral suministrados, sin elegir plazos operativos. JSON textual rechaza claves repetidas y números no admitidos. Es comprobación offline, no autenticación ni autorización: devuelve `enviable=false` y `autorizado=false`, sin cambiar estado. Aún faltan filtros completos, política temporal operativa y aplicación obligatoria antes de cualquier transporte futuro.

`exchange_context.py` conserva e inventaría controles de exchangeInfo público mediante consulta estricta, con origen separado de Testnet. Diagnostica LIMIT simple pero siempre mantiene NO_VALIDABLE_PARA_ENVIO: permisos/filtros privados, precios de referencia y vigencia siguen pendientes. Conserva huellas separadas de respuesta completa y reglas (esta última excluye solo serverTime). No omite silenciosamente filtros desconocidos ni conecta cuentas.

`execution_percent.py` prueba filtros porcentuales con evidencia sintética explícita: referencia prioritaria o, solo ante ausencia verificada, VWAP/último trade según ventana. Rechaza fuentes, tiempos y hashes incompatibles; no modifica precios ni autoriza. Evalúa un filtro, no PRICE_RANGE ni todas las condiciones de una orden.

`execution_bundle.py` integra filtros/contexto/evidencias mediante plan V2 ligado a intención. Exige límites temporales externos explícitos: el plan no puede ampliarlos por sí mismo. Rechaza cualquier filtro o evidencia no soportados; la salida siempre mantiene envío y autorización deshabilitados.

`execution_audit.py` guarda paquetes/evaluaciones/eventos atómicos en ledger offline separado, sin sobrescribir originales. Duplicados devuelven historia no autorizante; discrepancias quedan bloqueadas. Su constructor inicializa tablas: no usarlo como lector de bases ajenas. Los tests usan exclusivamente bases temporales.

`execution_audit_report.py` es el lector independiente para Windows. Exige ruta existente explícita con sufijo `.offline.sqlite3` e ID de intención; verifica identidad/esquema y reutiliza el informe en una transacción `mode=ro/query_only`, sin crear ni migrar. Ejemplo con una base de pruebas ya existente (no se crea al ejecutar):

```powershell
.\.venv\Scripts\python.exe -B execution_audit_report.py --base C:\ruta\ejemplo.offline.sqlite3 --id i1
```

JSON histórico y no autorizante: salida 0 REGISTRO_INTEGRO, 1 DISCREPANCIA, 2 NO_VERIFICADO (o argumentos inválidos). Sólo admite bases locales cerradas con journal de rollback; WAL, archivos auxiliares presentes, esquemas desconocidos o escritor abierto provocan rechazo sin limpieza/reparación. Conserva un handle de lectura que impide escritura/reemplazo ordinarios durante la consulta; no promete protección ante manipulación hostil del sistema. Integridad histórica no significa vigencia, rentabilidad ni autorización. No sirve para `trading.db`: para esa base usar `paper_report.py`.

Integración desatendida de revisión Claude con autorización de acceso y presupuesto; pruebas de estrategia fuera de muestra y seguimiento PAPER; adaptador testnet separado, filtros de mercado, reconciliación de órdenes/fills y stops en el exchange; verificación de elegibilidad y obligaciones aplicables. Cambiar la URL o una bandera NO habilita ni valida operación real. No pegar claves en chats ni guardarlas en el código.
