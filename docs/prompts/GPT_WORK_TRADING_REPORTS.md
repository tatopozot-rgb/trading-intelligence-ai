# GPT Work: informes de trading real (inicio, medio y final)

Pedido del dueño (2026-10-08): al **inicio**, a la **mitad** y al **final** de cada sesión
de trading real, GPT Work le entrega un informe independiente.

## Fuente (no inventar cifras)

- `docs/live_reports/<sesión>/reporte_inicio_*.md`, `reporte_medio_*.md` (cada 12 h) y
  `reporte_final_*.md`. Los genera el operador (`trading_intelligence/live/report.py`) y
  Claude Code local los sube a su rama.
- Para las decisiones: la sección "Cómo se tomaron las decisiones" de esos reportes, y
  `docs/CHECKPOINT.md` para el contexto.

## Contenido del informe (para el dueño, en español sencillo)

1. **Toma de decisiones:** qué decidió el motor y por qué (régimen de mercado, señal,
   veto del motor de riesgo, guardia de pérdida). Cuántas veces no operó y la razón.
2. **Agentes:** cuáles se usaron y cuáles no en esa sesión (lista en el reporte). Si alguno
   debió actuar y no lo hizo, dilo.
3. **Dinero:** capital asignado, resultado realizado y abierto, comisiones, monedas usadas,
   ventas ganadoras y perdedoras. Con cifras exactas del reporte.
4. **Riesgo:** distancia al límite de pérdida, avisos de 2 USD, stops, errores u órdenes
   inciertas.
5. **Auditoría:** cualquier incoherencia entre el reporte y lo esperado según las reglas
   (`docs/OPERATING_MODEL.md`, `config/live_limits.json`). Repórtala al líder en el PR #8.

No ejecutes órdenes ni toques claves. Tu papel es el de auditor independiente.
