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

## Lectura firmada de la cuenta (H1, 08-10-2026)

`binance_signed.py` es un cliente firmado de **solo lectura** contra `api.binance.com`, escrito solo con biblioteca estándar. Las pruebas (`test_binance_signed.py`) son offline con un transporte falso; **todavía no se ha ejecutado contra una cuenta real**.

- Solo emite GET a una lista cerrada: restricciones de la clave, cuenta/saldos, órdenes abiertas y trades propios. No contiene envío de órdenes, retiros ni transferencias, y no hay opción para añadirlos.
- Guardia de permisos fail-closed: antes de leer la cuenta consulta `/sapi/v1/account/apiRestrictions`. Se niega si la clave tiene retiros, trading, transferencias, margen, futuros o cualquier otro permiso activo, o si no puede determinarlo.
- 429/418/403/451: mismo criterio que la tabla anterior, con su propio archivo local `binance_signed_cooldown.json` (no se versiona). Un bloqueo sin plazo exige que el dueño lo revise y borre ese archivo.
- Solo admite claves HMAC. La clave y el secreto se leen de `BINANCE_READONLY_API_KEY` y `BINANCE_READONLY_SECRET_KEY`; ningún mensaje, log o excepción contiene su valor ni la firma.
- No usa proxies del entorno ni sigue redirecciones.

Pasos del dueño (ningún agente ve las claves):

1. En Binance, crear una clave de tipo HMAC con **solo "Enable Reading"**, sin trading ni retiros, y con restricción de IP.
2. Inicio → "Editar las variables de entorno de esta cuenta" → crear las dos variables anteriores. No pegarlas en ningún chat.
3. Abrir una terminal nueva en la carpeta del proyecto y ejecutar `python binance_signed.py`.

La salida muestra únicamente: conectado sí/no, permisos de la clave (lectura, trading, retiros, restricción de IP) y el número de activos con saldo.

## Órdenes solo en Spot Testnet (H2, 08-10-2026)

`binance_testnet_orders.py` es transporte de órdenes hacia `testnet.binance.vision` (dinero ficticio). Las pruebas son offline; **todavía no se ha enviado nada a Testnet**. No está conectado al runner PAPER ni al Risk Engine.

- Cualquier otro host lanza un error antes de tocar la red y no existe opción para cambiarlo.
- Cada intento se anota en `binance_testnet_journal.json` (local, no se versiona) antes del único POST. Una orden nunca se reenvía y su `newClientOrderId` no se reutiliza en ningún estado.
- Timeout, corte, 5xx, restricción HTTP o respuesta ilegible dejan la orden como `INCIERTA`. Se resuelve con `conciliar()`, que consulta por `newClientOrderId`; mientras quede una sin conciliar no se envía otra, también tras reiniciar.
- "La orden no existe" solo se acepta como definitivo pasados 10 s desde el intento.
- Un bloqueo de archivo (`binance_testnet_journal.json.lock`) hace que comprobar y anotar un intento sea una sola operación entre procesos e hilos: dos instancias que compartan el diario no pueden enviar a la vez, y guardar un resultado nunca pisa lo que otro proceso escribió.
- Claves: `BINANCE_TESTNET_API_KEY` y `BINANCE_TESTNET_SECRET_KEY`, creadas en testnet.binance.vision. `python binance_testnet_orders.py` comprueba la conexión sin enviar órdenes.

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
