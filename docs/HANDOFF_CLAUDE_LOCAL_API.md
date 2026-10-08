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
| H2 órdenes solo en Spot Testnet | `binance_testnet_orders.py` | `test_binance_testnet_orders.py`, 21 | 34 de 34 |
| H3 XM/MT5 demo, solo lectura | `xm_mt5_readonly.py` | `test_xm_mt5_readonly.py`, 10 | 19 de 19 |

- `python -B tools/check_repository.py`: 0 hallazgos.
- Suite raíz completa en este PC: 429 pruebas, 43 errores, todos en módulos ya
  existentes que importan pandas ("Una directiva de Control de aplicaciones bloqueó
  este archivo"). Ninguno en los archivos de esta rama. No se ejecutó mypy (no
  está instalado aquí).
- Comprobado sin credenciales: `api.binance.com/api/v3/time` responde 200 desde
  este PC y el reloj local va unos 1,1 s por detrás del servidor, dentro de
  `recvWindow` = 5000 ms.

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
5. PR borrador: este PC no tiene `gh` y el conector de GitHub no conectó. Abrir desde
   `https://github.com/tatopozot-rgb/trading-intelligence-ai/compare/claude-code/finding-3-persistent-halt...claude-code/api-session-readonly?expand=1`.

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
