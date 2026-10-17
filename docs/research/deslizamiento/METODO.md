# Deslizamiento real: señal contra ejecución (tema 7, 2026-10-17)

Encargo del líder: medir en puntos básicos (1 pb = 0,01%) cuánto peor que la señal salen las entradas y salidas
cerradas de las prácticas de futuros 1x y 3x, y del real cuando cierre; compararlo con el 0,02% (2 pb) por lado que
suponen los backtests (`research_mesa.SLIPPAGE`). Es una medición, no una prueba de estrategia: no suma filas al
registro.

## Qué mide

- **Positivo es en contra.** Comprar por encima de la referencia o vender por debajo.
- **Real, entrada:** precio medio de Binance (`orders.json`) contra el ask o bid del plan (evento OPEN de
  `state.json`), emparejados por moneda, lado y 5 minutos.
- **Real, salida:** precio medio de salida de Binance contra el stop o la meta que la cerró. Binance cierra con sus
  propias órdenes (STOP_MARKET, TAKE_PROFIT_MARKET), que no pasan por `orders.json`; por eso hace falta un CSV
  exportado en la PC, solo lectura, con `symbol, closed, why, exit_ref, exit_fill`.
- **Práctica, entrada:** el llenado simulado (ask o bid) contra la apertura de la vela de 1 minuto. Es medio spread.
- **Práctica, salida:** la práctica llena justo en el stop o la meta, así que su deslizamiento es 0 por
  construcción. Se re-estima con el **modelo de hueco de 1 minuto**: la primera vela de 1 minuto que toca el nivel
  llena en su apertura si abrió más allá; si no, en el nivel. Es un piso: lo que pasa dentro del minuto no se ve.

## Cómo se corre (en la PC, donde están los archivos)

```
python -m trading_intelligence.backtesting.research_deslizamiento ^
  --practica practica_1x=<carpeta 1x>\paper.json practica_3x=<carpeta 3x>\paper.json ^
  --real-estado <carpeta real>\state.json --real-ordenes <carpeta real>\orders.json ^
  --real-salidas <csv de salidas reales>
```

Solo lee archivos y velas públicas de 1 minuto de Binance Futuros. No manda órdenes ni usa claves. Escribe
`docs/research/deslizamiento/deslizamiento_<fecha>.{md,json,csv}` con precios, horas y puntos básicos: sin
cantidades, sin resultados y sin saldos, así que se puede subir al repo público.

## Cómo se lee

- Con menos de 30 operaciones por fuente el intervalo de la media es ancho y no decide nada. Hoy hay unos 5
  cierres de práctica y ninguno real.
- Si el intervalo de 90% de la media queda entero sobre 2 pb, el supuesto de los backtests es optimista y se
  re-corre la mesa con el número medido. Si queda bajo 2 pb, el supuesto es prudente.
