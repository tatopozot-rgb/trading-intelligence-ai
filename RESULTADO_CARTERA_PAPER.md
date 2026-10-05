# H6c — Sensibilidades de cartera compartida

Generado29sep2026; conciliación independiente30sep. Reutiliza H5f/H6a del25jun–22sep2026 UTC, sin redescargas, indicadores nuevos ni cambios de estrategia. Conserva392casos (BTC164/ETH228), seis censurados y cero ambigüedades stop/objetivo en esta muestra. Los cuatro archivos originales conservan sus hashes externos.

## Resultados diagnósticos

Hipótesis PAPER explícitas: capital común100, riesgo individual1%, presupuesto diario3%, máximo3posiciones y una por símbolo. Comisión0,1% aportada por caso, no tarifa de cuenta comprobada. Precios guardados sin slippage. Desempate técnico porID prioriza BTC, no representa orden del mercado.

| Tiempo hipotético de salida intravela | Temprano | Tardío |
|---|---:|---:|
| Candidatos conservados |392|392|
| Aceptados / rechazados |75 /317|73 /319|
| Cierres / posiciones abiertas al fin |74 /1|72 /1|
| Rechazos por símbolo ya abierto |311|314|
| Rechazos por límite diario |6|5|
| Cash libre |28,5161|29,0976|
| Nominal comprometido a coste |58,5352|59,7289|
| Saldo realizado NO MTM |87,0513|88,8265|
| P&L realizado, incluye fees de entrada |−12,9487|−11,1735|
| Comisiones reconocidas |7,9537|7,7624|
| Máximo retroceso realizado, NO MTM |17,9642|16,2189|

Cuatro variantes: temprano/tardío × STOP_PRIMERO/OBJETIVO_PRIMERO cuando hay ambigüedad. Sin casos ambiguos en esta muestra, las barreras son idénticas dentro de cada tiempo; fixtures sí verifican ambas. La sensibilidad temporal afecta toda salida intravela, no sólo casos ambiguos. Salidas modeladas en apertura/gap no cambian de instante.

Ambos tiempos dan pérdidas bajo estos supuestos: no respaldan presentar la estrategia como rentable. No se adopta tardío por perder menos. Estas sensibilidades NO son extremos garantizados: cambiar una salida afecta admisiones, capital y pérdidas posteriores. No se suman P&L aislados.

ETHUSDT_000222 sigue abierta, contabilizada a coste, sin precio final ni liquidación inventada. Los otros cinco candidatos censurados fueron rechazados; censura no implica posición aceptada. El saldo mostrado NO es valor final de cuenta ni patrimonio a mercado; el retroceso realizado NO es drawdown de equity.

## Consistencia, límites y pruebas

- H6a coincide exactamente con H5f en identidades, intervalos y censura. Se conserva IDoriginal y su correspondencia con IDdelmotor; todo rechazo tiene motivo.
- Reconciliación independiente a300dígitos: cash reconstruido de movimientos, comisiones sumadas y saldo por P&L neto de cierres menos fee de posición abierta coinciden en las cuatro variantes, tolerancia técnica1e−70.75/73aperturas y74/72cierres conciliados.
- La fee de entrada se reconoce al abrir; ledger operativo legado difiere ambasfees al cierre y reserva riesgo distinto. H6c NO es réplica exacta del runner. Ver CONTRATO_CARTERA_PAPER.md.
- Primera señal por episodio, entrada15m simultánea sin latencia: diagnóstico, no scanner dinámico ejecutado. Sin filtros/lotes/ticks, colas, parcialidades, spreads históricos, monitor60s ni costos calibrados. No evidencia fuera de muestra.
- Hashes verifican integridad, no autenticidad económica. No modifica originales, config o trading.db ni inicia sesión operativa.
-29pruebas dirigidasOK3,378s (17motor+12adaptador); suite completa540OK59,126s. Incluye200escenarios sintéticos previos. Se corrigió contexto Decimal heredado: precisión/redondeo/traps/exponentes ahora independientes del llamante. ROUND_UP/DOWN e Inexact no cambian resultado ni contexto externo.

Código: historical_portfolio_report.py y test_historical_portfolio_report.py. Resultado exclusivo: datasets/20260625_20260923/cartera_sensibilidades.json, SHA256 `9ad94b069fa69ee68ec45fe6f48f5b10a3e4a987ecfc3932ae5e136697176d43`. MapaH6a `052d0d9f87589ae89300077e671bddb36b0e5762e8c8d998398b56beb091acdd`. Salida incluye fuentes y huellas de código. No sobrescribe archivos; no repetir generación sin cambios justificados.

## Claude y uso de modelos

Resumen técnico sin claves/cuentas expresamente autorizado y enviado al chat existente03—SISTEMA OPERATIVO Y AUTOMATIZACIÓN, mensajes55/56. Sonnet5.5Medio seleccionado; revisión conceptual completada, NO ejecución local. Se incorporan conservación de rechazos/diferencia contable. Se descarta sugerencia de no variar tiempos de casos sin ambigüedad: contradice el eje temporal. Además cierre tardío15m es apertura+899999ms, no próxima apertura.

Oficiales consultadas29sep: [Sonnet5.5](https://www.anthropic.com/claude-sonnet-5-5) y [Opus5.5](https://www.anthropic.com/claude-opus-5-5), ambos visibles en esta cuenta. Decisión: Sonnet5.5Medio para tareas acotadas; reservar Opus5.5 para problemas complejos. Basado en descripción del proveedor, no comparativa independiente. Ahorro de API no garantiza ahorro de cuota del chat; cuota exactaClaude desconocida. Sin compras/API; los ciclos operativos no llaman modelos por operación.

## Siguiente

Revisar estabilidad numérica del simulador operativo y filtros/lotes reutilizando contrato LIMIT existente: un fill por presupuesto quote no es una orden LIMIT. No alterar resultados históricos guardados. Calibración, equivalencia con runner, observación fuera de muestra e integración privada permanecen pendientes.
