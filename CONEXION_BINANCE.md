# Conexión prevista con Binance — 25-09-2026

## Respuesta corta

Binance dispone de API Spot oficial: el programa podrá comunicarse directamente con ella, sin automatizar clics de su web ni consultar a Claude por cada operación. Esto es una posibilidad técnica, no confirmación de acceso privado o elegibilidad de una cuenta concreta.

Hoy está implementado el cliente de datos públicos. Una consulta local a `/api/v3/time` respondió correctamente el 25-09-2026 (`serverTime=1790342372623`). No prueba permisos de órdenes, acceso a la cuenta ni disponibilidad permanente. El usuario aclaró que el posible bloqueo provenía de un video de Instagram, no de un error observado en su cuenta.

El envío y la conciliación real de órdenes siguen pendientes de integrar: los módulos `execution_*` actuales validan fixtures offline y no disponen de transporte operativo. Iniciar sesión en la web no conecta automáticamente el programa.

## Tratamiento de restricciones

| Situación | Comportamiento actual del cliente público |
| --- | --- |
| HTTP 429 / 418 | Detiene consultas y conserva la espera indicada en Retry-After; sin plazo válido requiere revisión. No rota IP ni claves. |
| HTTP 403 | Conserva el bloqueo; no presupone que sea un CAPTCHA ni lo intenta resolver. |
| HTTP 451 | Bloqueo persistente sin vencimiento automático, incluso con Retry-After; requiere revisión de la restricción. |
| Timeout / conexión / 5xx en GET público | Máximo un reintento adicional. Esto NO se puede trasladar al envío de órdenes. |
| Respuesta incierta a una orden futura | Deberá conciliarse por ID antes de decidir; no asumir fracaso ni reenviar a ciegas. Todavía no existe ese transporte. |

El bloqueo abarca el cliente público de host único `data-api.binance.vision`; alcanza scanner, análisis y descargas que lo usan. No se añadieron proxies, VPN, hosts alternativos ni mecanismos para eludir restricciones de cuenta, seguridad o región.

La revisión breve de Claude (mensajes 47/48 del chat existente) propuso registrar origen, mostrar bloqueo en salud y auditar el desbloqueo manual. Son pendientes: no hay procedimiento nuevo de desbloqueo en este bloque. El estado de salud actual informa errores de componente, pero no un panel específico de restricción HTTP. No guardar cuerpos/cabeceras completos sin un diseño de minimización de datos.

## Reparto de trabajo

- Programa Python: reglas, consulta de datos, controles, ejecución cuando exista integración validada, registros e interfaz.
- Codex y Claude: desarrollo, revisión y pruebas; el modo autónomo por reglas no necesita una llamada IA por operación.
- Chat existente: `03 — SISTEMA OPERATIVO Y AUTOMATIZACIÓN`; se reutilizó, sin crear otra tarea.
- El proyecto Claude muestra la opción Cowork. No se verificó que tenga conectada la carpeta local ni se cambió ningún permiso; no asumir acceso compartido o Codex dentro de Cowork.
- El seguimiento programado de cinco horas permanece eliminado.

## Fuentes consultadas

- [API Spot, seguridad, límites y respuestas HTTP de Binance](https://developers.binance.com/en/docs/products/spot/rest-api).
- [HTTP 451: significado estándar, RFC 7725](https://www.rfc-editor.org/rfc/rfc7725.html).
- [Cowork: acceso local mediante Claude Desktop](https://support.claude.com/en/articles/13345190-get-started-with-claude-cowork).

No se atribuye una causa concreta a un error inexistente ni se garantiza ausencia de restricciones futuras.
