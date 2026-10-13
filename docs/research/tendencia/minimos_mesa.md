# Los "rechazos por mínimo" de la mesa no son por el mínimo: son por falta de capital (2026-10-13)

Pregunta del líder: ¿por qué la repetición de `mesa_r3` rechazó tantas entradas "por el mínimo de Binance" en dos
ventanas (190 en la de 2025-08-08 y 105 en la de 2025-10-12, contra 0 a 24 en las demás), y eso sesga el resultado?

Se repitieron **solo esas dos ventanas** (una corrida, dos procesos), con las mismas reglas que el informe de tendencia.
Cada rechazo guardó cuánto permitía cada tope de tamaño. Datos completos: `minimos_mesa_datos.md` y
`minimos_mesa.json`.

## Qué pasó

| Ventana | Rechazos | Episodios (señales distintas) | Posiciones abiertas | Capital ya usado | Tope que fijó el tamaño |
|---|---|---|---|---|---|
| 2025-08-08 a 2025-09-07 | 190 | 62 | siempre 2 | 95-102% | siempre "capital libre con 1x" |
| 2025-10-12 a 2025-11-11 | 105 | 32 | siempre 2 | 91-102% | siempre "capital libre con 1x" |

1. **El mínimo de Binance no fue la causa.** Los otros dos topes daban de sobra: por riesgo hasta el stop, una mediana
   de 2.622 y 1.108 USDT; por el tope de 50% por posición, 525 y 386 USDT. Los mínimos son 5 USDT (100 para BTC y 20
   para ETH). Lo que quedaba libre era de 0 a 64 USDT, porque **dos posiciones de hasta el 50% ya usaban todo el
   capital**. La regla recorta la cantidad a lo que cabe en 1x, la cantidad queda casi en cero, y entonces el chequeo
   del mínimo la rechaza. El contador lo anota como "sin mínimo", pero en realidad es "sin capital".
2. **La distancia al stop no importa aquí.** Las medianas fueron 4,7% y 8,5%; el tamaño lo puso el capital libre, no
   el stop.
3. **Monedas.** En 2025-08: TRX (54 rechazos), LINK (41), AVAX (32), ETH (18), DOGE (17) y ADA (16). En 2025-10: AVAX
   (25), ADA (24), DOGE (23) y DOT (16). Son las monedas que dieron señal mientras había dos posiciones abiertas, no
   monedas con problemas de mínimo.
4. **El número está inflado.** El contador suma una vez por cada vela de 5 minutos en que la señal se repite. Las 295
   rechazos son en realidad 94 señales distintas.
5. **¿Se perdió algo bueno?** Mirando 24 h hacia adelante, como con los vetos: de las 94 señales, 87 no tocaron ni el
   stop ni la meta de 3R, y 7 habrían tocado primero el stop. Ninguna habría llegado primero a la meta.

## ¿Sesga el resultado de mesa_r3?

**No en contra de la mesa.** Los rechazos son señales que la mesa no podía tomar por falta de capital. En la vida real
pasaría lo mismo con la misma configuración (1x, 50% por posición). Y las que se pudieron medir habrían perdido. El
−53% de 2025-26 y el +4,9% de 2024-25 no cambian por esto.

Lo que sí deja ver es otra cosa sobre la configuración: **con 1x y hasta 50% por posición, la mesa casi nunca puede
tener 3 posiciones abiertas**, aunque el límite diga 3. En la práctica opera con 2 cuando las dos primeras salen
grandes.

## Recomendación (para quien lleve la mesa; no se cambió nada en vivo)

- Que el contador distinga "sin capital" de "por debajo del mínimo", y cuente señales distintas en lugar de velas. Así
  los informes no confunden.
- Si se quieren de verdad 3 posiciones a 1x, el tope por posición debería ser cerca de 33%. Eso es un cambio de
  límites y queda para el dueño y el líder.
