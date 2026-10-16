# Preregistro: cartera de tendencia multi-mercado en XM (2026-10-16)

Escrito el 2026-10-16, **antes** de correr nada y antes de recibir los datos. Encargo del líder (2026-10-16): Renato
operará en XM, en cualquier mercado, con unos 200 USD reales. Se busca atacar el problema de "gana un año, pierde el
otro" diversificando: una regla de tendencia conocida, con riesgo igual por mercado, aplicada a la vez a 10-15
instrumentos poco correlacionados, con los costos reales de XM. Pocas variantes: la cartera es **una** prueba
decisoria y dos de sensibilidad, anotadas como "pendiente" en `docs/research/REGISTRO_PRUEBAS.md` en este mismo
commit. Nada se cambia después de ver el resultado.

## Datos

- Velas diarias y fichas leídas de la cuenta **DEMO** de XM (MT5, solo lectura) por Claude local, en
  `docs/research/cartera_xm/datos/`. Sin cuenta, sin saldo y sin claves en esos archivos.
- 15 mercados pedidos, fijados ahora:
  - forex: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF;
  - índices: US500, US100, GER40, JP225 (versiones Cash);
  - materias primas: GOLD, SILVER, OIL (Cash);
  - cripto: BTCUSD, ETHUSD.
- Un mercado que XM no tenga, o sin historia suficiente, queda fuera. No se agrega ninguno después.
- Dos años de prueba, los de siempre: 2024-10-12 → 2025-10-12 y 2025-10-13 → 2026-10-13. Los indicadores se
  calientan con la historia anterior.

## Regla (EWMAC de Carver, sin ajuste)

1. Cuatro pares de medias exponenciales sobre el cierre diario de cada mercado, en sus propios días de cotización:
   8/32, 16/64, 32/128 y 64/256.
2. Pronóstico de cada par = (rápida − lenta) / volatilidad del precio (desviación exponencial de las diferencias
   diarias, span 35) × la escala fija de Carver (*Systematic Trading*, 2015): 5,3 / 3,75 / 2,65 / 1,87.
3. Cada par se corta en ±20. El pronóstico final es el promedio de los pares disponibles × 1,1, cortado en ±20.
   No se estima nada con los datos.
4. Tamaño en USD = (pronóstico / 10) × 0,25% del capital / volatilidad diaria del rendimiento del mercado. Con 15
   mercados poco correlacionados, eso apunta a cerca de 1% diario de oscilación de la cartera.
5. Topes: 2 veces el capital por posición y 6 veces en total (se reducen todas en proporción).
6. Lotes de XM: se redondea al paso del lote. Menos de medio lote mínimo es no tener posición; entre medio y un lote
   mínimo, un lote mínimo. Si el lote mínimo solo ya pasa del tope de 2 veces, no hay posición.
7. El cierre de cada día fija el objetivo; se opera en la apertura del siguiente día que ese mercado cotice. Una
   posición solo se ajusta si el objetivo cambia más de 10%; abrir, cerrar y dar vuelta se hacen siempre. Sin stops.
8. Ganancias en la moneda del mercado, pasadas a USD con el par de forex correspondiente (JPY, EUR, CAD, CHF...).

## Costos de XM (sin comisión)

- Spread: medio spread por lado sobre lo operado. Se usa el mayor entre el spread registrado en la vela y el spread
  leído en la ficha.
- Swap: el de la ficha (compra o venta, en su modo: puntos, dinero o % anual), por cada noche con posición, triple la
  noche del día de rollover de la ficha (en los mercados que no cotizan los fines de semana).
- Límite conocido: el swap y el spread de la ficha son los de hoy; los históricos pudieron ser otros.

## Filas

1. **Cartera EWMAC con 200 USD y lotes de XM** — decisoria (la que cuenta en N).
2. Misma regla con 100.000 USD — sensibilidad: muestra la regla sin el efecto del lote mínimo.
3. 200 USD con spread y swap ×2 — sensibilidad.

## Listones

1. Neto/caída (caída con el cierre diario) mayor que el de la mesa de práctica en **los dos años**:
   1,67 en 2024-25 y −0,21 en 2025-26.
2. Sharpe deflactado ≥ 0,95 en 2025-26, con N = 258 decisorias (257 + esta) y V = 1/T, sobre los rendimientos de
   días naturales.

Pasa solo con los dos, en la fila 1. También se informa cuántos mercados caben con 200 USD: el lote mínimo de cada
uno contra su tamaño de riesgo igual a pronóstico 10. Cabe si el lote mínimo no pasa del doble de ese tamaño ni de
2 veces el capital.

El dinero real no cambia por este estudio. Abrir una cuenta real o mover dinero exige la frase escrita del dueño.
