# Preregistro: cripto que falló por costos de Binance, re-probada con costos de XM (2026-10-16)

Escrito el 2026-10-16, **antes** de correr nada. Encargo del líder (2026-10-16): XM no cobra comisión, solo spread y
swap; revisar qué estrategias de cripto fallaron principalmente por los costos de Binance y re-probar como máximo 3
con los costos de XM. Las 3 filas quedan "pendiente" en `docs/research/REGISTRO_PRUEBAS.md` en este mismo commit.

## Cuál se re-prueba y por qué solo una regla

Una revisión del registro (sumando de vuelta comisión, deslizamiento y financiación de cada informe) dio una sola
candidata clara: la **ruptura de Londres en BTC** (filas 271-272).

- Con costos de Binance perdió −14,8% y −17,8%; con costos ×2, −45% y −48%.
- Sin costos ganaba +12% a +34% por año, y 7 de 8 trimestres no eran negativos.
- Hace unas 340 operaciones al año, todas dentro del día, así que no paga swap en XM.

Las demás no son casos de costos:

- TSMOM 60 días fallaba por sus trimestres y usa 12 monedas que XM no tiene.
- Rango, RSI-2 y otras quedaban a 0,01-0,02 del listón con 6 a 46 operaciones, o perdían también sin costos.
- La reversión de 1 hora nunca se corrió en 2024-25.
- Las de varios días en BTC pagarían en XM un swap de unos 15% al año comprado y 10% vendido (−3.452 y −2.301 puntos
  por lote y noche).

## Costos de XM (ficha de la demo del 2026-10-16, `docs/research/cartera_xm/datos/fichas.txt`)

- BTCUSD: spread fijo de 40 USD por BTC, mitad por lado. Comisión 0 (confirmado en 23 operaciones demo).
- Sin swap: la regla cierra todo a las 20:00 UTC, antes del rollover.
- Lote mínimo 0,01 BTC, paso 0,01. Menos de medio lote mínimo: no se opera. Entre medio y uno: un lote mínimo, si no
  pasa del tope de 5 veces el capital.

## Regla (sin cambios, `research_oro.london`)

- Rango de Asia de 00 a 07 UTC. Entrada entre 07 y 16 UTC en la ruptura.
- Stop al otro lado del rango; meta a un rango; salida a las 20:00 UTC.
- 1% de riesgo por operación, tope 5 veces el capital.
- Precio: velas de 1 hora de BTCUSDT de Binance (el camino de XM puede diferir algo).

## Filas

1. **Costos de XM, 1.000 USD** — decisoria (N pasa a 259).
2. Spread ×2, 1.000 USD — sensibilidad.
3. Costos de XM, 200 USD — sensibilidad: cuántas operaciones impide el lote mínimo.

## Listones

1. Neto/caída mayor que la mesa de práctica en los dos años: 1,67 en 2024-25 y −0,21 en 2025-26.
2. Sharpe deflactado ≥ 0,95 en 2025-26, con N = 259 y V = 1/T, sobre los rendimientos de días naturales.

Pasa solo con los dos. El dinero real no cambia por este estudio.
