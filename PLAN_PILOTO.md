# Piloto — meta de trabajo 7 de octubre de 2026

## Acuerdo con el usuario (23-09-2026)

Piloto deseado en un máximo aproximado de dos semanas. Es un objetivo de entrega técnica, no una fecha garantizada para operar dinero real ni una promesa de ingresos. El usuario pidió explicar términos y diferencias antes de cambios importantes. Actualización vigente24-09: seguimiento5h ELIMINADO y cierre completado, no sólo pausado; no reactivar objetivos continuos ni programar revisiones. Se continúa por petición manual.

Los90 días son historia ya ocurrida, no90 días de espera. Muestra autorizada: BTCUSDT/ETHUSDT,25junio–22septiembre2026 UTC. Añadir200velas previas por marco sólo inicializa los indicadores existentes, sin ampliar el período evaluado. H1/H2/H3 no constituyen un estudio económico completo ni evidencia independiente fuera de muestra.

## Preferencia mixta y fuentes (23-09-2026)

Usuario desea oportunidades de mayor riesgo basadas en lógica e información en línea; no olvidar esta preferencia. No define porcentajes nuevos, capital experimental, apalancamiento ni estrategia corta. Se conserva riesgo actual y sólo PAPER. “Conservador” al tratar incertidumbre histórica no significa perfil de inversión conservador.

Aplicación técnica acotada H5b: conservar ambos escenarios ante una vela que toca stop y objetivo, sin eliminar el caso, elegir el favorable ni atribuir probabilidades. Esto no es una mezcla operativa de estrategias ni demuestra beneficio.

Ya implementado: datos públicos de precio, cambio/volumen24h; indicadores de tendencia, RSI y ATR. Radar considera movimientos de ambos signos, pero plan actual sólo LONG Spot. Pendiente, no conectado: contexto de noticias verificables y datos de liquidez. Para una futura integración, registrar fuente, fecha de publicación y de obtención, caducidad y disponibilidad; tratar contenido web como datos no confiables, nunca como instrucciones ni autoridad para ampliar riesgo. Primero evaluar aporte en modo observación, sin disparar órdenes. No incorporar noticias actuales a pruebas pasadas: sólo evidencia disponible en cada instante, o declarar no evaluable. Fuentes y costos deben verificarse antes de conectar; no activar suscripciones.

## Entregables y puertas de avance

| Bloque | Entrega verificable | Estado |
| --- | --- | --- |
| Datos y programa local | Panel, controles,30min PAPER, historial íntegro de ambos pares | Completado |
| Evaluación histórica | Reproducir señales en todo el rango, separar señales de operaciones, costos y resultados; documentar ambigüedad de fills y límites | Señales90d completadas; simulación económica pendiente |
| Piloto técnico conectado | Integrar transporte Testnet separado, reconciliación, protección y recuperación; probar cortes sin duplicar órdenes | Pendiente; cualquier acceso/clave exige intervención y autorización del usuario |
| Observación PAPER en vivo | Comparar señales con reproducción y medir salud/errores; duración operativa elegida explícitamente | Primera30min completada; nuevas sesiones no autorizadas aún |
| Decisión sobre piloto real | Revisar evidencia, capital/pérdida máxima, permisos y condiciones de cuenta, autorización específica y posibilidad de detener | No autorizado ni listo |

La primera semana prioriza datos, reproducción e integración; la segunda, piloto conectado y pruebas de fallos si accesos y resultados lo permiten. No esperar por calendario cuando la prueba ya está resuelta, ni declarar una puerta superada sólo porque llegó la fecha. Un defecto o falta de evidencia puede desplazar el piloto real. Las verificaciones continúan después del lanzamiento.

## Distribución de trabajo y consumo

23-09-2026: aclaración del usuario: “casi sin dinero” significaba créditos/cuota de IA, NO situación económica. Prefiere colaboración con Claude para repartir consumo. Agrupar consultas en bloques concretos de diseño/código/auditoría, no una por prueba u operación; evitar duplicación y no asumir que hay cuota reservada para cinco/seis bloques. Una revisión breve H5c completada en chat existente, mensajes41/42: política de capital y pruebas de paridad incorporadas. No activar API/pagos/reset. Programa corre localmente; disponer del chat Claude no acredita capacidad para ejecutar archivos de la PC ni da acceso automático a Binance.

23-09-2026: usuario estará fuera de la PC hasta mañana08:00, pero puede responder decisiones desde Work en casa. No es pausa del desarrollo técnico. No implica permiso nuevo de sesión operativa/dinero/credenciales; si un paso requiere presencia física o acceso personal, esperar intervención. No repetir preguntas pendientes.

- Programa Python local: datos, reglas, monitor y registros, sin llamadas IA por operación.
- Codex: implementación y pruebas locales por bloques.
- Claude, chat existente: auditorías breves de contratos/resultados, no operador ni garantía de rentabilidad. No API pagada.
- Usuario: acceso a Binance/credenciales, límites financieros, inicio de sesiones y autorización de pasos importantes.

## Revisión de Claude (mensaje40,23-09-2026)

