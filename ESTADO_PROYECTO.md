# Índice de continuidad — TRADING INTELLIGENCE

## Continuidad vigente desde 05-10-2026

Este archivo conserva el historial local. La continuidad compartida se lee ahora en
`docs/CHECKPOINT.md` y `docs/AGENT_COORDINATION.md` del repositorio privado
`tatopozot-rgb/trading-intelligence-ai`. Las instrucciones antiguas no prevalecen si contradicen
el nuevo encargo de coordinación. El usuario autorizó expresamente un nuevo seguimiento de desarrollo
cada ocho horas; no recrear los antiguos objetivos ni seguimientos de una/cinco horas.
La importación no traslada bases de datos, claves, sesiones ni datasets. No inicia el programa operativo.


Actualizado: 30 de septiembre de 2026. Estado vigente; no reiniciar lo completado.

## CHECKPOINT VIGENTE — H6c y estabilidad numérica operativa; 547pruebasOK (30-09-2026)

Bloque final30sep: corregido contexto Decimal heredado también en paper_fills.py (simular/resultado_cierre), execution_filters.py, execution_percent.py y broker_adapters.py. Revisión auxiliar reprodujo rechazo de evidencia válida con ROUND_UP e Inexact/Overflow/Clamped heredados; contextos ahora explícitos, conservando precisión y traps intencionales. test_decimal_isolation.py nuevo:7tests con redondeoUP/DOWN,prec2,Emin/Emax0,clamp1,todastraps activadas, resultado idéntico y contexto llamante intacto; adulteración sigue rechazada.75testsdirigidosOK0,987s y suiteFINAL547OK48,411s. No se reescribió ledger/modelo ni resultados históricos. Doctor30sep08:46Guayaquil:configPAPEROK,requests/pandasimportables,conciliaciónOK0trades/2solicitudes/11eventos; registroDETENIDO23sepantiguo da NO_VERIFICADO del proceso, no error contable. Ningún proceso operativo iniciado.

1. Terminado: adaptador histórico offline H6c conecta H5f/H6a guardados al motor de cartera común. Conserva392identidades/6censurados y aplica cuatro hipótesis temprano/tardío × stop/objetivo ambiguo sin elegir ganador ni declarar extremos garantizados. Hashes externos validados, originales sin cambios, sin red/indicadores/BD operativa. Auditor auxiliar encontró dependencia del contexto Decimal externo; motor ahora fija contexto completo y tiene test de independencia.
2. Archivos: nuevos historical_portfolio_report.py, test_historical_portfolio_report.py, RESULTADO_CARTERA_PAPER.md y datasets/20260625_20260923/cartera_sensibilidades.json. Modificados historical_portfolio.py, test_historical_portfolio.py, CONTRATO_CARTERA_PAPER.md, README.md, PLAN_PILOTO.md, CONTINUAR_CON_CLAUDE.md e índice. SHA256salida:9ad94b069fa69ee68ec45fe6f48f5b10a3e4a987ecfc3932ae5e136697176d43.
3. Pruebas:29dirigidasOK3,378s (17motor+12adaptador, incluyendo200escenarios sintéticos previos). Generación offline392casosOK. Suite completa540OK59,126s. Conciliación independiente de cuatrovariantes a300dígitos confirma cash/fees/saldo y75/73aperturas74/72cierres; cuatrofuentesoriginales intactas. Intento anterior de suite no ejecutado por fallo de cuota de auto-review; recuperación oficial confirmada30sep08:38Guayaquil,90%5h/11%semanal restante, y reintento exitoso. No comprar/canjear. Errores impresos por suite corresponden a fallos simulados esperados.
4. Resultado diagnóstico: temprano75aceptados/317rechazados, saldo realizado NO MTM87,0513; tardío73/319,saldo88,8265 desde100hipotéticos. Una posición ETH permanece abierta a coste, NO valor final de cuenta; pérdidas realizadas -12,9487/-11,1735 incluyen fee de esa entrada. Cero casos ambiguos en esta muestra hace idénticas stop/objetivo dentro de cada tiempo; fixtures sí prueban ambas barreras. No seleccionar tardío por mejor resultado, no prometer rentabilidad ni convertirlo en estrategia.
5. Claude: permiso explícito del usuario recibido; envío autorizado completado en chat existente mensajes55/56 con Sonnet5.5Medio seleccionado. Revisión conceptual de contrato, no acceso/ejecución local. Conservación de rechazos/efecto fee incorporados; sugerencia de no variar tiempos de casos sin ambigüedad descartada: sensibilidad temporal aplica a toda salida intravela. Sonnet5.5/Opus5.5 visibles sin aviso de compra; otros modelos requieren créditos, no usados. Cuota exactaClaude desconocida. Seguimiento eliminado sin cambios.
6. Próximo EXACTO: integrar filtros/lotes en un modelo de fill versionado, comenzando por contrato de volumen/tipo de orden y fixture end-to-end. Primero leer MODELO_FILLS_PAPER.md, execution_filters.py, execution_percent.py, execution_context.py y paper_fills.py; verificar documentación oficial vigente de Binance para LOT_SIZE/MARKET_LOT_SIZE y quoteOrderQty antes de cambiar semántica. Reutilizar ruta pública exchangeInfo ya permitida en market_http.py y contratos existentes; NO reescribir LIMIT ni aplicar sus reglas por analogía a compra por presupuesto quote. Conservar V1/evidencias históricas y modelo persistido para cierres; definir nuevo contrato técnico explícito y probar caducidad, paso, mínimo, dust y falta de metadatos antes de conectar a runner. No importarMT5/cuentas/órdenes. Históricos y suite547 ya cerrados: no repetir sin cambios. Costos/estrategia fuera de muestra, transporte privado e integraciónXM siguen pendientes; fase completa NO terminada.

