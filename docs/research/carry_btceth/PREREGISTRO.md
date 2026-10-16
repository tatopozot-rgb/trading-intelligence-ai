# Preregistro: carry de financiación en BTC y ETH, y si cabe en 31 USDT (2026-10-16)

Escrito el 2026-10-16, **antes** de correr nada. Encargo del líder (2026-10-16): spot comprado + perpetuo vendido
(neutral al precio) en BTC y ETH, entrando solo cuando la financiación paga los costes; medir el rendimiento neto
real, el riesgo de liquidación con 31 USDT y los mínimos de orden. Es ingreso, no una apuesta de dirección. Usa la
máquina ya probada de `research_carry.py` (2026-10-13). Las 4 pruebas están anotadas como "pendiente" en
`docs/research/REGISTRO_PRUEBAS.md` en este mismo commit. Nada se cambia después de ver el resultado.

## Regla

- BTCUSDT y ETHUSDT, cada uno por separado. Velas de 1 hora de Spot (`data-api.binance.vision`) y del perpetuo, y
  la financiación real (`data.binance.vision`), desde 2020-01-01.
- Cada 8 h (00, 08 y 16 UTC) se mira la media de los últimos 21 pagos de financiación (7 días).
- **Entrar** si esa media es al menos **0,0042% cada 8 h**: a ese ritmo la financiación paga en 30 días los costes
  de entrar y salir. Costes por pata y lado: spot 0,10% (sin descuento BNB) y perpetuo 0,05%, más 0,02% de
  deslizamiento en cada una: ida y vuelta 0,38% del tamaño de una pata, que es 0,19% del capital usado.
- **Salir** si la media baja de 0%.
- Mitad del capital compra spot y la otra mitad es el margen del corto de la misma cantidad (1x en total).
  Si la pérdida del corto se come la mitad de su margen, se cierran las dos patas y se reabren al precio de ese
  momento, pagando los costes ("rebalanceo", como en `research_carry`).

## Pruebas

- **Decisorias (2):** la regla en BTC y la regla en ETH.
- **Sensibilidad (2):** "siempre dentro" en BTC y en ETH (sin filtro de entrada).

## Cómo se juzga (fijado ahora)

- Una sola corrida continua desde 2020; cada año se mide contra el capital al empezar ese año: 2024-10-12 →
  2025-10-12 y 2025-10-13 → 2026-10-13. También se informa todo el periodo y cada trimestre.
- **Pasa a práctica** si cumple las dos cosas del protocolo: neto/caída mayor que la mesa en los dos años (1,67 y
  −0,21) **y** Sharpe deflactado de 2025-26 de al menos 0,95 con N = las decisorias del registro (254 con estas 2)
  y V = 1/T, sobre rendimientos diarios.
- Se informa al lado lo que daría el efectivo a 4% al año, porque un ingreso que no gana al efectivo no sirve.

## 31 USDT (medición, no prueba)

- Mínimos de orden: se leen en la corrida de `exchangeInfo` público de Spot (`data-api.binance.vision`) y, si
  responde, del de Futuros; si Futuros no responde, se usan 100 USDT para BTCUSDT y 20 USDT para ETHUSDT, marcados
  "no verificado" para que Claude local los confirme.
- Con 31 USDT se busca la configuración más chica posible: la pata spot igual al mínimo del perpetuo, y el resto
  como margen del corto. Se calcula su apalancamiento, la subida que lo liquida (margen de mantenimiento 0,5%) y
  cuántas veces desde 2020, dentro de las entradas de la regla, el precio subió más que eso antes de salir. Se
  informa también el ingreso esperado en USDT por año.
- No se toca `config/`, `live/` ni los límites. Nada de esto mueve dinero real.
