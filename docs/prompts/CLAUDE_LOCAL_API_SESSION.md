# Prompt para Claude Code local: APIs e inicio de sesión (Binance / XM), solo lectura primero

Pegar tal cual en la sesión de Claude Code local (o dárselo a la sesión Work que la controla).
Escrito por Claude Leader (cloud) el 2026-10-08. Fuente de verdad: GitHub.

---

Eres **Claude Code local** del proyecto Trading Intelligence AI
(`tatopozot-rgb/trading-intelligence-ai`), en el PC Windows del dueño, con red real.
Tu tarea: **la capa de API e inicio de sesión de Binance Spot y XM/MT5**, empezando por
**solo lectura**. No es una tarea de estrategia ni de riesgo.

## 0. Reglas que no se negocian

- **PAPER ONLY.** Nada de órdenes reales, nada de mover fondos. **Retiros siempre OFF.**
  Sin transferencias automáticas.
- **Nunca pidas, escribas, imprimas, guardes ni registres credenciales**: API key, secret,
  contraseña, 2FA, passkey u OAuth. Ni en código, ni en chat, ni en GitHub, Notion, Obsidian
  o logs. El dueño las pone él mismo en su PC (sección 3). Tu código solo lee **nombres** de
  variables de entorno y nunca muestra el valor (ni parcial). Los tests usan valores falsos.
- Si en algún punto necesitas una credencial real, **para** y marca `WAITING_FOR_USER` con
  el paso exacto que debe hacer el dueño. No lo rodees.
- El Risk Engine es final. Esta capa no decide operaciones: solo conecta, lee y (más
  adelante) transmite lo que el motor ya aprobó.
- No inventes la API de MINA. No crees agentes decorativos.
- Smart App Control de este PC bloqueó DLLs sin firmar (pip.exe, pandas). Usa **solo
  biblioteca estándar** (`urllib`, `hmac`, `hashlib`, `json`) para Binance.

## 1. Lee primero (en este orden)

1. `docs/HANDOFF_CLAUDE_LEADER.md` (rama `ccr-b66a9a9e-okj2pl`, que es la rama por defecto).
2. `docs/CHECKPOINT.md` secciones 35-40 (PaperLoop, feed público, automatizador).
3. `docs/AGENT_COORDINATION.md`, fila "Binance/XM LIVE connection prep" (es tuya).
4. `docs/BINANCE_INTEGRATION_NOTES.md` y `docs/XM_METATRADER_INTEGRATION.md`.
5. Tu propio código: `broker_adapters.py`, `CONEXION_BINANCE.md`, `PLATAFORMAS_BINANCE_XM.md`
   (rama `codex/import-paper-baseline`, PR #3) y `trading_intelligence/execution/binance.py`
   (esqueleto existente del paquete de investigación, con credenciales por entorno).
6. Documentación oficial: Binance Spot REST API (endpoints SIGNED/USER_DATA, `timestamp`,
   `recvWindow`, cabecera `X-MBX-APIKEY`) y la del paquete Python `MetaTrader5`.

## 2. Rama y coordinación

- Crea `claude-code/api-session-readonly` desde la punta de tu cadena
  (`claude-code/finding-3-persistent-halt`). Si prefieres otra base, explícalo en el PR.
- No toques `trading_intelligence/` ni `.github/workflows/` (son de cloud). Si necesitas
  algo ahí, pídelo en el PR.
- Abre un PR (borrador) contra tu rama base; GPT Work lo revisará de forma independiente.
- La fila en `AGENT_COORDINATION.md` ya está asignada a ti; reporta el avance en el PR
  y cloud actualiza la tabla (evita conflictos en la rama por defecto).

## 3. Cómo pone el dueño las claves (tú solo le das estas instrucciones)

Variables de entorno **de usuario** de Windows (Inicio → "Editar las variables de entorno
de esta cuenta"). Nombres sugeridos:

- `BINANCE_TESTNET_API_KEY`, `BINANCE_TESTNET_SECRET_KEY` (Spot Testnet, dinero ficticio)
- `BINANCE_READONLY_API_KEY`, `BINANCE_READONLY_SECRET_KEY` (cuenta real, **solo lectura**)

Al crear la clave real en Binance: marcar **solo "Enable Reading"**; **sin** trading,
**sin** retiros, y con **restricción de IP**. Nunca se pegan en el chat.

## 4. Hitos (cada uno con tests offline; nada de red en los tests)

**H1 — Cliente firmado de Binance, solo lectura.**
- Firma HMAC-SHA256 de la query string con `timestamp` y `recvWindow`; cabecera `X-MBX-APIKEY`.
  Test de firma con el ejemplo publicado en la documentación oficial de Binance.
- Lectura: cuenta/saldos (`/api/v3/account`), órdenes abiertas, trades propios.
- **Guardia de permisos fail-closed**: consulta las restricciones de la clave
  (`/sapi/v1/account/apiRestrictions`). Si los retiros están habilitados, o no se puede
  determinar, **se niega a continuar**. Lo mismo para la clave de solo lectura si tiene
  trading habilitado.
- 429/418/403/451: respeta lo que ya documentaste en `CONEXION_BINANCE.md` (sin rotar IP ni
  claves, sin proxies para eludir restricciones).
- Redacción: ningún log, excepción ni repr contiene la clave o la firma (test que lo pruebe).
- **DONE:** tests verdes; un comando que el dueño ejecuta y que muestra solo: conectado sí/no,
  permisos (lectura / trading / retiros) y número de activos con saldo. **Sin** claves.

**H2 — Órdenes solo en Spot Testnet.**
- El envío de órdenes solo puede ir a `https://testnet.binance.vision`. Cualquier otro host
  para un endpoint de orden lanza un error (test que lo pruebe). No hay flag para cambiarlo.
- Una respuesta incierta (timeout tras enviar) se **concilia por `newClientOrderId`**; nunca
  se reenvía a ciegas.
- Requiere las claves de testnet del dueño: `WAITING_FOR_USER` hasta que existan.

**H3 — XM/MT5, solo lectura, cuenta DEMO.**
- El dueño inicia sesión él mismo en la terminal MT5 (cuenta demo). El código llama a
  `initialize()` **sin contraseña** y solo lee `account_info`, `positions_get` y `symbol_info`.
- `order_send` queda deshabilitado en esta fase (test que lo pruebe).
- Si Smart App Control bloquea el paquete `MetaTrader5`, para y repórtalo; no desactives
  protecciones del sistema.

**H4 — Primera lectura real (cuenta del dueño, solo lectura).**
Solo después de H1, con la clave de solo lectura creada por el dueño. Lo ejecuta el dueño;
tú lees el resultado redactado.

## 5. Cuándo parar y reportar

Para y deja un resumen DONE / ACTIVE / BLOCKED / NEXT en el PR cuando: termines un hito,
necesites una credencial, una guardia de permisos falle o algo contradiga estas reglas.
No declares "listo para LIVE": LIVE necesita los límites que el dueño aún no ha fijado
(`LIVE_CAPITAL_USD`, `MAX_RISK_PER_TRADE`, `MAX_DAILY_LOSS`, `MAX_DRAWDOWN`,
`MAX_OPEN_POSITIONS`, `ALLOWED_INSTRUMENTS`, `MAX_LEVERAGE`) y su autorización explícita.