## Checkpoint anterior — fills integrados, diagnóstico y H6b verificados (29-09-2026)


1. Terminado: profundidad optativa FOK integrada en reglas/monitor/SQLite/panel, modelo persistente y evidencia atómica recalculable. Corregidos reserva de comisión/base diaria, cantidad Decimal original de compra (sin reconstrucción float), P&L por quotes/fees y cero con exponente enorme. Conciliación previa bloquea trabajadores y retirada de STOP ante discrepancias. Doctor sólo lectura y lectores Spot/XM separados completos en su alcance. H6a inventario conjunto ya completo; H6b motor puro de cartera compartida con candidatos/tiempos explícitos y sin conexión al runner.
2. Archivos nuevos de estos bloques: paper_fills.py, test_paper_fills.py, test_paper_depth.py, test_paper_cash.py, test_runner_preflight.py, historical_overlap.py, test_historical_overlap.py, RESULTADO_SOLAPES.md, datasets/20260625_20260923/solapes_casos.json, broker_adapters.py, test_broker_adapters.py, PLATAFORMAS_BINANCE_XM.md, paper_doctor.py, test_paper_doctor.py, ENTORNO_Y_DIAGNOSTICO.md, MODELO_FILLS_PAPER.md, historical_portfolio.py, test_historical_portfolio.py, CONTRATO_CARTERA_PAPER.md. Modificados: market_http.py, paper_store.py, risk_engine.py, trade_planner.py, paper_report.py, paper_monitor.py, paper_rules.py, system_runner.py, paper_control.py, paper_dashboard.py, test_paper_control.py, test_paper_ui_controls.py y documentos de continuidad. No cambios de config/estrategia ni de los JSON históricos originales.
3. Pruebas: suite FINAL527OK43,537s (`.\.venv\Scripts\python.exe -B -m unittest discover -q`). H6b16tests incluyen200escenarios reproducibles/6000candidatos: conservación cash+nominal/saldo, fees, cantidad, simultaneidad, pérdidas diarias no compensadas por ganancias, censura, gaps y controles numéricos. Correcciones depth/doctor/portfolio49testsOK1,504s antes de añadir estrés. Diagnóstico real del29sep21:57Guayaquil: PAPER correcto, requests2.34.2/pandas3.0.6 importables, conciliaciónOK0trades/2solicitudes/11eventos. EstadoDETENIDO23sep antiguo da NO_VERIFICADO (no es error contable ni acredita proceso vivo). No nueva sesión operativa ni consulta de mercado.
4. Problemas resueltos: suite inicial476tuvo1fallo por orden de mensaje Comisión/solicitud, corregido conservando validación. Auditoría reprodujo fracción extra/residual por float; compra100.3/100.1 y reinicio días después ya cubiertos. Caducidad durante apertura/cierre revierte datos/saldo/eventos. Doctor inicialmente no reconocía heartbeat_utc de ACTIVO, corregido con tests. Anterior errorDLL no reapareció; ninguna protección del sistema modificada.
5. Bloqueos reales: revisión externa Claude no enviada; auto-review rechazó transferencia de detalles internos y necesita aprobación explícita para ese resumen/chat antes de reintentar. No impide trabajo local. Cuota global desconocida por error de herramienta oficial; tres revisores auxiliares alcanzaron límite, sin reiniciarlos en bucle. Principal cerró doctor/H6b/pruebas. Sin nuevas claves/cuentas/transporte privado comprobado. Conectores Spot/XM son lectores, no integración ejecutora. CarteraH6b no ha sido aplicada a392casos ni validada contra operación real.
6. Próximo EXACTO: H6c, adaptador sólo offline desde H5f/H6a guardados y hashes externos al motorH6b. Preservar392identidades, nulos/censura y datos originales; comparar escenarios explícitos de tiempo de salida intravela temprano/tardío y, si aplica, stop/objetivo ambiguos, SIN declarar bounds garantizados ni seleccionar ganador. Capital/riesgo sólo parámetros PAPER existentes o explícitos; documentar distinta convención de fee/riesgo deH6b (ver CONTRATO_CARTERA_PAPER.md). No recalcularH4/indicadores ni redescargar. Probar adaptador/consistencia y guardar salida exclusiva+informe; no tocar trading.db. Después filtros/lotes en fills y validación de transporte/recuperación separada. Quedan pendientes técnicos: no declarar proyecto terminado.

