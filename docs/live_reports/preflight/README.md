# Ensayo previo (Fase 0 de `docs/archivo/PREFLIGHT_100.md`), Claude Code local

Ejecutado el 2026-10-09 ~01:50 UTC en el PC del dueño, sobre `b8a312c`. Ninguna orden real.

| Paso | Resultado |
|---|---|
| Clave de trading | OK: lectura + Spot, sin retiros, IP restringida (lectura firmada, `SpotTrader.verify_key`) |
| USDT libre en Spot >= 100 | **NO** en el momento de la comprobación (solo sí/no; el saldo no se registra aquí) |
| `tests/test_live_operator.py` | 38 passed |
| Ensayo SHADOW (`--capital 100 --perfil tendencia_rango --max-iteraciones 2`) | exit 0; reporte de inicio en esta carpeta |
| Revisión de top traders en vivo | **No hecha**: pendiente de que el dueño autorice a la sesión local a leer su Binance abierto en el navegador |

Coincide con el plan: capital 100, perfil `tendencia_rango`, velas de 4 h, 12 monedas, aviso a 18,
límite a 20, 40 % por posición, 3 posiciones, modo SHADOW.

Hueco del ensayo: en 2 iteraciones (unos 2 minutos) no cerró ninguna vela de 4 h, así que el
reporte no contiene decisiones ni el régimen por moneda. `engine/loop.json` quedó en la última
vela cerrada (2026-10-08T20:00Z) con el diario vacío. El punto "qué régimen tiene cada moneda y
qué haría el sistema ahora" no se puede responder con este ensayo.

## Segundo ensayo (2026-10-09 ~02:13 UTC, sobre `35a78d7`)

- `tests/test_live_operator.py`: 46 passed.
- Ensayo SHADOW `shadow100b` (misma configuración, 2 iteraciones): exit 0. El reporte de inicio ya
  incluye régimen y decisión por moneda: 10 en TREND_DOWN y 2 en NO_EDGE sin estrategia para ese
  régimen (NO_TRADE), y TRXUSDT en RANGE sin señal. Ninguna compra simulada.
- USDT libre en Spot >= 100: **NO**. La sesión real no se arrancó.
- Red inestable durante la comprobación: una lectura firmada falló sin respuesta HTTP y otra con
  código -1021 (marca de tiempo fuera de ventana) cuando la consulta de hora tardó más de 1 s.
  Tres lecturas posteriores respondieron bien.
- Vigilante de Task Scheduler, `powercfg` y revisión de top traders: no hechos; esperan el permiso
  del dueño en la sesión local.
