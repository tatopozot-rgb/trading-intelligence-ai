# Preregistro: Supertrend de freqtrade (FSupertrendStrategy) en BTC y ETH (2026-10-18)

Escrito el 2026-10-18, **antes** de correr nada. Las reglas y el plan de prueba los fijó el líder en
`docs/inteligencia/BOTS_PUBLICOS.md` (sección 2026-10-18). Aquí solo se fija cómo se simulan. Las filas quedan
"pendiente" en `docs/research/REGISTRO_PRUEBAS.md` en este mismo commit. Datos públicos de Binance, sin cuenta, sin
clave y sin órdenes.

Código fuente, en el commit fijo
[b8a90be](https://raw.githubusercontent.com/freqtrade/freqtrade-strategies/b8a90bebebfc13a78416635166ebafdece596d3f/user_data/strategies/futures/FSupertrendStrategy.py).
Se usan sus parámetros tal cual, sin volver a optimizar.

## Indicador (copiado del código, con sus rarezas)

- Rango verdadero (TRANGE); ATR = media simple de N velas.
- Bandas: (máx + mín)/2 ± m × ATR, con la regla de bandas finales del código (empiezan en 0 en la vela N).
- Valor y sentido del Supertrend con la misma cadena de condiciones del código. "Arriba" si el cierre ≥ la línea,
  "abajo" si queda por debajo, y nada mientras la línea vale 0.
- Compra: (m, N) = (4, 8), (7, 9) y (1, 8). Venta: (1, 16), (3, 18) y (6, 18).

## Señales y ejecución (como el backtest de freqtrade)

1. Las señales salen al cierre de cada vela de 1 hora. Se entra y se sale por señal en la apertura de la vela
   siguiente.
2. Entrada larga si los 3 de compra dicen "arriba" y el volumen es > 0. Entrada corta si los 3 de venta dicen
   "abajo". No se entra si salen las dos a la vez, ni si en esa vela está activa la salida del mismo lado.
3. Salida del largo: el 2.º de venta (3, 18) dice "abajo". Salida del corto: el 2.º de compra (7, 9) dice
   "arriba". Una posición a la vez por moneda.
4. Dentro de cada vela, en este orden:
   - el stop (si la vela abrió más allá, se llena en la apertura);
   - la toma de ganancia por tiempo, según la edad de la operación al abrir la vela: 10% en la primera hora, 75%
     de 30 a 60 minutos (nunca se ve con velas de 1 hora), 5% desde la hora 1 y 2,5% desde la hora 2. Se llena en
     el nivel, o en la apertura si abrió más allá;
   - el stop que sigue al precio, que se mueve con el máximo (o mínimo) de las velas anteriores: a 26,5% del
     extremo, y a 5% una vez que la ganancia del extremo llegó a 10%.
5. Costos de la mesa: 0,05% de comisión y 0,02% de deslizamiento por lado. Financiación real de Binance Futuros
   (`data.binance.vision`) cada 8 horas sobre la posición abierta: el largo paga si es positiva, el corto cobra.
6. Precio: velas de 1 hora del contado de Binance (BTCUSDT, ETHUSDT). 1.000 USDT al empezar cada año. Juntas: dos
   cuentas de 500 USDT, una por moneda, sumadas.

## Dos versiones

- **A, tal cual:** stop fijo de −26,5% y salidas del código. Cada operación usa todo el capital de su moneda, 1x.
- **B, con los frenos de la mesa:**
  - Stop a 1R de la mesa: el de `strategy.exit_plan.plan_exits` sobre las últimas 300 velas de 1 hora cerradas
    (entre 3% y 15%), en lugar del −26,5%. Las demás salidas del código siguen igual.
  - Tamaño: 2% del capital de la moneda en riesgo hasta el stop, con tope de 1x.
  - Freno de mercado (régimen b de la mesa): solo largos, y solo si el último cierre diario de BTC está sobre su
    media de 50 días. Si deja de estarlo, el largo abierto se cierra en la apertura siguiente. Sin cortos.
  - Freno de eventos: sin entradas en las 12 horas antes o después de una decisión FOMC o un dato de IPC
    (`research_mesa.macro_events`).

## Filas

Decisorias (N pasa de 266 a 272):

1. A, BTC. 2. A, ETH. 3. A, BTC y ETH juntas.
4. B, BTC. 5. B, ETH. 6. B, BTC y ETH juntas.

Sensibilidad (no cuentan, no deciden):

7. A juntas, costos ×2. 8. B juntas, costos ×2.

## Listones

1. Neto/caída mayor que la mesa de práctica en los dos años: 1,67 en 2024-25 y −0,21 en 2025-26.
2. Sharpe deflactado ≥ 0,95 en 2025-26, con N = 272 y V = 1/T, sobre los rendimientos de días naturales.

Una fila pasa solo con los dos. Se informa también contra mantener BTC. Menos de 100 operaciones en un año se marca
"muestra corta". El dinero real no cambia por este estudio.