Comandos seguros de reanudación desde C:\Users\tatop\trading-ai: `.\.venv\Scripts\python.exe -B paper_doctor.py` y pruebas dirigidas al módulo modificado. No repetir suite sin cambios;527OK es evidencia vigente de este bloque. Panel: `.\.venv\Scripts\python.exe -B paper_dashboard.py` sólo abre la ventana; arranque reservado al usuario. Sin automatización ni objetivo continuo.

## Bitácora intermedia del bloque (histórica; sustituida por checkpoint anterior)

Usuario autoriza resolver decisiones técnicas sin preguntas, implementar/refactorizar/probar y continuar trabajo seguro aunque falten accesos. Binance y XM separados; XM/MetaTrader debe verificarse, nunca aplicar fórmulas Spot por analogía. Mantener PAPER/simulación, sin fondos/órdenes reales/retiros/claves. Seguimiento automático sigue eliminado: no crear objetivos ni tareas recurrentes. Trabajar por bloques verificables, no gastar cuota sólo para agotarla.

Reanudación29sep: se inspeccionaron archivos antes de trabajar. Cuota actual NO VERIFICADA: lectura oficial devolvió error técnico, no límite confirmado; no comprar/canjear ni repetir consultas. La interrupción28sep había dejado integración escrita y34pruebas dirigidas aprobadas, aunque el checkpoint anterior no llegó a reflejarlo.

Integración ya guardada: paper_fills.py/test_paper_fills.py, ruta GET depth en market_http.py, paper_rules.py/paper_monitor.py/paper_store.py/paper_report.py/system_runner.py y test_paper_depth.py. Modelo Decimal, BUY por nominal/SELL por cantidad, VWAP/fee, parciales explícitos; el ledger sólo acepta FOK completo; evidencia APERTURA/CIERRE atómica y modelo persistente. Conciliación antes de arrancar trabajadores. Sigue pendiente corregir redondeo de cantidad SELL detectado en auditoría29sep (usar evidencia Decimal de compra, no nominal/VWAP float) y cero con exponente enorme. No declarar cerrado el bloque hasta nueva suite.

