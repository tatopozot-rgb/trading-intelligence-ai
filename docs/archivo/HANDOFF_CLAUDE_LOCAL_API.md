# Handoff de Claude Code local a Claude Leader: capa de API (Binance / XM)

Escrito el 2026-10-08. Rama `claude-code/api-session-readonly`, creada desde
`claude-code/finding-3-persistent-halt`. Prompt de origen:
`docs/prompts/CLAUDE_LOCAL_API_SESSION.md` (rama por defecto).

No se ha hecho ninguna llamada autenticada a Binance ni a MT5. Ningún agente ha
visto una clave. PAPER sigue siendo el único modo; nada de esto autoriza LIVE.

## DONE (código y pruebas offline)

| Hito | Archivo | Pruebas | Mutantes eliminados |
|---|---|---|---|
| H1 lectura firmada de Binance | `binance_signed.py` | `test_binance_signed.py`, 26 | 25 de 25 |
| H2 órdenes solo en Spot Testnet | `binance_testnet_orders.py` | `test_binance_testnet_orders.py`, 25 | 34 de 34, más 9 de 9 del bloqueo |
| H3 XM/MT5 demo, solo lectura | `xm_mt5_readonly.py` | `test_xm_mt5_readonly.py`, 10 | 19 de 19 |

- `python -B tools/check_repository.py`: 0 hallazgos.
- Suite raíz completa en este PC: 429 pruebas, 43 errores, todos en módulos ya
  existentes que importan pandas ("Una directiva de Control de aplicaciones bloqueó
  este archivo"). Ninguno en los archivos de esta rama. No se ejecutó mypy (no
  está instalado aquí).
- Comprobado sin credenciales: `api.binance.com/api/v3/time` responde 200 desde
  este PC y el reloj local va unos 1,1 s por detrás del servidor, dentro de
  `recvWindow` = 5000 ms.

## Actualización tras la revisión de cloud del PR #9 (comentario 6055699215)

| Punto de la revisión | Estado |
|---|---|
| 1a. Watchdog: `ultimo_ok IS NULL` como hueco infinito | Corregido en `7283edc` |
| 1b. `_abrir_validado` revertía la valoración válida al rechazar la orden | Corregido en `7283edc` (savepoint; la orden rechazada se revierte entera y después se confirma la valoración) |
| 2. Falta el fix de #5 (`is_junction`) | Incluido por merge de `7921038` |
| 3. Conflictos de documentos con la rama por defecto | Resueltos: se conservan las versiones de la rama por defecto; las locales quedan en `docs/history/` |
| 4. Descripción del PR desactualizada | Pendiente: este PC no tiene `gh`; texto propuesto al final de este archivo |

Pruebas en este PC tras el merge:

- `test_paper_halt`: 34 OK (26 previas + 8 nuevas). 8 mutantes sobre los dos arreglos: 7 eliminados; el
  superviviente es redundante (la fila inicial sin latido la rellena el mismo `inicializar()`).
- `reviews/gpt_work/test_watchdog_review.py` (sin cambios, commit `c21300c`): 8/8 OK; antes 4/8.
- `test_binance_signed`, `test_binance_testnet_orders`, `test_xm_mt5_readonly`: 57 OK.
- Cada módulo `test_*.py` raíz ejecutado en su propio proceso da el mismo resultado antes y después de
  los arreglos, salvo `test_paper_halt` (26 -> 34). Para importar los módulos que dependen de pandas se
  usó un sustituto vacío de pandas, porque Smart App Control bloquea sus DLL; 13 módulos que usan pandas
  de verdad fallan igual antes y después. **No ejecutado aquí:** `tests/` de `trading_intelligence`
  (pandas real), mypy, ni el `check_repository.py` en Linux.

## Binance Spot conectado desde Claude Code local (2026-10-08, ruta B)

El dueño confirmó la ruta B directamente en la sesión local y guardó él mismo la clave de trading
en variables de entorno de usuario de Windows (`BINANCE_TRADE_API_KEY`, `BINANCE_TRADE_SECRET_KEY`).
Ningún agente vio sus valores.

| Paso de `docs/prompts/CLAUDE_LOCAL_LIVE_OPERATOR.md` | Resultado |
|---|---|
| 1. Python con pandas | PASS sin WSL: entorno aparte con pandas 2.2.3, numpy 2.2.6 y scipy 1.18.1 (Smart App Control los permite; pandas 3.0.6 sigue bloqueado). `tests/test_live_operator.py`: 32 passed en `feccf8b`. |
| 2. Clave de trading | PASS. Lectura firmada de `/sapi/v1/account/apiRestrictions` con el cliente del operador (`SpotTrader.verify_key`, sin modificar): lectura SI, Spot trading SI, retiros NO, restricción de IP SI. También respondió `/api/v3/account`. |
| 3. SHADOW | PASS: 3 iteraciones, exit 0, en 1h (`b69892a`) y en 4h por defecto (`c6bcba7`); sin posiciones ni decisiones en ese intervalo. |

- **No se envió ninguna orden.** Solo lecturas firmadas. El operador real no se ha arrancado.
- Un primer intento con una clave anterior falló con HTTP 400, código -1022 (firma no válida);
  el dueño creó otra clave y esa conectó.
- La sesión local arrancó antes de que existieran las variables, así que no están en su entorno
  de proceso: el operador real debe lanzarse desde una terminal nueva.
