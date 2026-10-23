# Preregistro: Parabolic SAR de Wilder en BTC y ETH diario (2026-10-23)

Escrito el 2026-10-23, **antes** de correr nada. Las reglas las fijó el líder en `docs/inteligencia/BOTS_PUBLICOS.md`
(sección 2026-10-23, PR #136). Aquí solo se fija cómo se simulan. Las filas quedan "pendiente" en
`docs/research/REGISTRO_PRUEBAS.md` en este mismo commit. Datos públicos de Binance, sin cuenta, sin clave y sin
órdenes. No se toca `config/` ni `live/`.

## Indicador (parámetros de Wilder, no se afinan: 0,02 / 0,02 / 0,20)

Sobre velas diarias UTC del contado de Binance, desde 2023-10-01.

- Arranque (día 1): subida si cierre(1) ≥ cierre(0); SAR = mínimo del día 0 en subida (máximo en bajada); punto
  extremo (PE) = máximo del día 0 en subida (mínimo en bajada); aceleración (AF) = 0,02.
- Nivel del día t (se conoce al abrir t): SAR(t) = SAR(t−1) + AF × (PE − SAR(t−1)). En subida no pasa del mínimo de
  t−1 ni de t−2; en bajada no baja del máximo de t−1 ni de t−2.
- Giro: en subida, si el mínimo de t toca el nivel (mínimo ≤ SAR), pasa a bajada; el SAR del día pasa a ser el PE,
  el PE nuevo es el mínimo de t y AF vuelve a 0,02. En bajada, igual con el máximo. Sin giro, un máximo nuevo (o
  mínimo nuevo en bajada) mueve el PE y sube AF en 0,02, con tope 0,20.
- El SAR publicado del día t es el nivel, o el PE en el día de giro (como TA-Lib).

## Reglas

1. **Compra** al abrir el día siguiente a un cierre t sobre el SAR(t), cuando el cierre t−1 estaba bajo el SAR(t−1)
   (giro a subida).
2. **Venta** al abrir el día siguiente a cualquier cierre bajo el SAR mientras hay posición.
3. Solo compras, sin cortos. Una posición por moneda. Si una compra no se pudo hacer (freno), se espera al próximo
   giro.
4. Costos de la mesa: 0,05% de comisión y 0,02% de deslizamiento por lado; financiación real del perpetuo por día
   dentro. 1.000 USDT al empezar cada año; juntas = dos cuentas de 500. Lo abierto al final se cierra al último
   cierre.

## Dos versiones (el simulador del MACD, `research_macd.simulate`)

- **A, tal cual:** 100% del capital de la moneda a 1x. Sin stop aparte: solo sale por la regla 2.
- **B, con los frenos de la mesa:** además, el stop dentro del día es el más cercano entre el stop de la mesa
  (`plan_exits` sobre 300 velas diarias cerradas, fijado al entrar) y el nivel del SAR del día (que se conoce al
  abrir y sube cada día). Tamaño de 2% de riesgo sobre la distancia a ese stop, con tope de 1x. Freno de mercado b
  (BTC sobre su media de 50 días; si deja de estarlo, cierra en la apertura siguiente) y sin entradas el día UTC de
  FOMC o IPC.

## Filas (regla del 21-10: solo estas 3; cualquier otra que se mire cuenta en N)

Decisorias (N pasa de 297 a 300; con la del tope al riesgo abierto, preregistrada en el mismo commit, a 301):
1. A, BTC y ETH juntas. 2. B, BTC y ETH juntas. 3. **B, BTC solo**: elegida antes de ver resultados porque BTC es la
moneda con más liquidez y menor costo, y la que manda el freno de mercado.

## Listones

1. Neto/caída mayor que la mesa de práctica en los dos años: 1,67 en 2024-25 y −0,21 en 2025-26.
2. Sharpe deflactado ≥ 0,95 en 2025-26, con N = 301 y V = 1/T.

Pasa solo con los dos. Menos de 10 operaciones en un año: "muestra corta". El dinero real no cambia por este estudio.
