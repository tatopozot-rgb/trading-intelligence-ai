# Preregistro: EWMAC de Carver en las 12 monedas de la mesa (2026-10-14)

Escrito el 2026-10-14, **antes** de correr nada. Las reglas son las del líder
(`docs/inteligencia/BOTS_PUBLICOS.md`); lo que el líder no fijó se fija aquí y no se cambia después de ver el
resultado. Un cambio sería otra regla, con otro preregistro.

## Datos y periodo

- Monedas: las 12 de `two_way_backtest.SYMBOLS`, largos y cortos. Velas diarias UTC de Spot de Binance
  (`data-api.binance.vision`) como aproximación del perpetuo; financiación real del archivo público
  (`data.binance.vision`), sumada por día. Indicadores calentados desde 2021-01-01.
- Dos años de prueba, los mismos de `docs/research/mesa/`: 2024-10-12 → 2025-10-12 y 2025-10-13 → 2026-10-13.

## Regla

1. Pares EWMA (`ewm(span, adjust=False)` sobre el cierre diario): 8/32, 16/64, 32/128, 64/256.
2. Volatilidad del precio: desviación exponencial (span 35, como `robust_vol_calc` de pysystemtrade) de las
   diferencias diarias del cierre. Pronóstico crudo de cada par = (rápida − lenta) / esa volatilidad.
3. Escala de cada par = 10 / media de |pronóstico crudo| en los **90 días anteriores** al bloque de prueba, con
   las 12 monedas juntas. Nunca se usa el bloque de prueba. Cada par se escala y se corta en ±20; el pronóstico
   final es el promedio de los cuatro pares, cortado en ±20.
4. Tamaño: fracción del capital = (pronóstico / 10) × 1% / volatilidad diaria del rendimiento, cortada en ±50%.
   Un pronóstico de 10 apunta a ~1% de oscilación diaria del capital por posición.
5. Solo las 3 monedas con mayor |pronóstico|; si la suma de |fracciones| pasa de 100% (1x), se reducen todas
   en proporción.
6. Cada cierre diario fija el objetivo; se opera en la **apertura del día siguiente**. Una posición abierta solo se
   ajusta si el objetivo cambia más de 10% (en unidades); abrir y cerrar se hacen siempre. Sin stops.
7. Costes: comisión 0,05% y deslizamiento 0,02% por lado sobre lo operado; financiación real (el largo paga si es
   positiva, el corto cobra).
8. Walk-forward: bloques de 30 días; la escala se reestima al empezar cada bloque con los 90 días anteriores. El
   capital (1.000 USDT) y las posiciones siguen de un bloque al siguiente.

## Cómo se juzga (fijado ahora)

- **Pasa a práctica** solo si su neto/caída (caída con el cierre diario) supera al de la mesa en **los dos
  años**. "La mesa" = la mesa de práctica actual: `mesa_r3` con el freno de régimen b (BTC sobre su media de 50
  días). Referencias de `docs/research/mesa/`:
  - 2024-10-12 → 2025-10-12: `mesa_r3` +17,6% / caída 58,18% / neto/caída 0,30; con freno b +78,2% / 46,89% /
    1,67.
  - 2025-10-13 → 2026-10-13: `mesa_r3` −65,5% / 75,5% / −0,87; con freno b −7,4% / 35,75% / −0,21.
- También se informa contra `mesa_r3` sin freno y contra comprar y mantener BTC, por trimestre.
- Menos de 100 operaciones en un año se informa como "muestra corta".
- El dinero real no cambia por este estudio en ningún caso.