Verificados: H6a historical_overlap.py/test_historical_overlap.py/RESULTADO_SOLAPES.md/solapes_casos.json:392casos,3509solapesciertos+21posibles,15pruebas; sin asignarcapital. broker_adapters.py/test_broker_adapters.py/PLATAFORMAS_BINANCE_XM.md:16pruebas, lectores explícitos Spot/MT5 separados sin transporte ni cuenta. Reserva comisión/base diaria corregidas con10pruebas nuevas;34pruebas conjuntas fills/depth/cash/report pasaron1,632s el28sep. Panel/controlador añaden selección optativa profundidad (legacy sigue por defecto) y modelo solicitado visible:28pruebas28OK4,842s29sep.

Suite29sep:476ejecutadas48,495s,475OK/1fallo de diagnóstico test_migracion_tarifa_nula_idempotente: esperaba Comisión antes de falta de solicitud; se corrige orden de validación, no se elimina protección. pandas cargó correctamente: no reprodujo anterior bloqueo DLL/AppControl. No BD operativa modificada ni sesión nueva. ErroresHTTP yotros de mocks son esperados.

Claude53/54 revisó contrato el28sep; no ejecutó archivos. Chat existente se recuperó29sep, pero nuevo envío de revisión numérica fue RECHAZADO por auto-review por transferencia de detalles internos aClaude; no enviado, no reintentar indirectamente. Se continúa trabajo local. No afirmar colaboración nueva ni saldoClaude conocido.

PRÓXIMO EXACTO: cerrar fixcantidad/feeDecimal yexponentecero, nuevaspruebas+suitecompleta. En paralelo bloques acotados doctor(sólolectura,estado/dependencias/cooldown) y motorH6b de cartera compartida con escenarios explícitos, sin generar aúncartera histórica ni tocar controlesoperativos. Después documentarcomandos/limitaciones y pendientesconcretos. No repetirH5h/H6a ni downloads; historialprevio abajo.

## Instrucción vigente — seguimiento ELIMINADO; cierre completado

24-09-2026: usuario pidió eliminar el seguimiento5h, NO pausarlo. Herramienta oficial confirmó deleteStatus=deleted para retomar-trading-ai-desde-checkpoint. Cierre del seguimiento COMPLETADO; proyecto NO terminado. No recrear automatización ni objetivo continuo, ni programar reanudación automática. ACLARADO por usuario: standby se refería únicamente a la automatización; continuar desarrollo manual hoy mientras haya capacidad. No hay pausa ni pregunta pendiente. No gastar cuota sólo por agotarla; priorizar bloques útiles y compartir diseño/revisión con Claude.

## Último checkpoint — H5h retraso de entrada completado (25-09-2026)

1. Terminado: comparación pareada de entrada+15m sobre mismos392casos/señales, sin recalcular90d ni redescargar. BTC164:41objetivo/123stop antes/después pero2cambios cruzados. ETH228:71objetivo/151stop/6sin salida →75/147/6 con10cambios. Cero excluidos. Señal/ATR/capital/comisión y reglas conservados; nuevo open hipotético y mismo fin absoluto (horizonte menor). Mes/semanaISO/día concilian; no cartera/P&L agregado ni cambio operativo.
2. Archivos: nuevos historical_delay.py, test_historical_delay.py, RESULTADO_RETRASO_15M.md y datasets/20260625_20260923/{BTCUSDT,ETHUSDT}/retraso_15m.json. Actualizados README.md, PLAN_PILOTO.md, CONTINUAR_CON_CLAUDE.md, CHECKPOINTS.md y este índice. Hashes de casos/replay originales intactos; salidas/hashes en informe humano.
3. Pruebas:10nuevasOK6,544s; suite419OK46,236s. Ocho casos retrasados idénticos campo a campo a H5e individual:BTC0/82/108/163,ETH0/10/114/227. Conteos/transiciones de todos los períodos conciliados. Fixture inicialmente sin horizonte corregida con dos velas sintéticas, antes de generación histórica; no fallo pendiente. Errores impresos por suite son mocks esperados. No sesión operativa nueva.
4. Pendientes: cartera compartida/solapes, ejecuciónTestnet/privada, panelHTTP/desbloqueo auditado y costos/fills no calibrados. Claude49/50 revisó contrato y51/52 cierre/próximo paso, no archivos ni ejecución local; corregidas sugerencias suyas incompatibles (diagonal vacía/excluir barrera previa). Última lectura oficial de esta continuación: ordinaryUsageAllowed=true,78% restante5h/24% semanal; reset semanal30sep10:13UTC-5. Lectura puntual, no saldo posterior ni cuotaClaude. No pregunta pendiente; seguimiento ELIMINADO.
5. Siguiente EXACTO: H6a, construir/probar inventario cronológico CONJUNTO BTC/ETH de intervalos y solapes desde casos_episodios.json H5f y hashes externos; no usar H5h como nueva estrategia. Conservar todos los índices, sin adjudicar capital/aceptaciones, priorizar símbolos, inventar orden intravela o sumarP&L. Registrar salidas con tiempo incierto dentro de vela, ambigüedad y casos sin salida al fin; no convertir fin de observación en cierre. Esto prepara cartera compartida sin decidir políticas nuevas. Reusar CONTINUAR_CON_CLAUDE.md y revisiónClaude52; no repetir historia ni revisión inicial ya hecha. Arranque operativo/acceso cuenta siguen reservados al usuario.