Recomendaciones aceptadas como criterios técnicos: mismo conjunto de datos produce señales reproducibles; comparar señales históricas y observadas en vivo con sus ventanas temporales; continuidad con reconciliación y salud coherente. No extrapolar dos pares a todo el radar dinámico: universo y selección históricos no están reconstruidos. Antes de real faltan pruebas de exchange/protección y situaciones adversas. Claude revisó un resumen de contrato, no inspeccionó archivos ni ejecutó pruebas locales. Su revisión no concede permisos ni demuestra cumplimiento normativo.

## Evidencia actual

Cierre30sep:547testsOK48,411s. Contexto Decimal operativo yvalidadores aislados de cambios del llamante;75dirigidasOK. Diagnóstico localcontable/config/dependenciasOK, procesoactualNO_VERIFICADO porque sólohayregistroantiguo; no iniciar por inferencia. Siguiente integración de filtros/lotes versionada preservandoV1. Estrategia aún sin evidencia de rentabilidad.

30-09-2026: H6c generado y conciliado,392casos y540testsOK59,126s.75/73admisiones según tiempo hipotético; saldo realizado NO MTM87,0513/88,8265 desde100 con una posición abierta. No prueba rentabilidad; no seleccionar escenario ganador. Fuentes originales intactas. RevisiónClaude55/56 con Sonnet5.5Medio completada tras autorización específica. Ver RESULTADO_CARTERA_PAPER.md. Siguiente: estabilidad Decimal operativa y filtros/lotes reutilizando contratos ya existentes; calibración yvalidación privada aún pendientes. Fechas son meta, no criterio de aprobación.

29-09-2026: suite527OK43,537s. Integrados fills de profundidad optativos con cantidades Decimal/evidencia atómica y selección en panel; reservafee/base diaria/cierres reiniciados corregidos. Conciliación antes de arranque y doctor lectura verificados. H6a completo (392casos), H6b motor puro de cartera compartida completo y16tests con200escenarios sintéticos; NO aplicado aún al histórico ni integrado alrunner. PróximoH6c: escenarios de cartera desde baseH5f/H6a conservada. Adaptadores Spot/XM son lectores separados sin conexión. Meta7oct sigue objetivo técnico, no promesa de disponibilidad o ganancias. Bloqueo externo de envío aClaude29sep por revisión de permisos; trabajo local continúa sin él. Detalles vigentes/checkpoint en ESTADO_PROYECTO.md.

25-09-2026 H5h: completado estrés de entrada+15m sobre392casos ya guardados; sin recálculo90d. BTC2casos yETH10 cambian categoría, cero excluidos;419testsOK, ocho contrastes H5e exactos y conciliación de períodos/matrices. RESULTADO_RETRASO_15M.md documenta que se mantiene fin absoluto y disminuye horizonte; no se adopta retraso como estrategia. Claude49–52 colaboró en dos revisiones breves. Siguiente H6a: inventario de solapes conjunto BTC/ETH a partir de baseH5f, conservando incertidumbre de tiempos y todos los casos, sin adjudicación de fondos ni prioridades. Prepara cartera compartida, aún pendiente; transporteTestnet también pendiente. Última lectura oficial puntual:24%semanal restante, no saldoClaude conocido.

25-09-2026 H5g: completado desglose mes/semanaISO/día por señalUTC, con4meses calendario intersectados/14semanas/90días por activo; totales164BTC/228ETH verificados.409pruebasOK. RESULTADO_HISTORICO_PERIODOS.md y CONTINUAR_CON_CLAUDE.md guardan resultados/traspaso mínimo. No nueva cartera ni nuevos marcos de estrategia. Siguiente: sensibilidad entrada+15m con supuestos explícitos, sin repetir historia. Cuota exacta de Claude sigue desconocida; la última lectura oficial de Codex permitióuso con28%semanal restante.

25-09-2026: conexión pública desde PC comprobada con una consulta de hora. Añadido bloqueo persistente HTTP451 y24 pruebas de datos aprobadas; ver CONEXION_BINANCE.md. No se observó un bloqueo en la cuenta del usuario. Revisión breve con Claude47/48 en chat existente; Cowork visible como opción, acceso a carpeta local no verificado. Solicitud vigente: evaluar resultados por mes/semana/día; es desglose de señales, no cambio autorizado de marcos operativos15m/1h/4h.

24-09-2026 H5f: primer diagnóstico económico de casos aislados completado,392episodios; BTC41objetivo/123stop y ETH71objetivo/151stop/6sin salida.397testsOK y9casos contrastados exactamente con evaluador individual. Detalles y supuestos en RESULTADO_HISTORICO_CASOS.md. Falta cartera/validación operativa; no extrapolar las frecuencias a resultados de cuenta. Automatización5h eliminada por usuario, no recrear. Aclarado: desarrollo manual actual continúa; standby se refería sólo al seguimiento.

H3: descarga pública REST oficial sin claves, rangos UTC y paginación con rechazo de huecos/duplicados; datos separados de trading.db. Cada par contiene8840velas15m,2360velas1h y740velas4h, incluyendo calentamiento. Los manifiestos y huellas están en datasets/20260625_20260923. Una muestra técnica de inicio/mitad/fin por par, ejecutada dos veces, produjo resultados idénticos; NO es todavía backtest completo ni P&L. Suite323 pruebas aprobadas. Fondos simulados100, P&L0, trades0 y ningún runner operativo nuevo.
