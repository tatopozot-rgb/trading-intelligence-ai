# Avisos de Telegram

Pedido del dueño, 2026-10-15: "las notificaciones más lógicas ... las de dinero ficticio a las 10, detalle de lo
que pasó ... lo de dinero real cuando empiece la operación y cuando termine".

| Qué | Cuándo llega | Código |
|-----|--------------|--------|
| Bot de **dinero real** (Futuros) | Un aviso al **abrir** cada operación (moneda, compra o venta, entrada, stop, meta, cuánto arriesga) y otro al **cerrar** (motivo: meta, stop u otro; resultado en USDT y % de la cuenta) | `two_way.REAL_TELEGRAM` |
| Bots de **práctica** (Futuros simulado, Núcleo BTC 50 y 50+200, agentes XM demo, Londres en oro) | **Nada por operación.** Un solo resumen a las **22:00 de Ecuador** con lo que pasó en cada uno y una conclusión | `two_way.PRACTICE_TELEGRAM`, `live/resumen_diario.py` |
| **Alarmas** (límite de pérdida, freno del día, fallos de conexión, orden que la cuenta no confirma, orden rechazada, alarma de mercado) | Al instante, en todos los bots | tipo `alarma` |
| **Bot caído** (dejó de escribir su estado: 20 min el motor, 30 min Londres, 3 h el Núcleo) | Al instante, una vez; y otra cuando vuelve | `resumen_diario vigilar` |
| Respuestas a tus órdenes (CIERRA, META, continuar) | Al instante | tipo `dueño` |

El estado cada 2 minutos y el "sigo vivo" cada 4 horas ya no van a Telegram: quedan en la consola y en el diario de
la mesa. El resultado de cada cierre sale de Binance (Futuros real: sus fills, neto de comisiones; práctica: su libro
simulado); en XM se estima con el precio de salida y se marca "aprox.".

En la PC (tareas programadas, sin ventana):

    python -m trading_intelligence.live.resumen_diario enviar    # todos los días a las 22:00
    python -m trading_intelligence.live.resumen_diario vigilar   # cada 10 minutos
    python -m trading_intelligence.live.resumen_diario ver       # para mirarlo en la consola, sin enviar

Los montos del dinero real solo viajan a tu Telegram: el resumen lee `live_runs/` de la PC y nunca se sube al repo.
