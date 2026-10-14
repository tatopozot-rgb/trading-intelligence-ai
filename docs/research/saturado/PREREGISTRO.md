# Preregistro: filtro de "lado saturado" para la mesa (2026-10-14)

Escrito el 2026-10-14, **antes** de correr nada (pedido del líder, `docs/inteligencia/2026-10-14.md`). Nada de
lo de abajo se ajusta después de ver el resultado.

## Datos

Interés abierto (contratos, `sum_open_interest`) de los archivos `metrics` de 5 minutos de
`data.binance.vision`, las 12 monedas de la mesa. La mesa se repite exactamente como en `research_mesa`
(`mesa_r3`, velas de 5 minutos, costes y financiación reales, bloques de 30 días con 1.000 USDT).

Los mismos dos años que `docs/research/mesa/`: 2024-10-12 → 2025-10-12 y 2025-10-13 → 2026-10-13.

## Frenos de base (la mesa de práctica de hoy)

- **Régimen b:** solo largos, y solo mientras el último cierre diario de BTC esté sobre su media de 50 días; si
  no, fuera y las posiciones abiertas se cierran (`regime_btc_sma: 50`).
- **Eventos:** sin entradas nuevas de 2 h antes a 2 h después de cada decisión FOMC y dato de IPC de EE. UU.
  (como `config/eventos.json`, `hours: 2`; fechas de `research_mesa.FOMC_DAYS` y `CPI_DAYS`).

## Filtros candidatos (solo impiden entradas nuevas; las posiciones abiertas siguen)

- **L5 / L10 / L15:** sin largos nuevos si el interés abierto subió más de 5 / 10 / 15% en 24 h con el precio
  plano (cambio de 24 h entre −2% y +2%).
- **S12 / S24:** sin cortos nuevos durante 12 / 24 h después de una cascada de liquidaciones de largos:
  interés abierto −5% o más en 24 h y precio −3% o más en 24 h.

Sin dato de interés abierto, no hay filtro.

## Dos montajes

1. **Con los dos frenos** (la mesa de práctica): base = régimen b + eventos; luego la base + cada filtro. Con el
   régimen b la mesa no abre cortos, así que S12 y S24 no pueden cambiar nada; se informan igual.
2. **Solo freno de eventos** (sin régimen), para que el filtro de cortos se pueda medir: base = eventos; luego
   la base + cada filtro.

## Cómo se juzga (fijado ahora)

Un filtro **ayuda** si, en el montaje 1 (o en el 2 para S12 y S24), mejora el neto/caída de su base en **los
dos años**, sin quitar más de la mitad de las operaciones. Si ayuda, se propone para la práctica; nunca para el
dinero real sin la revisión del líder y el dueño. Se publica el resultado tal cual, ayude o no.
