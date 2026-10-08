# Project & Agent Mission Control

Actualizado 05-10-2026. Versión funcional en Notion, no nueva aplicación ni panel de trading.
Fuente técnica: GitHub. Notion muestra coordinación. Claude es el centro visible solicitado por el usuario;
las acciones reales dependen de la plataforma de cada tarea. No presentar un chat de Work como acceso al PC
o ejecución en Claude si no se verificó. No cambiar de proveedor/modelo por renombrar un registro.

## Registro único (no crear duplicados)

Operations Center: https://app.notion.com/p/3f002a0ff45f81c58fecc00ba9221812

| Área | Database ID | Data source ID |
|---|---|---|
| PROJECTS | bf818e4df9f94527a1b0f3a72faa10f5 | d28411d2-52a7-40eb-9399-01b292ffaad1 |
| AGENTS | 0d3c9e03a8c64844849327bc63224cc3 | 6e582d5e-356f-49fd-9cd1-006f58a189c7 |
| TASKS (Task Board) | 5ceac86891214d78928f1f7cf01f5d58 | 1d95ed11-81f8-457d-a97e-4fb3d07912ef |
| RUNS | 1eb17538d3664613a9f8d4dafd689238 | 1bc17566-cb99-4d5c-b78f-ee63bee1e60c |
| CHECKPOINTS | 15f18ec964ed4f258d9fabedae1621a9 | 0de02a90-ff59-42e7-a49e-91ab82327216 |
| DECISIONS | 56b80daad1b749a0a3093296d67f58da | ce325b2a-e3ad-4fec-aa7a-a1f8d178e9f0 |
| BLOCKERS | ad139f480e66431e9b80ba77a3d7da59 | 2f3c4343-57af-4a7a-a3f1-7500c5a80c83 |
| METRICS | 8394d8a915fb46cc918ca00838e3c777 | 8cf786f3-4f46-417d-a1a6-21d81cab7821 |

Proyecto TRADING: `3f002a0f-f45f-81df-b0cd-ca10bce1d463`.
Agente Codex: `3f002a0f-f45f-8175-9959-efcf04c56409`.
Agente Trading Claude Work: `3f002a0f-f45f-81f0-b497-efce8b7551d4`.
Auxiliar publicación (terminó con límite, sin reintento): `3f002a0f-f45f-8168-9b20-dd74670622d8`.
Run importación/Mission Control: `3f002a0f-f45f-81bf-a288-de15128bc70b`.
Bloqueo técnico CI (no pregunta humana): `3f002a0f-f45f-81e9-90e0-d01911353633`.
Tarea upload existente: `3f002a0f-f45f-8104-947f-e58e0b23a4ff`.

## Estados y evidencia

WORKING = turno/proceso verificado activo; REVIEW = revisión pendiente o activa (aclarar cuál);
WAITING_FOR_USER = depende de una respuesta personal; BLOCKED = impedimento técnico;
IDLE = sin tarea activa; DONE = criterio del bloque cumplido; ERROR = fallo observado.
Mostrar fecha de observación. Al acabar una sesión, no dejar WORKING por inercia.
No hay streaming ni garantía de actividad continua: el seguimiento local necesita equipo/app disponibles.
No inventar porcentajes de avance, cuotas de Claude ni hora exacta del siguiente disparo no expuesta por el scheduler.

## Cada ciclo (un único heartbeat cada ocho horas)

1. Leer AGENTS, coordinación, checkpoint, cambios/PR/Issues y estado de la otra tarea.
2. Leer Notion, reutilizar bloqueos/preguntas existentes, reclamar archivos sin solapar.
3. Ejecutar un bloque útil con pruebas proporcionales; no generar investigaciones redundantes.
4. Publicar evidencia y solicitar revisión acotada cuando aporte valor; no integrar hasta resolver hallazgos.
5. Actualizar RUNS, AGENTS, PROJECTS, tareas, checkpoint y métricas con fuente y límites.
6. Terminar con estado fiel y próximo paso. Notificar solo intervención, riesgo importante, hito o revisión final.

Automatización única: `trading-intelligence-continuidad-cada-8-horas`.
No se crea otro objetivo continuo, agenda ni agente de Notion de adorno. Los registros son coordinación, no
agentes nuevos contratados. Agentes especializados solo si INPUT/RESPONSABILIDAD/OUTPUT/CRITERIO DE FIN aportan valor.

## Preguntas: exactamente un WAITING_FOR_USER

Antes de preguntar, buscar registro por decisión bloqueada. Crear un ID estable con pregunta exacta,
autor, fecha, qué bloquea y qué sigue independientemente. En próximos ciclos no volver a preguntar ni
reinvestigar mientras el contexto siga igual. Al responder usuario, registrar respuesta/decisión y resolver.
Si todo el trabajo requiere esa respuesta o el usuario pausa, pausar seguimiento hasta respuesta explícita.
Existe WAIT-CLAUDE-CODE-001: instalación CLI preguntada por Trading Claude Work, página
`3f002a0f-f45f-81b9-8304-fc0b70089f93`. Solo afecta ese flujo; no repetir ni pausar trabajo independiente.
No pedir claves Binance/MT5 como requisito de pruebas públicas/offline.

## Límites de esta fase

Solo PAPER. Sin cuentas, credenciales nuevas, operaciones reales o cambios de capital. No hay estrategia validada;
el diagnóstico histórico negativo se conserva. Configuración CI preparada no implica CI aprobado. Las métricas
de tests no son métricas de rentabilidad. No lanzar sesiones operativas por un heartbeat de desarrollo.