## Checkpoint anterior — H5g períodos completados y continuación compacta (25-09-2026)

1. Terminado: desglose de H5f por fecha de SEÑAL UTC en mes/semanaISO/día, ceros y períodos parciales. Ambos activos:4meses calendario intersectados/14semanas/90días; sumas164BTC/228ETH conservadas. No recálculo90d, nueva simulación, redescarga ni modificación de marcos15m/1h/4h. ProtecciónHTTP451 y consulta pública comprobadas en bloque anterior de hoy. Claude47/48 revisó esa protección en el chat existente.
2. Archivos: nuevos historical_periods.py, test_historical_periods.py, RESULTADO_HISTORICO_PERIODOS.md, CONTINUAR_CON_CLAUDE.md y datasets/20260625_20260923/{BTCUSDT,ETHUSDT}/periodos_senales.json. Modificados README.md, PLAN_PILOTO.md y checkpoints; cambiosHTTP en bloque inferior. Originales casos/replay conservados. Huellas de salidas en informe humano.
3. Pruebas:10nuevasOK2,669s; suite completa409OK34,063s. JSONreales generadossin sobrescritura; mes/semana/día concilian totales. Recuento mensual independiente coincide. Errores impresos por suite son mocks esperados. No hay prueba operativa ni integración de órdenes en este bloque.
4. Pendientes: estréslatencia, cartera compartida y transporteTestnet/privado, panelHTTP y desbloqueo auditado. Cowork está visible como opción, NO acceso local verificado. No bloqueo concreto de cuenta. La revisión auxiliar se interrumpió con error de cuota; archivos fueron revisados/probados por la sesión principal. Lectura oficial posterior: ordinaryUsageAllowed=true,98% restante5h/28% semanal; reset semanal30sep10:13UTC-5. No confundir fallo auxiliar con bloqueo global ni afirmar saldoClaude. Seguimiento5h ELIMINADO; no hay vigilancia automática ni pregunta pendiente.
5. Siguiente EXACTO: estrés de entrada+una vela15m sobre mismos casos/señales, conservar ATR/capital/comisión originales, registrar falta de cobertura sin truncar, comparar transiciones y períodos sin sumaP&L. Usar informes/H4guardados y hashes externos de RESULTADO_HISTORICO_CASOS.md; no rehacer historia ni inventar estrategia. Retomar con CONTINUAR_CON_CLAUDE.md, sólo archivos necesarios, revisión breve Claude antes de implementar si aporta valor; no duplicar trabajo. Arranque de programa/acceso a cuenta siguen reservados al usuario.

## Checkpoint anterior — protección HTTP451 verificada (25-09-2026)

