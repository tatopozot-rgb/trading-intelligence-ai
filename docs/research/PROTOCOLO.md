# Protocolo de investigación de estrategias (líder, 2026-10-12)

Orden del dueño: "si no ganamos pues no tiene sentido, busca estrategias y olvida lo que yo dije y mis
marcas, vamos mejorándolas con la práctica". Cada investigador (agente) sigue estas reglas para que los
resultados se puedan comparar y nadie se engañe con un número bonito.

## Cómo correr

- Un módulo propio: `trading_intelligence/backtesting/research_<nombre>.py`, con sus pruebas en
  `tests/test_research_<nombre>.py` (datos sintéticos, sin red).
- Datos públicos de Binance (`data-api.binance.vision` y `data.binance.vision`): velas, financiación y
  `metrics` (top traders). Sin clave, sin cuenta, sin órdenes. Reutiliza `two_way_backtest.fetch`,
  `fetch_funding` y `fetch_top_traders`.
- Se ejecuta en GitHub Actions: workflow **"Investigación de estrategias"** (`research-run.yml`),
  despachado en tu propia rama con `modulo=research_<nombre>` y `args` (por ejemplo `--dias 365`).
  El informe queda en `docs/research/<nombre>/` en tu rama.

## Reglas de medición

1. **Historia larga:** al menos 365 días, para incluir mercados que suben, bajan y van de lado. Muestra
   el resultado por trimestre: una estrategia que solo gana en el tramo alcista no sirve.
2. **Fuera de muestra:** walk-forward (ajusta en 90 días, prueba en los 30 siguientes, avanza 30). Solo
   cuenta el resultado de las ventanas de prueba. Rejilla pequeña de parámetros (máximo ~20 combinaciones).
3. **Costes reales:** comisión 0,05% por lado, financiación real cada 8 h, deslizamiento 0,02% por lado.
   Stop y meta en la misma vela cuentan como stop.
4. **Tamaño como la mesa:** capital de investigación 1000 USDT, 1x, posición máx. 50% del capital,
   3 posiciones a la vez, riesgo por operación 1-15% según la señal (o fijo, si lo dices).
5. **Evidencia mínima:** 100 operaciones fuera de muestra, o se reporta como "muestra corta".
6. **Comparación obligatoria:** contra `mesa_r3` (la mesa en vivo: meta a 3 veces el riesgo) y contra
   comprar y mantener BTC, en la misma ventana. Métricas: neto %, máx. caída, neto/caída, acierto,
   ganancia media / pérdida media, operaciones, comisiones, financiación, correlación diaria con la mesa.
7. **Nada en vivo:** la investigación no toca `config/`, `live/` ni los límites. Si algo gana, se propone
   en un PR y el líder decide si pasa a la práctica (dinero ficticio). Al dinero real solo llega con la
   aprobación escrita del dueño.

## Qué es "ganar"

Neto/caída mejor que `mesa_r3` fuera de muestra, positivo en al menos 3 de 4 trimestres, con 100+
operaciones. Una estrategia sin correlación con la mesa también sirve aunque gane algo menos: suma.
