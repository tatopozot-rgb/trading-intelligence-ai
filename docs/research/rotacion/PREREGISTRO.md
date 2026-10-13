# Pre-registro: rotación por momentum en el top 30 "de cada día" (2026-10-13)

Escrito **antes** de ver ningún resultado de esta prueba. El líder lo pidió después del estudio
`rotacion_2026-10-13.md`, donde la rotación sobre el top 30 de hoy ganó +149,7% pero no contó por sesgo de
supervivencia (la lista de hoy son las monedas que ya subieron). Aquí se corrige ese sesgo y no se ajusta nada.

## Regla única (fija, no se re-ajusta)

Tomada del estudio anterior: es la combinación fija que mejor salió en el top 30 (14 días, diario, largo 3,
filtro BTC). Como se eligió mirando aquella prueba sesgada, **el año ciego de abajo es el que decide**.

- **Universo de cada día:** perpetuos USDⓈ-M de Binance cotizados en USDT (sin contratos trimestrales, sin
  stablecoins ni índices como BTCDOM), incluidas las monedas que después dejaron de cotizar. En cada fecha se
  ordenan por **volumen en USDT de los 30 días anteriores** (hasta el día de ayer) y se toman las **30 primeras**.
  Una moneda necesita 30 días completos de historia antes de esa fecha para entrar.
- **Señal:** a las 00:00 UTC de **cada día**, se ordenan esas 30 por su **rendimiento de 14 días**.
- **Posición:** **largo en las 3 primeras**, un tercio del capital cada una. Solo si el cierre diario de BTC de
  ayer está **por encima de su media de 50 días**; si no, sin posiciones. Una moneda que sigue entre las 3 no se
  toca. Sin cortos.
- **Costes y tamaño:** como el estudio anterior: comisión 0,05% y deslizamiento 0,02% por lado, financiación real
  cada hora, 1.000 USDT, 1x, máx. 3 posiciones de 50% como máximo. Velas de 1 hora de los **perpetuos** (archivo
  público `data.binance.vision`, futuros USDⓈ-M).
- **Ventanas:** 30 días, cada una empieza con 1.000 USDT; el resultado de un año es la suma de 12 ventanas. La
  caída máxima se mide en % de los 1.000 USDT.

## Periodos

1. **Año ciego:** las 12 ventanas de 30 días que terminan donde empieza el año 2 (≈ 2024-10 a 2025-10). Nadie lo
   ha mirado con esta regla.
2. **Año 2:** las 12 ventanas más recientes (≈ 2025-10 a 2026-10). Ya se vio con la lista de hoy; aquí solo
   se informa.

En los dos: por trimestre, contra `mesa_r3` (repetida en velas de 5 min, con el mismo deslizamiento) y contra
comprar y mantener BTC en las mismas ventanas.

## Sensibilidad

En cada año se buscan las **2 monedas que más ganancia aportaron** y se repite la prueba **sin ellas** en el
universo (entra la 31.ª, la 32.ª, ...). Si sin ellas deja de ganar, la estrategia depende de la suerte con una
o dos monedas.

## Qué es pasar (todo en el año ciego)

1. 100 operaciones o más.
2. Neto positivo **y** neto/caída mejor que `mesa_r3` en las mismas ventanas.
3. Positiva en al menos 3 de los 4 trimestres completos.
4. Sin las 2 monedas que más aportaron, el neto sigue positivo.

Si pasa, se propone práctica con dinero ficticio (no dinero real). Si no pasa, se informa así, sin buscar otra
combinación que sí pase.

Información adicional, que **no** decide: el walk-forward de las 18 combinaciones del estudio anterior sobre el
mismo universo de cada día.