1. Terminado: HTTP451 detiene el cliente público y persiste bloqueo sin vencimiento automático, incluso con Retry-After. Se conserva el cliente de host único; no evasión. Consulta puntual de hora pública Binance desde PC OK (serverTime1790342372623); no demuestra acceso privado. Usuario aclaró: preocupación originada en video, no error de cuenta comprobado.
2. Archivos: market_http.py y test_market_data.py modificados; CONEXION_BINANCE.md creado. Sin cambios a estrategia, riesgo, cuenta o sesiones. Claude revisó contrato de este cambio en el chat existente (mensajes47/48); Cowork visible como opción del proyecto, acceso a carpeta local no verificado.
3. Pruebas: test_market_data,24 pruebasOK3,307s, respuestas simuladas/archivos temporales. Dos pruebas nuevas incluyen persistencia, reloj avanzado, cliente nuevo, ausencia de reintento, cierre de respuesta y bloqueo no acortado por429 posterior. Suite completa aún pendiente para cierre conjunto del siguiente bloque. Consulta oficial actual: uso permitido90% restante5h y42% semanal al comienzo; no extrapolarlo como saldo vigente después.
4. Pendientes: panel específico de bloqueo y desbloqueo manual auditado, sin implementarlos ni borrar cooldown; conexión privada/Testnet siguen pendientes. Seguimiento5h ELIMINADO. No pregunta pendiente tras aclaración del video. Desglose histórico mes/semana/día iniciado, todavía no declarado completado.
5. Siguiente EXACTO: terminar y probar historical_periods.py sobre informes H5f existentes; agrupar por fecha de SEÑAL UTC, con períodos parciales y sin casos, sin sumar P&L ni llamarlo rendimiento mensual. Después retomar estrés de entrada+una vela15m conservando señal/ATR/costos, registrar falta de cobertura, comparar frecuencias por períodos. No recalcular90d ni redescargar; no cambiar marcos operativos15m/1h/4h.

## Checkpoint anterior — H5f lotes y diagnóstico90d completados (24-09-2026)

1. Terminado: adaptador historical_batch valida replay H4 ya calculado (hash externo, filas/manifiesto/código, símbolo, malla, ventanas/cierres/precios, coherencia de indicadores/contadores). Reutiliza lógica H5c/e con helpers internos, sin recalcular todos los indicadores. CLI historical_batch_report exige parámetros explícitos y no sobrescribe. Evaluación de primera señal por episodio: BTC164casos41objetivo/123stop; ETH228casos71objetivo/151stop/6sin salida. No ambigüedades en casos seleccionados; fixtures previos sí las cubren. No cartera ni sumaP&L/ROI.
2. Archivos: nuevos historical_batch.py, test_historical_batch.py, historical_batch_report.py, test_historical_batch_report.py, RESULTADO_HISTORICO_CASOS.md; helpers extraídos en historical_case.py/historical_proposal.py; README/PLAN_PILOTO/índice/histórico actualizados. Generados datasets/20260625_20260923/{BTCUSDT,ETHUSDT}/casos_episodios.json sin sobrescritura. Código operativo/config sin cambios. Claude colaboró en contrato/matriz (mensajes43/44) y revisión de resultados (45/46); no acceso suyo a archivos ni ejecución local.
3. Pruebas:33 integraciónOK4,979s;4informeOK1,115s; suite397OK29,523s. Comprobadas17.280filas de replay sin volver a calcularlo. Igualdad exacta H5e individual en9casos de los datos existentes:BTC0/7/82/163 yETH0/10/114/222/227, incluyendo sin salida. Huellas de casos verificadas; hashes completos de informes en RESULTADO_HISTORICO_CASOS.md. Conciliación sólo lecturaOK100/P&L0/trades0/eventos11. Errores de suite son mocks esperados. Consulta oficial de comienzo permitió uso con73% ventana5h/55% semanal restante: no límite confirmado, no comprar/canjear. Claude respondió a ambas consultas, sin conocer cuota restante exacta.
4. Límites: entrada hipotética en apertura15m simultánea, sin latencia/deslizamiento;100 capital independiente/caso y0,1%comisión son parámetros PAPER existentes, no evidencia de fills/tarifa/capital agregado. Selección de episodios es diagnóstico, no reentrada operativa. Predominan stops: alerta que no equivale por sí sola a rendimiento de cuenta/futuro. Falta cartera con capital/riesgo compartidos y validación de ejecución. Hashes no prueban autenticidad ni recalculan todos los indicadores; valores esperados se fijaron tras inspección local. No pregunta pendiente. Seguimiento ELIMINADO, aclarado que standby sólo era automatización; desarrollo manual permitido, sin objetivo continuo.
5. Siguiente EXACTO: evaluar sensibilidad del MISMO diagnóstico a retraso explícito de entrada (una vela15m como escenario de estrés, no latencia real estimada) conservando señal original y costos/reglas, usando H4/casos guardados sin redescargas. Registrar casos sin cobertura en lugar de truncarlos y comparar transiciones sin sumaP&L de cartera. No calibrar umbrales para maquillar muestra. Deslizamiento requerirá hipótesis separadas explícitas, sin afirmar calibración empírica. Recomendación de Claude46 aceptada como próximo estudio técnico, no autorización operativa. No recrear automatización ni objetivo.

