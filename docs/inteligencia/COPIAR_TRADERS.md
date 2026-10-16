# ¿Sirve copiar a los top traders? (revisión 2026-10-16)

Pregunta del dueño (2026-10-16): "copiar a los top traders, ¿serviría? Creo que no, porque uno ve sus operaciones
tarde". Se probó con datos, siguiendo `docs/research/PROTOCOLO.md`: preregistro en
`docs/research/copiar/PREREGISTRO.md`, informe en `docs/research/copiar/`, filas 318–321 de
`docs/research/REGISTRO_PRUEBAS.md`.

## Resumen en simple

1. **No sirve.** Copiar a los 10 que más ganaron el año anterior habría perdido **−65,6%** en 2025-26, con una
   caída de 73,7%. Los 10 "más parejos" perdieron −51,7%. BTC solo perdió −27,7% ese año.
2. **Los top de hace un año no siguen arriba.** De los 10 mejores de octubre 2025: 9 perdieron plata, 7 cayeron más
   de 50%, **5 se quemaron por completo (−100%)** y 3 están cerradas. Solo 2 siguen en el top 10.
3. **Ganar mucho un año predice perder el siguiente.** La correlación de rangos entre un año y el siguiente es
   **−0,48** (p 0,006): los que más subieron fueron los que más arriesgaron, y eso se cobra después.
4. **Y esto es el mejor caso.** Se usaron bóvedas de Hyperliquid, donde el seguidor hace las mismas operaciones del
   líder **sin retraso**. Copiar en Binance, viendo las operaciones tarde, solo puede salir peor. Renato tenía razón,
   y el retraso ni siquiera es el problema principal: el problema es que el "top" es suerte con mucho riesgo.

## Por qué Hyperliquid y no Binance

- Binance solo muestra 7 a 180 días de cada lead trader, y los que quiebran desaparecen de la lista. No se puede
  reconstruir "el top de hace un año".
- Las bóvedas de Hyperliquid tienen todo su historial en la cadena, y la lista incluye las **cerradas** (9.477
  bóvedas, 4.267 con edad suficiente). Las comisiones ya van dentro; al final se descontó el 10% de la ganancia que
  cobra el líder.
- Regla: el día de inicio, bóvedas con 1 año o más de vida, 10.000 USD o más y ganancia positiva en el año previo.
  Se compran las 10 mejores en partes iguales y se mantienen 1 año.

## Resultados

| Año | Regla | Neto | Caída | Neto/caída | Mesa | Pasa |
|---|---|---|---|---|---|---|
| 2024-25 | A, los que más ganaron | +14,7% | 17,3% | 0,85 | 1,67 | no (muestra corta: 1 sola bóveda elegible) |
| 2025-26 | A, los que más ganaron | −65,6% | 73,7% | −0,89 | −0,21 | no |
| 2025-26 | B, los más parejos (ganancia/caída) | −51,7% | 58,9% | −0,88 | −0,21 | no |
| 2025-26 | A, top 30 (sensibilidad) | −35,4% | 47,1% | −0,75 | — | — |

Sharpe deflactado 2025-26: 0,0 en las dos (listón 0,95; se calculó con N = 259 y, con las 2 de opciones que entraron el mismo día, N = 261: sigue en 0,0). Mediana de las 32 bóvedas elegibles en 2025-26: −26,9%;
25 de 32 perdieron.

Las 10 mejores de octubre 2025 y su año siguiente (de `docs/research/copiar/`): +2.762% → −100%; +1.130% → −100%;
+774% → −2%; +422% → −9%; +292% → −92%; +223% → −100%; +210% → −100%; +209% → +14%; +171% → −66%; +145% → −100%.

## Foto de Binance Futures (informativa)

Los 2.000 lead traders de mayor ROI a 180 días (solo los que siguen vivos, así que la foto sale **mejor** de lo real):

- Los líderes ganaron 20,4 millones de USDT; sus copiadores, 9,1 millones: menos de la mitad.
- 722 tienen a sus copiadores en ganancia y 586 en pérdida (el resto no tiene copiadores).
- Los 20 de mayor ROI muestran una mediana de **+4.279%** con una caída de **41,5%**: es apalancamiento extremo, no
  habilidad repetible.

Otro estudio de 90 días en Binance, Bybit y MEXC (YieldFund, 2025; 100.236 copiadores) encontró que solo el **48%**
de los copiadores ganaba, aunque el 97% de los líderes estaba en ganancia propia
([fuente](https://yieldfund.com/is-copy-trading-profitable-a-90-day-multi-exchange-study)). El líder gana con su
entrada temprana y con la parte que cobra; el copiador entra después y paga.

## "Operar con las pérdidas buscando la ganancia"

Si la idea es **subir el tamaño después de perder para recuperar** (martingala o promediar a la baja), está
prohibida en las reglas del proyecto y es justo lo que quemó a 5 de las 10 bóvedas de arriba: funciona muchas veces
y una sola racha mala se lleva todo. Si la idea es **hacer lo contrario de los que pierden**, eso ya se midió con
el sentimiento de Binance (posiciones de los top traders y financiación, `docs/research/sentimiento/`): "no predice
nada útil" en los dos años.

## Decisión

Archivado: copiar traders o bóvedas no entra a práctica. 0 candidatas.
