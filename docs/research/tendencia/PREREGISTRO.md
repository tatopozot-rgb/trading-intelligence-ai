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

---

# Preregistro 2: "BTC régimen" (2026-10-13)

Escrito el 2026-10-13, **antes** de correr ninguna prueba de esta regla. Pedido por el líder como la referencia más
simple que usan los profesionales. Se prueba sin cambiar nada en los dos años ya medidos: **2024-10-12 a 2025-10-12**
y **2025-10-12 a 2026-10-12**.

## Regla base: `btc_sma200`

- Solo BTCUSDT, solo largos, 1x. Precio Spot de Binance como aproximación del perpetuo.
- Cada cierre diario UTC: si el cierre está por encima de su media simple de 200 días, la regla quiere estar comprada;
  si no, quiere estar en efectivo.
- Se actúa en la apertura de la primera hora del día siguiente (velas de 1 hora). Al empezar cada año de prueba se
  usa la última señal conocida y se entra (o no) en la apertura de la primera hora.
- Tamaño: todo el capital (cantidad = capital / (precio × (1 + comisión))). Esto se aparta del tope de 50% por
  posición del protocolo, a pedido del líder; sin apalancamiento.
- Costes: comisión 0,05% y deslizamiento 0,02% por lado; financiación real de cada 8 h, cobrada cada hora
  (los largos pagan si es positiva; 0,01% si falta).
- Capital 1.000 USDT al empezar cada año.

## Variantes

- `btc_sma50`: igual, con la media simple de 50 días.
- `btc_sma200_stop10`: la regla base más un stop que sigue al precio: se vende si el mínimo de una hora toca el
  máximo alcanzado desde la entrada × 0,90 (un hueco por debajo se llena en la apertura). Tras salir por el stop,
  no se vuelve a entrar hasta que un cierre diario quede por debajo de la media de 200 y luego otro vuelva por
  encima (un cruce nuevo).

## Cómo se juzga (fijado ahora)

Igual que el preregistro 1, cada año por separado, contra `mesa_r3` y BTC comprar y mantener en las mismas fechas
(los números de la mesa son los de `tendencia_2026-10-12.json` y `preregistro_2025-10-12.json`):

1. Neto positivo.
2. Neto / caída máxima (caída medida con el cierre diario) mejor que el de `mesa_r3`.
3. Positiva en al menos el 75% de los trimestres (redondeando hacia arriba).
4. Al menos 100 operaciones. Se sabe de antemano que una regla de régimen opera pocas veces (decenas como mucho),
   así que no llegará: si cumple 1-3 se informa como "muestra corta, favorable", no como prueba.

Además se informa (sin ser criterio de aprobación): la caída máxima frente a la de comprar y mantener BTC, y qué parte
de la subida de BTC capturó en el año alcista y qué parte de la bajada evitó en el año bajista.

Se publica el resultado tal cual, gane o pierda.

---

# Preregistro 3: BTC por encima de las dos medias (2026-10-13)

Escrito el 2026-10-13, **antes** de correr ninguna prueba de estas reglas, a pedido del líder. Idea: `btc_sma200` evitó
mejor los años bajistas y `btc_sma50` capturó mejor los alcistas, pero `btc_sma50` se dejó engañar por rebotes en 2022;
exigir las dos medias a la vez podría juntar lo bueno de cada una.

**Advertencia de selección, escrita antes de ver nada:** estas son las variantes 4 y 5 de la misma familia, probadas
sobre los mismos datos 2020-2026 que ya se miraron para elegir la idea. Cuantas más variantes se prueban sobre los
mismos datos, más fácil es que una gane por suerte. Por eso, aunque pase, sigue siendo "muestra corta" y necesita
práctica hacia adelante (dinero ficticio) antes de contar como evidencia.

## Reglas (lo demás igual que el preregistro 2)

- Solo BTCUSDT, solo largos, todo el capital, 1x, velas de 1 hora, señal del cierre diario UTC ejecutada en la apertura
  de la hora siguiente, comisión 0,05% y deslizamiento 0,02% por lado, financiación real cada 8 h cobrada cada hora,
  1.000 USDT al empezar cada año; al empezar cada año se usa la última señal conocida.
- `btc_sma50_200`: comprado cuando el cierre diario está por encima de su media simple de 50 días **y** por encima de
  su media simple de 200 días (las dos del mismo día); si falla cualquiera de las dos, efectivo.
- `btc_sma50_200_conf2`: entra solo cuando **dos cierres diarios seguidos** cumplen las dos condiciones; sale con el
  **primer** cierre que no las cumple. Sin stop.

## Años y comparación

Seis años de prueba, del 12 de octubre al 12 de octubre: 2020-21, 2021-22, 2022-23, 2023-24, 2024-25 y 2025-26. Al lado,
en la misma tabla, `btc_sma50` y `btc_sma200` del preregistro 2 (mismas reglas, sin cambios), comprar y mantener BTC y,
en los dos últimos años, `mesa_r3` (números ya publicados).

## Cómo se juzga (fijado ahora)

Es una prueba nueva de régimen, así que se usa el criterio con la enmienda del líder del 2026-10-13. En **cada** año:

1. Neto positivo.
2. Trimestres no negativos (neto ≥ 0, un trimestre en efectivo cuenta) en al menos el 75% de los trimestres del año,
   redondeando hacia arriba.
3. Donde existe la mesa (2024-25 y 2025-26): neto / caída máxima mejor que el de `mesa_r3`.
4. Al menos 100 operaciones: no llegará (una regla de régimen opera pocas veces), así que si cumple 1-3 en todos los
   años se informa como "muestra corta, favorable en los seis años", no como prueba.

Se informan también, sin ser criterio: el crecimiento compuesto de los seis años frente a BTC y a `btc_sma50`, la caída
máxima de cada año frente a BTC y el resultado con el criterio original del preregistro 2 (trimestres positivos).

Se publica el resultado tal cual, gane o pierda.
