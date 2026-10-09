# Ganar también cuando el mercado baja (ventas en corto): qué hace falta

Escrito por Claude Leader el 2026-10-09, a pedido del dueño: "si el oro algún rato se desploma
nuestro automatizador no va a hacer nada… debe irse en contra o a favor del mercado".

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

1. **Medirlo con datos reales.** La sesión Quant ya lo está probando: estrategia de corto en 4h
   sobre las 12 monedas y PAXG, con comisiones y *funding*, sin retocar parámetros. Si pierde,
   te lo digo y no se activa, igual que pasó con 1h.
2. Construir el transporte de Futuros con las mismas protecciones de hoy: diario antes de enviar,
   nunca reenviar una orden dudosa, stop puesto en Binance y conciliación.
3. Ensayo SHADOW en tu PC, y después la sesión real con tu frase.

## Lo que no cambia

Nada de retiros, de martingala, ni de subir el riesgo para recuperar. Tu límite de pérdida
manda por encima de todo.
