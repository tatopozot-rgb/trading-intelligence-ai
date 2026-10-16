# Preregistro: oro solo dentro del día, sin swap (2026-10-16)

Escrito el 2026-10-16, **antes** de correr nada. Encargo del líder (2026-10-16): oro sin swap, solo dentro del día,
cerrando antes del rollover de XM, con 2 o 3 variantes como máximo. El swap largo de GOLD en XM (−0,84 USD por onza
y noche) se come cualquier idea que duerma comprada, así que todo cierra a las 20:00 UTC (el rollover de XM es a
medianoche del servidor, 21:00 o 22:00 UTC). La ruptura de Londres ya se probó (`docs/research/oro/`); estas son
otras. Las 6 pruebas están anotadas como "pendiente" en `docs/research/REGISTRO_PRUEBAS.md` en este mismo commit.
Nada se cambia después de ver el resultado.

## Datos y costes

- Velas de 15 minutos de PAXGUSDT en Spot de Binance, sin sábados ni domingos, desde 2024-06-01.
- Apertura de Nueva York = 9:30 en Nueva York, pasada a UTC cada día (13:30 UTC en verano y 14:30 UTC en
  invierno).
- Costes de GOLD real en XM demo: diferencial 0,40 USD por onza (mitad por lado) más 0,05 de deslizamiento por lado.
  Sin swap, porque nada queda abierto de noche.
- Capital 1.000 USD al empezar cada año. Una operación por día como máximo por prueba.

## Las tres reglas

1. **Ruptura del rango de apertura de 30 minutos** (Toby Crabel, *Day Trading with Short Term Price Patterns and
   Opening Range Breakout*, 1990). Rango = máximo y mínimo de las dos velas de 15 minutos desde la apertura de Nueva
   York. Después, hasta las 18:00 UTC, la primera vela que toque el máximo entra largo (en el máximo, o en la apertura
   de la vela si abrió más allá) y la que toque el mínimo entra corto. Stop en el otro lado del rango; sin meta; sale
   en la apertura de la vela de 20:00 UTC. Riesgo 1% del capital hasta el stop, tamaño máximo 5 veces el capital.
   Si una vela toca entrada y stop, cuenta el stop.
2. **Lo mismo con el rango de 60 minutos** (cuatro velas).
3. **Impulso dentro del día** (Gao, Han, Li y Zhou, *Market Intraday Momentum*, 2018; Baltussen, Da, Lammers y
   Martens, 2021, para materias primas). Si el oro subió desde el cierre de la vela de 20:00 UTC de ayer hasta 30
   minutos después de la apertura de Nueva York, se compra en la apertura de la vela de 19:00 UTC; si bajó, se vende.
   Sale en la apertura de la vela de 20:00 UTC. Sin stop; tamaño = 100% del capital, 1x.

## Sensibilidad

Costes al doble en las tres (solo informativa).

## Cómo se juzga (fijado ahora)

- Años: 2024-10-12 → 2025-10-12 y 2025-10-13 → 2026-10-13.
- **Pasa a práctica** solo si cumple el protocolo: neto/caída mayor que la mesa en **los dos años** (1,67 y −0,21;
  se informa también la mesa re-medida, 1,73 y 0,20) **y** Sharpe deflactado de 2025-26 de al menos 0,95 con N = las
  decisorias del registro (257 con estas 3) y V = 1/T, sobre rendimientos diarios.
- Menos de 100 operaciones en un año: "muestra corta". El JSON guarda el capital diario.
- Advertencia fijada ahora: PAXG cotiza en Binance, no en el COMEX; la apertura de Nueva York puede pesar menos en
  PAXG que en el oro de XM.
- No se toca `config/`, `live/` ni los límites.
