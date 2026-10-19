# Preregistro: nube de Ichimoku en BTC y ETH diario (2026-10-19)

Escrito el 2026-10-19, **antes** de correr nada. Las reglas las fijó el líder en `docs/inteligencia/BOTS_PUBLICOS.md`
(sección 2026-10-19, PR #107). Aquí solo se fija cómo se simulan. Las filas quedan "pendiente" en
`docs/research/REGISTRO_PRUEBAS.md` en este mismo commit. Datos públicos de Binance, sin cuenta, sin clave y sin
órdenes.

## Indicador (9/26/52 fijos, no se afinan)

- Tenkan = (máximo + mínimo de los últimos 9 días, hoy incluido) / 2. Kijun = lo mismo con 26 días.
- Borde A de hoy = (Tenkan + Kijun) de hace 26 días / 2. Borde B de hoy = (máximo + mínimo de 52 días) de hace 26
  días / 2.
- Nube de adelante (la que se dibuja 26 días adelante) = A y B calculados hoy. Es verde si A > B.

## Reglas

1. **Entrada en compra**, al cierre del día: cierre sobre la nube de hoy (sobre el borde más alto), Tenkan > Kijun y
   nube de adelante verde. Se entra en la apertura del día siguiente.
2. **Salida**, al cierre del día: cierre bajo la Kijun, o cierre dentro de la nube o debajo de ella (no sobre el
   borde más alto). Se sale en la apertura del día siguiente.
3. Solo compras. Una posición a la vez por moneda.
4. Costos de la mesa: 0,05% de comisión y 0,02% de deslizamiento por lado. Financiación real del perpetuo
   (`data.binance.vision`) por cada día con la posición abierta; el largo paga si es positiva.
5. Velas diarias UTC del contado de Binance (BTCUSDT, ETHUSDT). 1.000 USDT al empezar cada año. Juntas: dos cuentas
   de 500 USDT, una por moneda.

## Dos versiones

- **A, tal cual:** 100% del capital de la moneda a 1x, sin stop aparte.
- **B, con los frenos de la mesa:**
  - Stop en la Kijun del día de la señal; cada día sube a la Kijun nueva si es más alta (nunca baja). Se llena en el
    stop, o en la apertura si el día abrió por debajo.
  - Tamaño: 2% del capital de la moneda en riesgo hasta el stop, con tope de 1x. Sin entrada si la Kijun no queda
    bajo el precio de entrada.
  - Freno de mercado (régimen b): solo se entra si el cierre de ayer de BTC está sobre su media de 50 días. Si deja
    de estarlo, el largo se cierra en la apertura siguiente.
  - Freno de eventos: sin entradas el día UTC en que cae una decisión FOMC o un dato de IPC
    (`research_mesa.FOMC_DAYS` y `CPI_DAYS`).

## Filas

Decisorias (N pasa de 272 a 278):

1. A, BTC. 2. A, ETH. 3. A, juntas. 4. B, BTC. 5. B, ETH. 6. B, juntas.

Sensibilidad (no cuentan): 7. A juntas, costos ×2. 8. B juntas, costos ×2.

## Listones

1. Neto/caída mayor que la mesa de práctica en los dos años: 1,67 en 2024-25 y −0,21 en 2025-26.
2. Sharpe deflactado ≥ 0,95 en 2025-26, con N = 280 (las 278 de aquí más las 2 decisorias del freno por caída,
   preregistradas en el mismo commit) y V = 1/T, sobre rendimientos de días naturales.

Pasa solo con los dos. Menos de 10 operaciones en un año: "muestra corta". Se informa también contra mantener BTC. El
dinero real no cambia por este estudio.
