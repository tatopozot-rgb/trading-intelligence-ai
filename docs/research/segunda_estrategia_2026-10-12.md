# Segunda estrategia de futuros junto a la mesa (2026-07-14 a 2026-10-12)

Investigación con datos públicos (sin cuenta, sin órdenes). Velas de 5 min (precio Spot como aproximación del perpetuo), comisión 0,05% por lado y financiación real. Tamaño como la mesa: riesgo 1-15% según la calidad, posición máx. 50%, 1x, 3 posiciones. Capital de estudio 1.000 USDT. Ajuste en el primer 60% (2026-07-14 a 2026-09-06); prueba en el último 40% (2026-09-06 a 2026-10-12). Solo cuenta lo que se sostiene fuera de muestra con al menos 30 operaciones.

| Candidata | Parámetros elegidos | Ajuste: ops / neto % | Prueba: ops | Acierto | Neto % | Media/op | PF | p | Máx. caída | Neto/caída | Comisiones | Correlación con la mesa | Veredicto |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **mesa_r3 (la mesa en vivo, misma ventana de prueba)** | meta 3R | — | 42 | 54.8% | +18.54% | — | — | — | 10.28% | 1.8 | 15.66 | — | referencia |
| funding | {'theta': 0.025, 'hours': 8} | 18 / -0.14% | 14 | 57.1% | -0.35% | -0.049% | 0.74 | 0.6939 | 1.08% | -0.32 | 6.99 | 0.007 | insuficiente: 14 operaciones fuera de muestra (< 30) |
| ruptura | {'stop': 'opuesto', 'k': 1.0} | 63 / +7.74% | 50 | 48.0% | +0.50% | +0.024% | 1.04 | 0.879 | 4.94% | 0.1 | 24.86 | 0.018 | positiva fuera de muestra, pero sin significancia |
| scout | {'move': 1.5, 'vol': 3.0, 'hours': 1} | 121 / +3.52% | 157 | 42.7% | -1.46% | -0.020% | 0.97 | 0.8853 | 14.02% | -0.1 | 68.18 | 0.081 | no se sostiene fuera de muestra (pierde) |

## Nota

**Ninguna candidata se sostiene fuera de muestra** con 30 operaciones o más. No se recomienda un bot de práctica con estas reglas; si se quiere seguir midiendo, la menos mala puede correr solo en práctica, sin dinero real.

Advertencias: 90 días son un solo tipo de mercado; elegir el mejor de una cuadrícula en el ajuste infla el resultado del ajuste (por eso solo cuenta la prueba); el precio Spot aproxima al perpetuo; un stop y una meta en la misma vela cuentan como stop. Un resultado pasado no promete uno futuro.