## Objetivo y decisiones

23-09-2026 tarde: usuario fuera de PC hasta mañana08:00; puede responder desde Work/casa. Continuar trabajo técnico seguro; solicitar intervención sólo si necesaria. No considerar su disponibilidad remota autorización genérica de dinero, claves, login o sesión operativa.

23-09-2026: meta de piloto en un máximo aproximado de dos semanas (7oct2026), plan en PLAN_PILOTO.md. Explicar diferencias entre historia, PAPER, Testnet y real antes de cambios importantes. Fecha es objetivo técnico, no autorización de fondos ni garantía; pruebas y monitoreo siguen necesarios tras lanzamiento.

### Decisión vigente del usuario — 22-09-2026

AUTORIZADO: desarrollar y probar una versión autónoma PAPER por reglas, sin revisión Claude por operación. Reutilizar estrategia y límites existentes; Claude/Codex quedan para desarrollo, auditoría y explicación. El modo asistido anterior se conserva separado. No contratar API ni inventar confianza, estrategia, capital o límites nuevos. La pregunta sobre quitar revisión IA en PAPER quedó respondida afirmativamente; no tratarla como bloqueo pendiente.

RESERVADO AL USUARIO: empezar el programa/sesión operativa, iniciar sesión Binance y cualquier paso importante de acceso o dinero. Dejar la PC encendida permite desarrollo y seguimiento, NO autoriza iniciar trading mientras duerme. La prueba PAPER30min terminó; no hay sesión operativa vigente; no hay permisos de dinero real, retiros, nuevas claves o servicios de pago. No canjear resets.

Objetivo final: programa autónomo con fondos reales día/noche, observación y aprendizaje del usuario. PAPER es fase de prueba, no se redefine como objetivo final. La integración de extremo a extremo está verificada con fixtures; la interfaz y la observación30min con mercado actual están verificadas; faltan validación de estrategia y puertas testnet/protección. No prometer fecha ni rentabilidad; operar más tiempo no garantiza ganancias.

El millón es aspiración. USD100 es saldo inicial PAPER, no capital perpetuo. Reinversión/aportes/retiros futuros no autorizan ajustes discrecionales. Antes de real deben definirse capital y pérdida máxima, validar integración/protección/requisitos y obtener autorización específica. Iniciar sesión web no conecta por sí solo el programa a fondos.

Sesiones actuales máximo ocho horas; no ampliar a 24/7 ni reiniciar automáticamente por la intención futura. Por defecto permanece modo manual; --auto-paper sigue consumiendo revisiones Claude recibidas, --reglas-paper es optativo y separado. La API Claude sigue aplazada (decisión20-09-2026). Para desarrollo, usar el chat existente y revisiones breves; no puede calcularse saldo exacto de tokens Claude con los datos disponibles. Consultar uso oficial de Codex sin comprar/canjear.

Histórico de aclaraciones, conteos de pruebas y decisiones anteriores: CHECKPOINTS.md; las recomendaciones que figuraban como no autorizadas quedaron sustituidas por esta decisión expresa.

