# Ganar también cuando el mercado baja (ventas en corto): qué hace falta

Escrito por Claude Leader el 2026-10-09, a pedido del dueño: "si el oro algún rato se desploma
nuestro automatizador no va a hacer nada… debe irse en contra o a favor del mercado".

## Resultado de la prueba con datos reales: NO (2026-10-09)

La sesión Quant probó, con datos reales de 4 años, cortos en 4h sobre las 12 monedas y PAXG
(oro). Usó comisiones y *funding* de Futuros y no retocó nada (CHECKPOINT sección 61):

- **pierde 1,70% por operación**, gana solo el 23% de las veces, p = 0,001;
- pierde en los 5 periodos de prueba, también en los de mercado bajista; en PAXG, −0,87%;
- sumar cortos a lo que ya hacemos **empeora** el resultado (+7.851 contra +11.219 sin cortos).

**Decisión del líder:** con esta lógica no se activan cortos reales y no se construye el
transporte de Futuros. Cuando el mercado cae, el sistema hace lo que sí funciona: no compra en
tendencia bajista y sale con stops puestos en Binance. Otra estrategia de corto sería un estudio
nuevo, registrado antes, con datos que no se usaron aquí; solo se activaría si pasa.

## Por qué hoy no puede

Hoy el sistema opera en **Spot**: compra una moneda y la vende después. En Spot solo se gana
si el precio sube. Cuando baja, lo único que puede hacer es salirse a USDT a tiempo, y eso ya
lo hace con los stops. Ganar con la bajada (vender primero y recomprar más barato) solo existe
en **Futuros** o en **Margin**, y hoy está fuera de los límites aprobados ("SPOT, sin
apalancamiento") y de lo que la clave permite.

## Lo que propongo (todo con tu aprobación escrita)

| Pieza | Propuesta |
|---|---|
| Mercado | Binance **Futuros USDⓈ-M** (perpetuos), solo para cortos |
| Apalancamiento | **1x** (sin apalancar): una posición de 40 USDT vende en corto 40 USDT |
| Riesgo de liquidación con 1x | solo si el precio sube cerca del 100% desde la entrada; antes salta el stop |
| Stop | cada corto con su **STOP_MARKET reduce-only puesto en Binance**, igual que hoy en Spot |
| Cuándo | solo con el régimen en `TREND_DOWN` o `BREAKOUT_DOWN` y la señal de la estrategia |
| Tamaño | igual que hoy: máximo 40% por posición, 3 posiciones entre largos y cortos |
| Pérdida de la sesión | la misma guardia: tu límite (35% estándar, 20–50 a tu palabra) y aviso 2 USD antes |
| Oro | **PAXGUSDT** en Spot (token respaldado por oro) para el lado comprador; corto de oro solo si Binance Futuros lo ofrece en tu cuenta |

## Qué tienes que hacer tú, cuando lo apruebes

1. En Binance, **abrir la cuenta de Futuros** (cuestionario de Binance) y pasar ahí el capital que
   quieras usar para cortos. Las transferencias entre tus propias billeteras las haces tú.
2. En la clave de la API, activar **"Enable Futures"**. Retiros siguen **desactivados**.
3. Escribirme algo como: **"apruebo cortos en futuros 1x con los límites de DECISION_SHORTS"**.

## Qué hago yo antes de que haya un solo corto real

1. **Medirlo con datos reales.** Hecho: la estrategia de corto en 4h **perdió** (arriba). No se
   activa, igual que pasó con 1h. Los pasos 2 y 3 quedan en pausa.
2. Construir el transporte de Futuros con las mismas protecciones de hoy: diario antes de enviar,
   nunca reenviar una orden dudosa, stop puesto en Binance y conciliación.
3. Ensayo SHADOW en tu PC, y después la sesión real con tu frase.

## Lo que no cambia

Nada de retiros, de martingala, ni de subir el riesgo para recuperar. Tu límite de pérdida
manda por encima de todo.
