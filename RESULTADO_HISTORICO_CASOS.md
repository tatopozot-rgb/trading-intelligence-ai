# Diagnóstico de episodios — 24 de septiembre de 2026

Se evaluaron392 casos aislados sobre señales guardadas de25junio–22septiembre2026 UTC. No es una simulación de cartera ni un resultado de ganancias de cuenta.

| Activo | Casos | Objetivo primero | Stop primero | Sin salida al final | Ambiguos |
| --- | ---: | ---: | ---: | ---: | ---: |
| BTCUSDT | 164 | 41 | 123 | 0 | 0 |
| ETHUSDT | 228 | 71 | 151 | 6 | 0 |

Los eventos de stop superan los de objetivo en esta selección. Es una alerta diagnóstica, no una demostración de rentabilidad o pérdida futura. No se sumó P&L de casos que pueden solaparse ni se asignó resultado a los seis casos sin salida. La ausencia de ambigüedad en estos casos no demuestra que el problema no exista: está cubierto en pruebas sintéticas.

## Hipótesis exactas

- Selección: primera señal de cada episodio consecutivo ALCISTA MOMENTUM SANO. Es muestreo diagnóstico, no política operativa de reentrada.
- Entrada: apertura15m al mismo instante de señal. Supone latencia cero y no demuestra un fill alcanzable. Los indicadores sólo usan información cerrada anteriormente.
- Salida: primer toque de barrera; un salto usaría apertura de vela; si ambos niveles se tocan se conservan dos escenarios sin probabilidades. Sin evento no hay liquidación forzada.
- Capital independiente por caso100; comisión0,1% aportada, tomados de parámetros PAPER existentes. No representan tarifas verificadas ni disponibilidad simultánea de capital.
- No modela cartera, reinversión, posiciones concurrentes, pérdida diaria compartida, spread, impacto, deslizamiento, caducidad ni el monitor real60s.
- Universo fijoBTC/ETH, no radar dinámico; no prueba independiente fuera de muestra. No ajustar umbrales sólo para mejorar esta muestra.

## Verificación

397 pruebas de software aprobadas. Se comprobó igualdad exacta del adaptador frente al cálculo individual en9casos: BTC índices0/7/82/163; ETH0/10/114/222/227. Se verificaron17.280 filas H4, ventanas/cierres/precios/código/hashes, sin recalcular el replay completo ni redescargar datos. Los hashes prueban coherencia respecto de los valores esperados, no autenticidad del proveedor ni corrección de todos los indicadores por sí solos.

Informes completos: datasets/20260625_20260923/BTCUSDT/casos_episodios.json y ETHUSDT/casos_episodios.json.

SHA256 informes:

- BTC:9aee522f66b165b886d421f797634bcdffa50f6ab86d949de6340b03433c5ea1
- ETH:bdc040c05be46f3dd4ad6b2b594003ab63f2af14a1c10ec03847f2848e17f9d1

SHA256 replay fuente fijados externamente al evaluar:

- BTC:fc5f2f27ee73ea67531db18f68d044fed6aa31105f0dcd54b05c3df898a37447
- ETH:86f31797ab317edae1607963d043cbc771b493df8d8d7d5e1a0fd3c606086223

Claude colaboró en contrato/matriz de pruebas (mensajes43/44 del chat existente). Su revisión fue sobre resumen, no acceso a archivos ni ejecución local. No se cambió la estrategia ni sus límites.

Revisión final de Claude (mensajes45/46): estudiar sensibilidad a supuestos de ejecución antes de ajustar estrategia. Próximo escenario técnico propuesto: retraso de una vela15m conservando señal original; es estrés hipotético, no latencia calibrada del sistema. Deslizamiento debe declararse por separado, sin afirmar realismo no medido. No extrapolar frecuencias a rentabilidad de cuenta ni al radar dinámico.
