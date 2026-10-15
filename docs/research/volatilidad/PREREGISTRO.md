# Preregistro: "freno de volatilidad" para la mesa (2026-10-15)

Escrito el 2026-10-15, **antes** de correr nada (lección 5 de teoría, pedido del líder). Nada de lo de abajo se
ajusta después de ver el resultado.

## Medida y filtro

- **Volatilidad de 7 días de BTC:** desviación estándar de los últimos 7 rendimientos logarítmicos diarios
  **cerrados** (velas diarias UTC de Spot). En cada vela de 5 minutos del día D se usa el valor calculado con los
  cierres hasta el de D − 1.
- **Umbral:** el percentil 90 de esa misma medida en los 365 días anteriores (de D − 365 a D − 1), sin incluir el
  día D. Sin 365 días de historia o sin dato: sin filtro.
- **Filtro V90:** sin entradas nuevas mientras la medida esté **por encima** del umbral. Las posiciones abiertas
  siguen con sus stops.
- **Sensibilidad (solo informativa):** V80 y V95 (percentiles 80 y 95). No se usan para elegir.

## Montajes (como `docs/research/saturado/`)

La mesa (`mesa_r3`) repetida exactamente como en `research_mesa`, con las reglas de hoy (sin inclinación del
tamaño por sentimiento), velas de 5 minutos, costes y financiación reales, sesiones de 30 días con 1.000 USDT.

1. **Mesa de práctica:** régimen b (solo largos y solo con BTC sobre su media de 50 días; si no, fuera y cierra) +
   freno de eventos (±2 h de FOMC e IPC). Base = eso; luego base + V80 / V90 / V95.
2. **Solo freno de eventos:** base = eventos; luego base + V80 / V90 / V95.

Años: 2024-10-12 → 2025-10-12 y 2025-10-13 → 2026-10-13.

## Cómo se juzga (fijado ahora)

El freno **ayuda** si **V90**, en el montaje 1, mejora el neto/caída de su base en **los dos años** sin quitar más
de la mitad de las operaciones. El montaje 2 y V80/V95 se informan, no deciden. Se publica tal cual. Si ayuda, se
propone para la práctica; nunca para el dinero real sin el líder y el dueño.