## Completado y verificado

- Entorno Windows/Python existente conservado en `C:\Users\tatop\trading-ai`.
- Datos públicos Binance sin API key, análisis 15m/1h/4h con velas cerradas y rechazo de datos obsoletos.
- Propuestas inmutables con ID/hash/caducidad, transacciones SQLite y protección ante duplicados.
- Límites por operación, capital, número de posiciones y pérdidas del día; seguimiento/cierre PAPER con comisiones estimadas.
- Aportes/retiros simulados separados de P&L; tamaño basado en saldo actual.
- Escáner periódico y monitor independiente, bloqueo de segunda instancia, señal de detención, registros y archivo de estado.
- 17 pruebas locales aisladas aprobadas el 20-09-2026. Incluyen cierre atómico, concurrencia, caducidad, sesión automática que vence durante la cotización, precio fuera de tolerancia y límites de riesgo.
- Ciclo público 20-09-2026 16:31 UTC: 5 símbolos, 0 errores, 0 aperturas. Todos quedaron ESPERAR.
- Prueba real de proceso continuo en segundo plano: inicio MANUAL, latido ACTIVO observado, señal de detención aceptada y estado final DETENIDO a las 16:33:04 UTC; último escaneo 5 símbolos, 0 errores. Se dejó detenido, no operando desatendidamente. `DETENER_RUNNER` permanece hasta un inicio explícito con `--reanudar`.
- Intercambio real con el chat existente de Claude completado: solicitud `ca7300c51f5b4fd39997b528b6b9cab3`, símbolo GUSDT, prueba NO ejecutable; respuesta RECHAZAR con confianza entera 95, importada y persistida como RECHAZADA. Saldo PAPER 100, P&L 0, ninguna operación.

## Incidente corregido

Claude había devuelto confianza decimal 0.92 en la primera prueba. No se aceptó ni se convirtió silenciosamente. La instrucción ahora exige entero 0–100 y tiene prueba de rechazo para decimales. La solicitud histórica `e6b0084e93a749279e5f6b38ecfbeea2` ya tiene estado CADUCADA; el validador impide consumirla.

## Pendientes y dependencias

1. Prueba PAPER30min COMPLETADA, fin automático y conciliación verificados. No repetir ni relanzar por seguimiento. Objetivo eliminado; seguimiento5h eliminado posteriormente; ver instrucción vigente. Contrato en CONTRATO_CONTROLES_PAPER.md.
2. Continuar observación PAPER y pruebas de estrategia fuera de muestra. El éxito de software no valida rentabilidad. No forzar entradas cuando el sistema decide ESPERAR.
3. Implementar y probar adaptador Spot Testnet separado, filtros, precisión, reconciliación de fills, órdenes protectoras y recuperación tras fallos/reinicios. El simulador local actual NO es testnet.
4. Antes de real: auditoría independiente, validación de estrategia/costos, disponibilidad legal/contractual y autorización específica. No basta cambiar URL y claves.

## Archivos de referencia

- `README.md`: uso operativo y limitaciones.
- `config.py`: parámetros PAPER y rutas.
- `paper_store.py`: validación y persistencia transaccional.
- `system_runner.py`: ciclo y detención.
- `claude_bridge.py`, `claude_authorizer.py`: intercambio estricto.
- `trading.db`: cuenta, solicitudes, operaciones y eventos; conservar.
- `solicitudes/`: paquetes exportados; `respuestas/claude_prueba_20260920.json`: evidencia importada.
- `test_paper_system.py`: pruebas aisladas.
- `backups/antes_automatizador_20260919_195638`: respaldo previo; conservar.
- Claude: https://claude.ai/chat/b8efcffd-d59d-414f-b7ac-480a62a55d77 dentro del proyecto existente.

## Riesgos y límites vigentes

El monitor solo observa mientras la PC y el proceso estén activos; parar no cierra posiciones. El precio observado cada 60 s puede saltar stops. Las comisiones son supuestos. No hay notificaciones externas, API Claude automática, órdenes testnet ni reales. No confundir una confianza subjetiva de Claude con probabilidad estadística de beneficio.
