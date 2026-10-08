# Controles del panel PAPER — implementación funcional verificada

23-09-2026: UI revisada; identificación Windows venv corregida con PID directo o parent_pid, mismo ID/modo y handle propio vivo. Suite297 OK previa. Reintento autorizado30min de246d5ef0a94b56b1ce0f80212fec77 finalizado automáticamente16:01:56UTC, trabajadores cerrados; dos scanner de5símbolos/0errores/0entradas,30monitor/0errores, conciliaciónOK100/P&L0. No hay sesión vigente. No relanzar por heartbeat; sólo seguimiento5h y objetivo continuo eliminado.
No autoriza iniciar sesiones, conectar Binance, cambiar estrategia/límites ni usar dinero real.

## Inicio explícito

- Duración indicada por usuario, número finito mayor que cero y máximo ocho horas; sin renovación automática.
- Confirmación por cada inicio, explicando que simula por reglas, no consulta IA por operación, la pausa previa se conserva, parar/cerrar no liquida posiciones y apagar deja de vigilar.
- Lanzador con intérprete del entorno y script fijos, argumentos separados y sin shell. No entrada de comandos arbitrarios. Sin servicio ni arranque al iniciar Windows. Ventana de proceso oculta en Windows, registro de errores local.
- Bloqueo de SO del runner es autoridad final de exclusión. Adquirirlo antes de quitar DETENER_RUNNER o iniciar trabajadores. El panel no retira STOP. Un fallo de adquisición no modifica señales.
- Identificador nuevo por intento explícito; el hijo publica ese identificador sólo tras adquirir bloqueo. Estado terminal lo conserva. ID, proceso propio y estado coherente distinguen solicitud/arranque confirmado/terminado. Un PID o ACTIVO histórico no basta; ID por sí solo tampoco demuestra vida o salud.
- Doble clic bloqueado mientras el lanzamiento está pendiente o el hijo sigue vivo. No reintentos automáticos. Comprobar terminación del hijo incluso si nunca publicó estado. Error al crear proceso deja señales intactas.
- Si hay timeout de observación pero el hijo sigue vivo, mostrar NO CONFIRMADO y permitir solicitar parada, NO desbloquear otro inicio ni matar proceso. No inventar timeout financiero ni interpretar demora como muerte. Nuevo intento sólo manual tras terminación confirmada; otro proceso externo sigue protegido por bloqueo del runner.

## Pausa, reanudación y parada

- Pausa: crear PAUSA_ENTRADAS, bloquear nuevas entradas al comprobar controles; mantener monitor. Señal solicitada no es confirmación inmediata y no deshace commits previos.
- Reanudar entradas: confirmación explícita, quitar sólo PAUSA_ENTRADAS. No quitar STOP ni arrancar proceso; no extender duración.
- Parada: crear DETENER_RUNNER, conservar PAUSA_ENTRADAS, no liquidar ni matar trabajadores. Mostrar solicitado hasta observación verificable; cooperativa, no instantánea.
- Implementación R3b.2: además DETENER_SESION_<id> por intento para no perder una parada que llegue mientras el hijo retira STOP. El hijo nunca retira esta señal; se comprueba antes de arranque y en callback/bucle. Cada inicio explícito genera ID nuevo. Fallos de escritura se comunican; se intenta también la otra señal. No borrar señales históricas automáticamente.
- Cerrar panel no detiene el runner; advertencia si hay sesión propia pendiente/activa/no confirmada. Sin reinicio automático del panel o del motor.
- Configuración exclusivamente PAPER; ninguna lectura de claves, permisos de cuenta ni endpoint de órdenes.

## Pruebas previas a cualquier uso

Sólo rutas temporales, launcher falso y red bloqueada. Inicio cancelado, duración inválida/no finita, doble clic, fallo Popen, muerte antes/después bloqueo, estado ausente/antiguo/ID distinto, niño vivo sin estado (sin duplicación), fallo de escritura, pausa/reanudar/stop preservados, cierre del panel y máximo ocho horas. Integrar pruebas de runner/identificador sin lanzar sesiones operativas.

Revisión Claude del contrato (mensaje38 del chat existente): propone timeout y liberar UI si no aparece sesión. Se acepta prueba de muerte durante arranque y publicación de ID tras bloqueo; NO se acepta desbloquear por timeout mientras el hijo pueda seguir vivo. poll/terminación confirmada y bloqueo SO siguen obligatorios. Claude no vio archivos ni ejecutó pruebas; no es auditoría de implementación.
