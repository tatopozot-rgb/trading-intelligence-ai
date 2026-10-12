# Preregistro: dos reglas de tendencia fijas (2026-10-12)

Escrito el 2026-10-12, **antes** de mirar el año de prueba. Las reglas salen de la tabla "combinaciones fijas"
del estudio de tendencia (2025-10-12 a 2026-10-12), donde fueron las mejores en retrospectiva. Eso no prueba
nada: se eligieron mirando ese año. Por eso se prueban, sin cambiar nada, en el año anterior, que no se usó
para elegirlas: **2024-10-12 a 2025-10-12**.

Nada de lo de abajo se ajusta después de ver el resultado. Si una regla cambia, es una regla nueva y necesita
otro año sin mirar.

## Reglas comunes

- Monedas: las 12 de `two_way_backtest.SYMBOLS` (BTC, ETH, BNB, SOL, XRP, DOGE, ADA, LINK, AVAX, LTC, TRX, DOT),
  largos y cortos. Precio Spot de Binance como aproximación del perpetuo USDⓈ-M.
- Velas de 1 hora para ejecutar; velas diarias UTC (00:00 a 00:00) para las señales. Una señal del cierre diario
  se llena en la apertura de la primera hora del día siguiente.
- Costes: comisión 0,05% por lado, deslizamiento 0,02% por lado, financiación real de cada 8 h (0,01% si falta).
- Capital 1.000 USDT, 1x, una posición como máximo 50% del capital, 3 posiciones a la vez, todas dentro del
  capital. Si hay más señales que huecos, entran las más fuertes. Sin filtro de régimen de BTC.
- Los parámetros no se vuelven a ajustar nunca (sin walk-forward). La simulación empieza el 2024-10-12 con
  1.000 USDT; los indicadores se calientan con los 310 días anteriores.

## Regla A: `ema` 1d 20/50, stop de 3 ATR

- EMA de 20 y de 50 días sobre el cierre diario (`ewm(span, adjust=False)`); ATR de 14 días (media simple del
  rango verdadero diario).
- Entrada larga cuando la EMA 20 cruza por encima de la EMA 50 en un cierre diario; corta cuando cruza por debajo
  (solo desde la vela 50). Fuerza = |EMA20 − EMA50| / ATR.
- Salida: el cruce contrario (en la apertura siguiente) o el stop que sigue: cierre − 3 ATR en largos
  (cierre + 3 ATR en cortos), recalculado en cada cierre diario, solo se mueve a favor y se mira cada hora con el
  máximo / mínimo. Un hueco por encima del stop se llena en la apertura.
- Tamaño: 5% del capital en riesgo hasta el stop, con los topes de arriba.
- En el código: `GRIDS["ema"]` con `{"tf": "1d", "rapida": 20, "lenta": 50, "atr": 3}`.

## Regla B: `tsmom` 60 días

- Cada cierre diario, por moneda: rendimiento de 60 días; volatilidad = desviación de los rendimientos
  logarítmicos diarios de 20 días × √365; puntaje = rendimiento / volatilidad.
- Se eligen las 3 monedas con mayor |puntaje|; largo si el rendimiento es positivo, corto si es negativo.
- Se sale cuando la moneda deja de estar entre las 3 primeras o su rendimiento cambia de signo (en la apertura
  siguiente). Sin stop.
- Tamaño: capital × mín(50%, 20% / volatilidad anual de la moneda), con los topes de arriba.
- En el código: `GRIDS["tsmom"]` con `{"dias": 60, "vol": 20, "mantener": 3}`.

## Cómo se juzga (fijado ahora)

Se compara con `mesa_r3` (la mesa, velas de 5 min, cada ventana de 30 días con 1.000 USDT) y con comprar y
mantener BTC, en las mismas ventanas de 30 días del año de prueba. Una regla **se sostiene** si cumple todo:

1. Neto positivo en el año de prueba.
2. Neto / caída máxima (caída medida con el cierre diario) mejor que el de `mesa_r3` en las mismas ventanas.
3. Positiva en al menos el 75% de los trimestres del año (redondeando hacia arriba).
4. Al menos 100 operaciones. La regla A hizo solo 28 operaciones en el año en que se eligió, así que se espera
   que no llegue: si cumple 1-3 con menos de 100 operaciones, se informa como "muestra corta, favorable",
   no como prueba.

Se publica el resultado tal cual, gane o pierda.

Comando: `python -m trading_intelligence.backtesting.research_tendencia --hasta 2025-10-12 --preregistro`
