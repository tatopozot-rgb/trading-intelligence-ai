# H6b — Motor puro de escenarios de cartera compartida

Actualización30sep2026: H6c ya conecta este motor a392casos guardados con escenarios explícitos de tiempo/barrera; ver RESULTADO_CARTERA_PAPER.md. Motor con contexto Decimal propio completo,17pruebas y suite540OK. Las frases inferiores sobre adaptador futuro son estado histórico29sep, no pendiente vigente. No se ha integrado al runner; diferencia de contabilidad/costos sigue vigente.

29-09-2026. `historical_portfolio.simular` recibe candidatos, capital, porcentajes, máximo de posiciones, cobertura y política de empates **explícitos**. No importa config, red, cuenta, SQLite o el runner. No tiene valores financieros por defecto. Fixtures no son recomendaciones ni simulaciones de los392casos.

Cada candidato requiere id único, símbolo Spot, entrada_ms/precio/stop/objetivo y comisión; salida_ms/precio deben ser ambos explícitos o ambos nulos. Precios e instantes son hipótesis aportadas, NO hechos de ejecución. Nulos conservan posición abierta al fin, sin cierre/P&L inventado. No acepta intervalos intravela de H6a: falta un adaptador que declare escenarios temporales y sus límites.

## Decisiones técnicas

- Empates se modelan sólo bajo `SALIDAS_ANTES_ENTRADAS_ID_LEXICO_V1`: salidas de posiciones previas, luego entradas por id lexicográfico estable, luego cierres de compras hechas en ese mismo instante. No representa prioridad real ni selecciona estrategia. Ningún candidato rechazado se reintenta; su salida no genera dinero.
- Capital común, una posición por símbolo y máximo de posiciones. Nominal se limita por riesgo individual y cash con fee de entrada incluida. La suma de pérdidas realizadas del día UTC, riesgo restante abierto y riesgo total de entrada nueva no puede superar presupuesto diario. Si no cabe, se rechaza; ganancias no borran pérdidas.
- Se reconoce fee de entrada inmediatamente: saldo realizado = cash + coste nominal de posiciones abiertas = capital inicial + P&L realizado. No equivale a patrimonio valorado a mercado. El riesgo restante de una posición incluye caída hasta stop y fee de salida hipotética a ese stop; fee ya reconocida no se duplica.
- Esta convención contable difiere del ledger operativo legado (ambasfees al cierre y reserva separada) y su riesgo usa coste exacto al stop, no reserva conservadora de dosfees sobre nominal. NO se anuncia paridad operativa ni se modifica la estrategia. El adaptador histórico futuro debe declarar esta diferencia; resultados no sustituyen estudio del runner.
- Base diaria se fija antes del primer evento del día, también si es cierre nocturno. La cuantía presupuestada no garantiza pérdida máxima: un precio de salida aportado con salto puede superarla.
- Decimal con precisión100 y entradas acotadas. No hay cuantización de lotes/ticks del broker. Se admite residuo de hasta1e-70 por división periódica para verificar conservación y normalizar cash negativo de ese orden; no es tolerancia económica ni deslizamiento.
- Se registran todas las decisiones con razón, eventos, posiciones abiertas, días, comisiones, cash/comprometido/saldo realizado, máxima concurrencia y drawdown realizado absoluto NO MTM. SHA256 vincula parámetros/candidatos; no autentica datos ni valida rentabilidad.

## Uso y estado

API en `historical_portfolio.py`; ejemplos reproducibles en `test_historical_portfolio.py`. Pruebas sin datos de cuenta:

```powershell
.\.venv\Scripts\python.exe -B -m unittest test_historical_portfolio -v
```

Pendiente: adaptador desde H5f/H6a con hashes externos, escenarios explícitos de incertidumbre y comparación de políticas sin optimización sobre la muestra. NO se aplicó este motor a los392casos, no se sumaron los P&L aislados ni se modificó H6a. Fees, precios y tiempos todavía son supuestos no calibrados. XM queda excluido de este motor Spot; margen, lotes, divisas y swaps necesitan su propio modelo.