- Los saldos de la cuenta no se registran en este repositorio.
- Sigue en pie: nada con `--real` sin una frase explícita del dueño con el capital; solo 4h; y el
  resultado de la sección 45 (ninguna configuración pasa el criterio GO) se le recuerda antes.

## Revisión de GPT Work sobre `3ec14f5` (comentario 6059998935)

Hallazgo aceptado: en H2 la secuencia leer diario -> comprobar -> anotar -> POST no era atómica entre
procesos; dos instancias con el mismo diario podían enviar a la vez y una podía borrar el registro
de la otra. Corregido con un bloqueo de archivo de un único escritor (`Diario.exclusivo`) que cubre
la reserva del intento, el guardado del resultado (sobre el diario releído) y las escrituras de
`conciliar()`, que además no degrada un resultado definitivo anotado por otro proceso.

`test_binance_testnet_orders.py`: 25 OK (21 + 4 nuevas, incluida una carrera determinista de dos
instancias). 9 de 9 mutantes del bloqueo eliminados. Sigue siendo solo Testnet y sin ejecutar
contra el servicio. Respuesta en el PR pendiente: este PC no puede publicar comentarios (sin `gh`).

## Verificador de GPT Work

Para la primera consulta firmada de permisos se usa, sin cambios, el verificador
de GPT Work (`reviews/gpt_work/binance_connect/readonly_permissions.py`, PR #8,
commit `c21300c`). Se extrajo con `git show` a
`C:\Users\tatop\trading-intelligence-work\gpt_work_binance_connect\` (fuera del
repo; mismos hashes de blob) y sus 6 pruebas offline pasan en este PC.

Solapamiento a decidir por Leader: la guardia de H1 (`evaluar_restricciones`) se
escribió antes de recibir la instrucción de reutilizar ese verificador y cubre
lo mismo. Diferencia de criterio: GPT Work exige los 11 permisos documentados
como booleanos y rechaza cualquier campo desconocido; H1 exige retiros, trading,
lectura y restricción de IP, y rechaza cualquier `enable*`/`permits*` activo o
no booleano. Ambas fallan cerrado.

## BLOCKED: WAITING_FOR_USER

1. Primera consulta de permisos de la clave nueva. La ejecuta el dueño en una
   PowerShell propia: `python -B readonly_permissions.py` en la carpeta anterior.
   Pide clave y secreto ocultos, hace un único GET y no guarda nada. Tipo de
   clave sin confirmar: no hay ninguna variable `BINANCE_*` definida en el PC.
2. H4 (lectura de cuenta con `python binance_signed.py`): requiere
   `BINANCE_READONLY_API_KEY` y `BINANCE_READONLY_SECRET_KEY`.
3. Prueba real de H2: requiere `BINANCE_TESTNET_API_KEY` y
   `BINANCE_TESTNET_SECRET_KEY`.
4. Prueba real de H3: el paquete `MetaTrader5` no está instalado y no se intentó
   instalar (Smart App Control ya bloqueó otras DLL). Requiere además la terminal
   MT5 abierta con una cuenta demo.
5. El PR #9 ya existe contra la rama por defecto; falta actualizar su descripción (ver abajo).

## Límites conocidos

- H2 es solo transporte: no está conectado al runner PAPER ni al Risk Engine, no
  redondea a los filtros del exchange y no cancela órdenes.
- Tras un 429/418/403/451 en el POST la orden queda `INCIERTA` y hay que esperar
  al fin del bloqueo para conciliar.
- H3 comprueba que la cuenta sea DEMO por `trade_mode == 0`; contra una terminal
  real no se ha probado.
- Nada se ha medido contra el exchange real: formatos de respuesta tomados de la
  documentación de Binance y MetaQuotes.

## NEXT (en este orden)

1. El dueño ejecuta el verificador de permisos y comunica solo el resultado
   (OK de solo lectura, permisos sobrantes o código HTTP).
2. Si es OK: definir las dos variables de solo lectura y ejecutar H4.
3. Claves de Testnet: comprobación de conexión y, con permiso del dueño, una
   orden mínima en Testnet para validar formatos y la conciliación.
4. Decidir cómo instalar `MetaTrader5` sin tocar Smart App Control.
5. LIVE sigue cerrado: faltan `LIVE_CAPITAL_USD`, `MAX_RISK_PER_TRADE`,
   `MAX_DAILY_LOSS`, `MAX_DRAWDOWN`, `MAX_OPEN_POSITIONS`, `ALLOWED_INSTRUMENTS`,
   `MAX_LEVERAGE` y la autorización explícita del dueño. El piloto previsto de
   USD 30 no cambia esto.

## Texto propuesto para la descripción del PR #9

**Título:** Sistema PAPER real (#3 -> #4 -> F3) + capa de API de solo lectura (H1-H3)

Contiene la cadena completa: import del runtime PAPER (#3), contrato MARKET lote/dust (#4), fix de
`is_junction` (#5), halt persistente y política de drawdown ratificada (F3) con sus dos defectos de
watchdog corregidos, y la capa de API: lectura firmada de Binance con guardia de permisos (H1),
órdenes solo en Spot Testnet con diario y conciliación (H2) y lectura de XM/MT5 en demo (H3).

PAPER únicamente. Ningún código de esta rama envía órdenes a Binance real, mueve fondos ni maneja
credenciales; nada se ha ejecutado contra una cuenta real, Testnet ni una terminal MT5. Detalle de
pruebas, límites y pasos pendientes del dueño: `docs/HANDOFF_CLAUDE_LOCAL_API.md`.
