# Preregistro: tendencia de horizonte largo en oro y BTC (2026-10-16)

Escrito el 2026-10-16, **antes** de correr nada. Encargo del líder (2026-10-16): priorizar ideas de días o semanas en
oro y BTC, lo que pidió Renato ("con el dinero ficticio deberías intentar buscar flujos más largos"). Tres reglas
públicas conocidas, con señal una vez al mes. Nada se cambia después de ver el resultado. Las 10 pruebas están
anotadas como "pendiente" en `docs/research/REGISTRO_PRUEBAS.md` en este mismo commit.

## Datos

- **Oro:** velas diarias de PAXGUSDT en Spot de Binance, sin sábados ni domingos (como en `docs/research/oro/`).
- **BTC:** velas diarias de BTCUSDT en Spot de Binance, todos los días, y la financiación real del perpetuo
  (`data.binance.vision`; sin dato, 0,01% cada 8 h).
- Desde 2023-06-01, para tener 12 meses de historia antes del primer año.
- **Cierre de mes** = el cierre del último día con vela de cada mes calendario (UTC). La señal se calcula con ese
  cierre y se opera en la apertura del día siguiente.

## Las tres reglas

1. **Media de 10 meses** (Mebane Faber, *A Quantitative Approach to Tactical Asset Allocation*, 2007). En cada cierre
   de mes: si el cierre está sobre la media de los últimos 10 cierres de mes (incluido este), largo; si no, fuera.
   Una prueba en oro y otra en BTC.
2. **Momento de 12 meses** (Moskowitz, Ooi y Pedersen, *Time Series Momentum*, 2012). En cada cierre de mes: si el
   cierre está sobre el de hace 12 cierres de mes, largo; si está debajo, corto. Sin ajuste por volatilidad
   (simplificación, fijada ahora). Una prueba en oro y otra en BTC.
3. **Momento dual** (Gary Antonacci, *Dual Momentum Investing*, 2014). En cada cierre de mes se compara el rendimiento
   de 12 meses de BTC y de oro. Se queda largo en el mejor, solo si su rendimiento de 12 meses es positivo; si no,
   fuera (efectivo al 0%). Una sola prueba.

## Tamaño y costes

- Capital 1.000 USD al empezar cada año. Una posición por regla, del 100% del capital, 1x, sin stop (las tres reglas
  originales no usan stop). Solo se opera cuando la posición deseada cambia; no se reajusta el tamaño cada mes.
- El primer día de cada año se abre la posición que dicta el último cierre de mes anterior, en la apertura.
- Lo que siga abierto al cierre del último día del año se cierra a ese cierre, con costes.
- **Oro (GOLD real de XM demo, leído por Claude local el 2026-10-15):** diferencial 0,40 USD por onza (la mitad por
  lado) más 0,05 USD de deslizamiento por lado. Swap por cada noche abierta (posición abierta a las 21:00 UTC, de lunes
  a viernes): largo −0,84 USD por onza, corto +0,21 USD por onza; la noche del miércoles cuenta triple.
- **BTC (perpetuo como la mesa):** comisión 0,05% y deslizamiento 0,02% por lado; financiación real cada 8 h (00, 08
  y 16 UTC): el largo paga si es positiva, el corto cobra.
- **Sensibilidad (solo informativa):** todos los costes al doble, en las 5 pruebas.
- La caída se mide sobre el capital marcado al cierre de cada día. El JSON guarda ese capital diario.

## Cómo se juzga (fijado ahora)

- Años: 2024-10-12 → 2025-10-12 y 2025-10-13 → 2026-10-13. Cada prueba por separado, con costes base.
- **Pasa a práctica** solo si cumple las dos cosas:
  1. su neto/caída supera al de la mesa de práctica en **los dos años** (1,67 y −0,21; se informa también la mesa
     re-medida, 1,73 y 0,20);
  2. su Sharpe deflactado (`research_deflactado`) es al menos 0,95 en el año 2025-26, con N = las pruebas decisorias
     del registro (252 con estas 5) y V = 1/T.
- Con una señal al mes habrá pocas operaciones: todas son **muestra corta**. Por eso solo podría ir a práctica con
  dinero ficticio, nunca directo a dinero real.
- Se informa al lado: comprar y mantener oro, comprar y mantener BTC, número de operaciones, días dentro, y lo que
  costaron el swap y la financiación.
- No se toca `config/`, `live/` ni los límites.
