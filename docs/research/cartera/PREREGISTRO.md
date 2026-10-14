# Preregistro: cartera mesa de práctica + EWMAC (2026-10-14)

Escrito el 2026-10-14, **antes** de correr nada. Hipótesis nueva aprobada por el líder después del veredicto de
EWMAC (`docs/research/ewmac/`): EWMAC no pasó sola, pero gana donde la mesa con freno pierde o se queda fuera.
Nada de lo de abajo se ajusta después de ver el resultado; otro peso u otra regla serían otra hipótesis.

## Las dos patas (reglas actuales, sin cambios)

- **Mesa de práctica:** `mesa_r3` (velas de 5 minutos, repetida exactamente como en `research_mesa`) con los
  frenos con los que corre hoy en práctica: régimen b (`regime_btc_sma: 50`: solo largos y solo con BTC sobre su
  media de 50 días; si no, fuera y se cierran las posiciones) y el freno de eventos (sin entradas de 2 h antes a
  2 h después de cada FOMC e IPC). **Sin** la inclinación del tamaño por sentimiento (quitada en f8912db): se
  vuelve a medir con las reglas de hoy. Sesiones de 30 días, cada una empieza con su capital (límite de pérdida
  45%, meta +58%), como la mesa.
- **EWMAC:** exactamente la regla preregistrada en `docs/research/ewmac/PREREGISTRO.md`, curva continua.

## Cómo se juntan (fijado ahora)

- Los años son los mismos 12 bloques de 30 días de `docs/research/mesa/`: desde 2024-10-12 y desde 2025-10-13.
- La mesa se convierte en una curva diaria: dentro de cada sesión de 30 días, su capital al cierre de cada día
  (00:00 UTC) dividido por el capital de inicio de la sesión; las sesiones se encadenan (el rendimiento de cada
  sesión se compone sobre el anterior). Si una sesión termina antes (límite o meta), su capital queda plano hasta
  el final de la sesión.
- EWMAC se toma con su capital al cierre de cada día UTC de los mismos 360 días.
- **Rebalanceo mensual:** al empezar cada sesión de 30 días, la cartera se reparte otra vez con los pesos fijos;
  dentro de la sesión, cada pata sigue su propia curva. Se cobra 0,07% (comisión + deslizamiento) sobre lo que se
  mueve de una pata a la otra en cada rebalanceo.
- **Pesos:** 50/50 y 70/30 (70% mesa, 30% EWMAC). Ningún otro.
- Caída máxima con el capital diario de la cartera.

## Cómo se juzga (fijado ahora)

Un peso **pasa** solo si cumple las dos cosas en **los dos años**:

1. Neto/caída de la cartera mayor que el de la mesa de práctica sola (misma curva diaria encadenada).
2. Caída máxima de la cartera menor que 35% (el límite de pérdida del dueño es 45%; EWMAC sola llegó a 43%).

Se informa también por trimestre y contra comprar y mantener BTC. Se publica tal cual, pase o no. El dinero real
no cambia por este estudio.
