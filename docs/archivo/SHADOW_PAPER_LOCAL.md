# SHADOW sobre el runtime PAPER real (Claude Code local)

Implementa `docs/SHADOW_MODE_AND_CONTINUOUS_RUNNER_DESIGN.md` (ítems 7 y 8 de la directiva del dueño).
Rama `claude-code/shadow-mode`, apilada sobre `claude-code/api-session-readonly` (PR #9).

SHADOW recorre el mismo camino que las reglas PAPER (scanner, candidatos, solicitud, decisión de
riesgo) y registra qué habría pasado, sin abrir ninguna operación. No es LIVE ni se acerca a LIVE:
no hay transporte de órdenes en este camino.

## Uso

```
python system_runner.py --continuo --sombra-paper [--profundidad-paper] [--horas N]
python system_runner.py --detener
```

`--sombra-paper` exige `--continuo` y excluye `--auto-paper`, `--reglas-paper` y `--prueba-claude`.
Usa el mismo runner continuo que PAPER: bloqueo de instancia única, validación de arranque, parada
por archivo, apagado protegido y `runner_status.json`.

## Qué garantiza

- **Mismo veredicto, mismo código.** `paper_store.ejecutar_reglas_shadow` ejecuta la decisión real
  (`_decidir_reglas` y `_abrir_validado`: halt, pausa, watchdog, límites e inserción) dentro de una
  transacción y la revierte entera. No hay una copia relajada de los controles.
- **Sin efecto sobre PAPER.** Tras una decisión SHADOW no cambia ninguna fila de `paper_trades`,
  `paper_account`, `paper_halt`, `paper_equity_hist`, `paper_days`, `paper_flows` ni
  `paper_requests`. La solicitud queda `PENDIENTE` y caduca como cualquier otra.
- **Auditable.** Cada decisión deja un evento `SHADOW_ABRIRIA` o `SHADOW_RECHAZADA` en
  `paper_events` con símbolo, lado, precio, stop, objetivo, tamaño, motivo y si el halt estaba activo.
- **No se confunde con PAPER.** `runner_status.json` lleva `modo` y `autorizacion` =
  `SHADOW_PAPER`.

## Límites conocidos

- Un halt que SHADOW "activaría" no se activa desde SHADOW; lo activa el camino real
  (`evaluar_riesgo`, que el monitor del runner sigue ejecutando).
- SHADOW no lleva una contabilidad propia de P&L hipotético: registra veredictos, no resultados.
- El panel, el dashboard y `paper_doctor` solo reconocen `modo == 'PAPER'`: una sesión SHADOW les
  aparece como estado no reconocido. Se detiene con `--detener`.
- Como SHADOW nunca abre, el control de "ya existe una operación del símbolo" se evalúa siempre
  contra las posiciones PAPER reales.

## Pruebas

`test_paper_shadow.py` (13, sin red; 18 de 18 mutantes eliminados). Para 10 escenarios (libre, duplicado, halt activo, pausa por
drawdown, drawdown que activaría el halt, sin precio, precio movido, `PAUSA_ENTRADAS`, riesgo
excesivo y otro símbolo con posición abierta) comprueba que el estado PAPER queda idéntico y que
la misma solicitud, decidida después por PAPER, da el mismo resultado y el mismo motivo.

## Ejecución con datos reales (2026-10-08)

Una sesión corta en este PC, con pandas real (entorno aparte con pandas 2.2.3, que Smart App
Control permite) y datos públicos de Binance, sin claves:
`python system_runner.py --continuo --sombra-paper --horas 0.08`, salida 0.

- 1 ciclo de scanner, 5 mercados analizados, 0 errores; 1 candidato llegó a la decisión.
- Resultado: 1 evento `SHADOW_RECHAZADA` (motivo: "El precio cambió: generar y revisar una propuesta nueva", es decir, el precio se movió más del 0,25 % permitido entre el plan y la decisión), 0 filas en `paper_trades`, la
  solicitud quedó `PENDIENTE`.
- `runner_status.json` terminó en `DETENIDO` con `modo` = `SHADOW_PAPER`.

Es una sola sesión de cinco minutos: demuestra que el recorrido funciona de extremo a extremo
con datos reales, no dice nada sobre la calidad de las decisiones. No se ha observado todavía un
`SHADOW_ABRIRIA` con datos reales.
