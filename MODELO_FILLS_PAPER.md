# Profundidad visible: modelo PAPER optativo

30sep2026: cálculos y recomputación usan contexto Decimal propio (redondeo,precisión,traps,rangoexponencial). Un llamante con contexto diferente ya no invalida evidencia legítima; evidencia adulterada sigue rechazada.7tests de aislamiento,75dirigidas y suite547OK48,411s. Sin cambio de modeloV1 ni reinterpretación de evidencias guardadas.

29-09-2026. `PROFUNDIDAD_VISIBLE_FOK_PAPER_V1` simula una compra/venta consumiendo los niveles de un snapshot. No es una orden enviada ni una promesa de ejecución. El modo legado se conserva, sin cambiar resultados históricos.

## Uso

Abrir `paper_dashboard.py` no inicia sesiones. Para un inicio explícito posterior, elegir duración y marcar «Nuevas entradas: profundidad visible FOK», revisar el diálogo e iniciar. Sin marcar, se conserva ticker legado. Cambiar el selector no altera posiciones ya abiertas: su modelo está fijado en el plan persistido.

Equivalente CLI, **no ejecutado durante este desarrollo** (duración de ejemplo; no fija capital ni riesgo nuevos):

```powershell
.\.venv\Scripts\python.exe -B system_runner.py --continuo --reglas-paper --profundidad-paper --horas 0.5 --reanudar
```

Mantiene máximo8horas por sesión, estrategia/riesgo existentes, pausa de entradas, caducidad, consumo único, control de instancia y cierre seguro de trabajadores. No es servicio24/7 ni se reinicia por horario. La conciliación se ejecuta antes de arrancar trabajadores y antes de retirar STOP con `--reanudar`; una discrepancia bloquea el inicio.

## Contabilidad e integridad

- BUY recibe nominal cotizado antes de comisión y recorre asks; SELL usa exactamente la cantidad Decimal conservada en la compra y recorre bids, también tras reinicio. No reconstruye cantidad desde un VWAP float.
- VWAP incorpora impacto de los niveles observados; comprar ask/vender bid ya incluye spread. No se suma spread otra vez ni se inventa deslizamiento aleatorio.
- Fee es hipótesis explícita en activo cotizado. Se reserva nominal+fee de entrada; reservar NO descuenta saldo ni duplica gasto. Al cierre, beneficio neto proviene de quote de venta menos quote de compra y ambas comisiones verificadas. SQLite conserva sus columnas numéricas existentes; evidencia Decimal original permite recalcularlo.
- Snapshot, parámetros y resultado quedan junto al evento APERTURA/CIERRE en la misma transacción. El modelo queda en el plan hasheado. Falta, duplicación o alteración de la evidencia impide cerrar por sustitución.
- La antigüedad local máxima5s incluye duración de consulta y se revalida antes de commit. Caducidad durante la transacción provoca rollback. Para auditar compra antigua se valida a su fecha histórica, no se exige que un libro antiguo siga vigente hoy.
- Parcial es un resultado real del simulador, pero este ledger sólo integra llenado completo (FOK simulado). Compra parcial no abre posición; venta parcial NO finge cierre: la posición queda abierta y monitor informa error. `PROFUNDIDAD_VISIBLE_INSUFICIENTE` describe sólo el snapshot limitado, no toda la liquidez del mercado.

## Límites conocidos

El REST depth aporta niveles/lastUpdateId, no timestamp del exchange; se guardan solicitud/recepción locales. No asegura frescura remota, prioridad en cola, ejecución de una orden hipotética ni disponibilidad futura. Fuente oficial: [Binance, datos de mercado](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market).

No aplica aún redondeo al lote/tick del exchange dentro del fill, descuentos de comisiones en otro activo, consumos globales de profundidad entre operaciones, fills parciales persistentes o calibración de latencia real. Los módulos `execution_*` de filtros permanecen separados. El monitor observa periódicamente: una cotización puede saltar stop; detener el proceso no liquida posiciones. No usar estadísticas de este modelo como rentabilidad demostrada ni transplantarlo a XM/contratos.

Pruebas aisladas cubren niveles exactos, libro cruzado, edad límite, parciales, fees, cantidades periódicas, reinicios, evidencia manipulada, duplicados, base diaria, conciliación y rollback. Conteos actuales y siguiente bloque están en `ESTADO_PROYECTO.md`.
