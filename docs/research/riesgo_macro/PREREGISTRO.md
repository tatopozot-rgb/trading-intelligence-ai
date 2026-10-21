# Preregistro: riesgo a la mitad cuando suben el bono a 10 años y el dólar (2026-10-21)

Escrito el 2026-10-21, **antes** de correr nada. Encargo del líder (teoría del tema 3, segunda vuelta,
`docs/inteligencia/2026-10-21.md`). Las filas quedan "pendiente" en `docs/research/REGISTRO_PRUEBAS.md` en este mismo
commit. Datos públicos, sin cuenta, sin clave y sin órdenes. No se toca `config/` ni `live/`.

## La regla (fija, sin afinar)

- **Bono:** rendimiento del Tesoro de EE. UU. a 10 años, `DGS10` de FRED (si FRED no responde: `^TNX` de Yahoo).
- **Dólar:** índice DXY (`DX-Y.NYB` de Yahoo); si no responde, `DTWEXBGS` de FRED.
- "Arriba" = el último dato conocido está sobre la media de sus últimos 50 datos (días hábiles con dato).
- **Riesgo a la mitad** mientras los dos estén arriba: el riesgo de cada entrada nueva se multiplica por 0,5. Los topes
  de tamaño no cambian; lo ya abierto no se toca. Solo baja el riesgo, nunca lo sube.
- **Sin mirar el futuro:** el dato del día D se usa desde las 00:00 UTC de D+2 para `DGS10` (FRED lo publica la
  tarde de D+1), desde D+1 para Yahoo (cierra antes de las 24:00 UTC) y desde D+8 para `DTWEXBGS` (sale cada
  lunes con la semana anterior). El informe dice qué fuente se usó.

## La mesa (sin otros cambios)

La de `docs/research/salida_regimen/`: `research_mesa.replay` en 5 minutos con las 12 monedas, riesgo 1-15% por
calidad, régimen b con salida, eventos ±2 h, costos de Binance Futuros, bloques de 30 días encadenados, 1.000 USDT.
1x (`SIZINGS[0]`) y 3x (`SIZINGS[4]`).

## Filas

Decisorias (N llega a 296, con las 6 del TTM Squeeze del mismo commit): 1. 1x con riesgo a la mitad por macro.
2. 3x con riesgo a la mitad por macro.

Referencias (no cuentan): la misma mesa sin la regla, 1x y 3x.

## Listones

1. Neto/caída mayor que la mesa de práctica en los dos años: 1,67 en 2024-25 y −0,21 en 2025-26.
2. Sharpe deflactado ≥ 0,95 en 2025-26, con N = 296 y V = 1/T.

Pasa solo con los dos. Se informa también cuántos días estuvo activa la regla y el cambio contra la referencia. Si
ninguna fuente responde desde GitHub, la prueba no se corre y las filas quedan anuladas (no cuentan).
