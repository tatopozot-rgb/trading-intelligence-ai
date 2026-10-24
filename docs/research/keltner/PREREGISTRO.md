# Preregistro: ruptura del canal de Keltner (Raschke) en BTC y ETH diario (2026-10-24)

Escrito el 2026-10-24, **antes** de correr nada. Las reglas las fijó el líder en `docs/inteligencia/BOTS_PUBLICOS.md`
(sección 2026-10-24, PR #143). Aquí solo se fija cómo se simulan. Las filas quedan "pendiente" en
`docs/research/REGISTRO_PRUEBAS.md` en este mismo commit. Datos públicos de Binance, sin cuenta, sin clave y sin
órdenes. No se toca `config/` ni `live/`.

## Indicador (valores publicados, no se afinan)

- Velas diarias UTC del contado de Binance (BTCUSDT, ETHUSDT), desde 2023-10-01 para que todo esté asentado.
- EMA de 20 cierres (α = 2/21, desde el primer cierre).
- ATR de Wilder de 10 días: media de Wilder (α = 1/10, desde el primer rango verdadero) del rango verdadero
  (máximo − mínimo, o la distancia al cierre anterior si es mayor).
- Banda de arriba = EMA + 2 × ATR.

## Reglas

1. **Compra** al abrir el día siguiente a un cierre sobre la banda de arriba, si no hay posición.
2. **Venta** al abrir el día siguiente a un cierre bajo la EMA de 20.
3. Solo compras. Una posición por moneda. Si una compra no se pudo hacer (freno), vale el próximo cierre sobre la
   banda.
4. Costos de la mesa: 0,05% de comisión y 0,02% de deslizamiento por lado; financiación real del perpetuo por día
   dentro. 1.000 USDT al empezar cada año; juntas = dos cuentas de 500. Lo abierto al final se cierra al último
   cierre.

## Dos versiones (el simulador del MACD, `research_macd.simulate`, como el Parabolic SAR)

- **A, tal cual:** 100% del capital de la moneda a 1x. Sin stop aparte: solo sale por la regla 2.
- **B, con los frenos de la mesa:** además, el stop dentro del día es el más cercano entre el stop de la mesa
  (`plan_exits` sobre 300 velas diarias cerradas, fijado al entrar) y la EMA de 20 del cierre anterior (se conoce al
  abrir). El stop solo sube. Tamaño de 2% de riesgo sobre la distancia a ese stop, con tope de 1x. Freno de mercado b
  (BTC sobre su media de 50 días; si deja de estarlo, cierra en la apertura siguiente) y sin entradas el día UTC de
  FOMC o IPC.

## Filas (regla del 21-10: solo estas 3; cualquier otra que se mire cuenta en N)

Decisorias (N pasa de 301 a 304): 1. A, BTC y ETH juntas. 2. B, BTC y ETH juntas. 3. **B, BTC solo**: elegida antes
de ver resultados porque BTC es la moneda con más liquidez y menor costo, y la que manda el freno de mercado.

## Listones

1. Neto/caída mayor que la mesa de práctica en los dos años: 1,67 en 2024-25 y −0,21 en 2025-26.
2. Sharpe deflactado ≥ 0,95 en 2025-26, con N = 304 y V = 1/T.

Pasa solo con los dos. Menos de 10 operaciones en un año: "muestra corta". El dinero real no cambia por este estudio.
