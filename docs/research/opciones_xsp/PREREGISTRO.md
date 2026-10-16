# Preregistro: spreads de compra de 1 USD en XSP (2026-10-16)

Escrito el 2026-10-16, **antes** de correr nada. Encargo del líder (2026-10-16): probar los spreads de XSP de 1 USD de
ancho con las comisiones reales de Interactive Brokers, en los dos años, y pasar el Sharpe deflactado
(`docs/opciones/2026-10-16.md`). Las 4 pruebas están anotadas como "pendiente" en `docs/research/REGISTRO_PRUEBAS.md`
en este mismo commit. Nada se cambia después de ver el resultado.

## Datos

- Cierres diarios del S&P 500 (FRED, serie SP500) y del VIX (Cboe, `cdn.cboe.com`; respaldo FRED VIXCLS).
  XSP = SPX / 10. (Corrección antes de tener resultados: la primera corrida falló al bajar los datos de Cboe/Stooq.)
- **No hay precios grabados de opciones.** Cada opción se valora con Black-Scholes usando el VIX del día como
  volatilidad para los dos strikes, tasa 4% y dividendo 1,3% al año. Es un modelo, no un registro real.

## Costes (IBKR Pro, `docs/opciones/2026-10-16.md`)

- Por contrato y por lado: comisión 0,65 USD + cámara (OCC) 0,025 + tasa de la bolsa 0,30 (supuesta) = 0,975 USD.
  Un spread son 2 contratos: 1,95 USD al entrar. El mínimo de 1 USD por orden no aplica (1,30 > 1).
- Deslizamiento: 0,03 por opción y por lado (3 USD por pata), en contra al entrar.
- Se mantiene hasta el vencimiento: XSP es europea y se liquida en efectivo, sin comisión de salida.

## Las dos reglas

1. **Spread alcista mensual siempre:** el primer día de cada bloque de 21 días de bolsa se compra una call de XSP con
   strike = XSP redondeado al entero más cercano y se vende la call de strike +1. Vence 30 días naturales después
   (XSP tiene vencimientos diarios; si cae en día sin bolsa, se usa el día de bolsa anterior). Se liquida al cierre
   del SPX del vencimiento: valor = min(max(XSP − K1, 0), 1) × 100. Un spread a la vez, 1 contrato. Si el spread anterior
   todavía no venció el primer día del bloque, se entra el día en que vence (después de cobrarlo).
2. **Lo mismo, solo si el SPX cierra sobre su media de 200 días** el día de entrada. Si no, ese mes queda en efectivo.

Capital: 200 USD al empezar cada año (el monto que el Líder dio para opciones). Si el capital no alcanza para un
spread, no se entra. El efectivo no gana interés en la prueba.

## Sensibilidad

Costes y deslizamiento al doble en las dos reglas (solo informativa).

## Cómo se juzga (fijado ahora)

- Años: 2024-10-12 → 2025-10-12 y 2025-10-13 → 2026-10-13 (los mismos del registro). Un spread que vence después
  del fin del año se marca a modelo ese último día.
- **Pasa** solo si, en **los dos años**: neto positivo después de costes, mejor que dejar el dinero quieto (0%) y
  mejor que el 4% que habría dado una cuenta de ahorro en dólares; **y** Sharpe deflactado de 2025-26 de al menos
  0,95 con N = las decisorias del registro (259 con estas 2) y V = 1/T, sobre rendimientos diarios del capital marcado.
- Referencias (no cuentan): comprar y mantener el SPX con 200 USD.
- Con ~12 spreads por año siempre es "muestra corta" (menos de 100 operaciones).
- **Advertencia fijada ahora:** aunque pase, no va a práctica sin repetir la prueba con precios reales de opciones
  (datos con retraso de IBKR o Cboe DataShop). El VIX no es la volatilidad de cada strike: la inclinación (skew) real
  puede hacer el spread más caro o más barato que el modelo.
- No se toca `config/`, `live/` ni los límites.
