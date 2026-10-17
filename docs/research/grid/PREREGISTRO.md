# Preregistro: bot de cuadrícula ("Spot Grid") en BTC y ETH (2026-10-17)

Escrito el 2026-10-17, **antes** de correr nada. Las reglas las fijó el líder en
`docs/inteligencia/BOTS_PUBLICOS.md` (entrada 2026-10-17, PR #95); aquí solo se fija cómo se simulan. Las filas
quedan "pendiente" en `docs/research/REGISTRO_PRUEBAS.md` en este mismo commit. Datos públicos de Binance, sin
cuenta, sin clave, sin órdenes.

## Regla (del líder, sin cambios)

- Velas de 1 hora de Binance (BTCUSDT, ETHUSDT). Al contado, 1x, sin stop.
- Cada lunes a las 00:00 UTC se cierra la cuadrícula anterior al precio de apertura de esa vela y se arma una nueva.
- Rango: precio de apertura ±10%. 20 escalones geométricos (21 niveles, razón (1,1/0,9)^(1/20) ≈ 1,0101).
- Cada escalón usa 1/20 del capital del lunes. Compra en su nivel de abajo; vende esa porción en el nivel de arriba.
- Fuera del rango no hay órdenes nuevas; se mantiene lo comprado hasta el lunes.

## Cómo se simula (fijado hoy)

1. **Capital:** 1.000 USDT por fila (sin lote mínimo que importe: 1/20 son 50 USDT, sobre el mínimo de 5 USDT de
   Binance). Cada lunes el capital de cada escalón se recalcula con el capital total de ese momento.
2. **Primera cuadrícula** en la primera vela de cada año de prueba; desde ahí, cada lunes.
3. **Orden de compra viva:** un escalón vacío tiene su compra puesta si el cierre de la vela anterior (o la apertura,
   en la primera vela de la cuadrícula) está por encima de su nivel de abajo. Sin compra inicial de inventario.
4. **Llenado solo si se cruza:** la compra se llena si el mínimo de la vela queda **por debajo** del nivel; la venta,
   si el máximo queda **por encima** del nivel de arriba. Tocar no basta.
5. **Sin ida y vuelta en la misma vela:** lo comprado en una vela se puede vender desde la vela siguiente (la vela de
   1 hora no dice qué pasó primero).
6. **Costos base:** 0,1% de comisión por lado en todas las órdenes, también en el cierre del lunes.
7. **Mejor caso (sensibilidad):** las órdenes límite pagan 0,02% de maker y se llenan 0,01% a favor; el cierre del
   lunes es a mercado y sigue pagando 0,1%.
8. **Juntas a mitades:** dos cuadrículas, BTC y ETH, cada una con la mitad del capital; cada lunes se vuelve a
   repartir 50/50.
9. Al final de cada año se cierra todo al último cierre.
10. Se guarda el capital diario (cierre de cada día UTC).

## Qué se informa aparte

- **Idas y vueltas:** suma de lo ganado en cada compra-venta completa, neto de comisiones.
- **Inventario:** resultado de lo que el cierre del lunes (o del año) vendió por debajo o por encima de su compra,
  neto de comisiones. Neto = idas y vueltas + inventario.
- Referencias (no cuentan en N): mesa de práctica (1,67 ; −0,21) y mantener BTC el mismo año.

## Filas

Decisorias (N pasa de 263 a 266):

1. BTC, ±10%, costos base.
2. ETH, ±10%, costos base.
3. BTC y ETH a mitades, ±10%, costos base.

Sensibilidad (no cuentan, no deciden):

4. BTC, mejor caso de maker. 5. ETH, mejor caso de maker. 6. Mitades, mejor caso de maker.
7. BTC, ±5%. 8. ETH, ±5%. 9. BTC, ±20%. 10. ETH, ±20%.

## Listones

1. Neto/caída mayor que la mesa de práctica en los dos años: 1,67 en 2024-25 y −0,21 en 2025-26.
2. Sharpe deflactado ≥ 0,95 en 2025-26, con N = 266 y V = 1/T, sobre rendimientos de días naturales.

Una fila decisoria pasa solo con los dos. El dinero real no cambia por este estudio.
