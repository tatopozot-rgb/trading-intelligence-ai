# Estudio del mercado de opciones

**Orden del dueño, 2026-10-13:** «quiero que revises otro mercado ... no vamos a empezar con esto, solo vamos a hacer un
estudio para ver de qué se trata. Tú mismo lo vas a estudiar ... sacas un agente más para eso o unos dos agentes de
revisión ... y en un mes, dos meses empezamos con esto. Es el mercado de opciones.»

Solo estudio: no se abre ninguna cuenta, no hay claves y no se opera. El dueño va a enviar lo que le recomendó una
persona que sabe del tema; el líder lo acopla a este plan cuando llegue.

## Equipo

- **Analista de Opciones** (`.claude/agents/analista-opciones.md`): estudia y escribe una nota por semana.
- **Riesgo de Opciones** (`.claude/agents/riesgo-opciones.md`): revisa cada idea y la rechaza si no cumple.
- **Compliance:** confirma si cada plataforma atiende a residentes de Ecuador antes de cualquier práctica.

## Calendario

| Fase | Fechas | Meta |
|---|---|---|
| 1. Aprender | 13-10 a 13-11 | Temas 1 a 4 de la lista de abajo. Recordatorio al dueño el 13-11. |
| 2. Diseñar | 13-11 a 13-12 | Temas 5 y 6: una o dos estrategias de riesgo limitado, probadas sobre datos grabados. |
| 3. Decidir | dic-2026 | Si Riesgo de Opciones y Compliance aprueban: práctica con dinero ficticio. El dinero real necesita los límites escritos del dueño. |

## Temas

| # | Tema | Estado |
|---|------|--------|
| 1 | Lo básico: call, put, strike, vencimiento, prima | pendiente |
| 2 | Las griegas y la volatilidad implícita | pendiente |
| 3 | Dónde se opera: Interactive Brokers (opciones de EE. UU.), Binance Options, Deribit, OKX, Bybit (mínimos, comisiones, Ecuador) | en curso |
| 4 | Qué dicen las opciones a la mesa de futuros (put/call, sesgo, DVOL, vencimientos grandes) | pendiente |
| 5 | Estrategias de riesgo limitado para 30–100 USDT | pendiente |
| 6 | Plan de práctica: regla, tamaño, salida y prueba con comisiones | pendiente |

## Reglas que ya están claras

- Nunca vender opciones «al descubierto» (pérdida sin límite).
- Pérdida máxima conocida antes de entrar.
- Todo se liquida en USDT.

## Interactive Brokers (pedido del dueño, 2026-10-14)

Orden del dueño: «necesito saber si podemos tener acceso a Interactive Brokers LLC para poder revisar ahí todo el
mercado de opciones».

- **Ecuador:** aparece en la lista oficial de países que pueden abrir cuenta
  ([IBKR, países](https://www.interactivebrokers.com/en/accounts/open-account-country-list.php)). Compliance lo confirma
  antes de cualquier práctica.
- **Lo difícil es depositar desde Ecuador, no abrir la cuenta.** IBKR tiene una herramienta que muestra los métodos de
  depósito según el país ([IBKR, cuentas](https://www.interactivebrokers.com/en/accounts/individual.php)).
- **Datos de opciones de EE. UU. en vivo:** suscripción OPRA ~1,50 USD al mes para no profesionales. IBKR pide un saldo
  mínimo en la cuenta para activarla; el monto exacto está sin confirmar
  ([IBKR, datos](https://www.interactivebrokers.com/en/pricing/research-news-marketdata.php)). Los datos con retraso son
  gratis y alcanzan para la fase de estudio.
- **Conexión:** la abre el dueño con su usuario. Local se conectaría por la API de TWS o IB Gateway en su PC, en modo
  **solo lectura**. Nunca se guardan usuario, clave ni datos de la cuenta en GitHub, Notion ni registros.
- **Plan:**
  1. Estudio con datos con retraso, en la fase 1.
  2. Cuenta de práctica de IBKR en la fase 3.
  3. Dinero real solo con límites de opciones escritos por el dueño.

## Pendiente: Alejandro Cardona (dueño, 2026-10-14: «lo vemos después, tenlo en mente»)

- **Quién es:** educador de opciones de EE. UU. Seminario «Creando Riqueza», libro *Crea tu propia riqueza*.
- **Registro:** BrokerCheck de FINRA muestra un Alejandro Cardona con licencias de opciones (Series 4); sin confirmar
  que sea la misma persona. No se encontraron sanciones.
- **Publicidad sin verificar:** promete «3.000%» y «450% en un día». No hay un historial auditado.
- **Siguiente paso:** cuando el dueño consiga sus notas o una estrategia concreta, el Analista de Opciones escribe sus
  reglas, Riesgo de Opciones las revisa y se prueban con datos antes de cualquier práctica.
