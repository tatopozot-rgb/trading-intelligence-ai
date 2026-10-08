# Piloto real con USD 30: camino más corto y decisiones del dueño

Escrito por Claude Leader (cloud), 2026-10-08. Nada de esto autoriza operar con dinero
real: el piloto empieza solo cuando el dueño decida cada punto de la sección 4 por
escrito.

## 1. Qué es posible por vías oficiales (verificado)

- **La API oficial de Copy Trading de Binance tiene solo dos endpoints**, los dos para
  el propio *líder* (`/sapi/v1/copyTrading/futures/userStatus` y `.../leadSymbol`).
  Lo verifiqué en el código fuente del conector oficial `binance-connector-python`
  (`clients/copy_trading`). **No existe vía oficial para**: listar líderes o "top
  winners", leer sus posiciones o resultados, ni seguir/copiar a un líder por API.
- Las "APIs de leaderboard" que circulan son scrapers de endpoints web no documentados.
  El sistema las **rechaza** (`copy_trading/sources.py`).
- **Copy Trading nativo** (en la app): según las páginas de ayuda de Binance (vistas por
  búsqueda; desde la nube no puedo abrir binance.com, Claude Code local debe confirmarlo
  en la app), el seguidor necesita mínimo ~10 USDT por copia (Futures; en Spot 10 USDT
  en modo monto fijo o 100 USDT en modo proporcional), el líder cobra ≥10% de las
  ganancias, Spot Copy exige KYC con domicilio y depende de la región. El seguidor
  **no puede controlarlo por API**: entrar/salir es un clic del dueño.
- **Ejecución propia por API Spot oficial**: totalmente automática y bajo nuestro motor
  de riesgo, pero **sin acceso oficial a las operaciones de los líderes** no puede
  replicarlos automáticamente.

**Conclusión honesta:** "copiar traders automáticamente por API" no es posible por vías
oficiales. Hay dos rutas reales:

| | Ruta A: Copy Trading nativo + nuestro sistema decide y vigila | Ruta B: ejecución propia por API Spot |
|---|---|---|
| Quién ejecuta | Binance (el dueño hace clic en seguir/dejar) | nuestro programa, automático |
| Qué aporta el sistema | selección auditable de líderes, reglas de riesgo, cuándo dejar de seguir, seguimiento | todo: decisión, riesgo, órdenes, reconciliación |
| Datos de líderes | lo que muestra la app, capturado a mano (plantilla) | no aplica (estrategia propia) |
| Bloqueo actual | confirmar en la app mínimos y disponibilidad regional | ninguna estrategia propia tiene ventaja probada (NO-GO honesto) |
| Automatización | parcial | total |

## 2. Qué queda funcionando (cloud, probado)

- `trading_intelligence/copy_trading/`: fuentes solo oficiales, evaluador/selector con
  criterios auditables (incluye las cifras tal como las muestra la app), riesgo sobre el
  RiskEngine, seguidor PAPER/SHADOW realista, pipeline de extremo a extremo y reporte.
  47 pruebas; 28/28 mutantes detectados. Demostración: `python -m
  trading_intelligence.copy_trading.pipeline --demo` (datos SINTÉTICOS, marcados).
- Automatizador PAPER en GitHub Actions con datos reales públicos de Binance y reporte
  de decisiones por símbolo (pestaña Actions).

## 3. Hallazgo clave para USD 30

Con la asignación propuesta (30% del capital por trader) **ninguna copia llega al
mínimo de orden de Binance (5 USDT)**: en la demo, 7 de 7 copias se omiten
(`BELOW_MIN_NOTIONAL`). Con USD 30 solo funciona **concentrando todo en un trader**
(asignación 100%), que es justo el riesgo de concentración que el evaluador penaliza.
En Copy Trading nativo, USD 30 alcanza para 1 a 3 copias de 10 USDT. Esto es decisión
del dueño, no del sistema.

## 4. Decisiones que necesito del dueño antes de dinero real (no las invento)

1. **Ruta**: A (Copy Trading nativo) o B (API Spot propia), o A primero.
2. **Pérdida máxima total aceptada** del piloto (¿los 30 completos? ¿menos?), y qué pasa
   al alcanzarla (apagado y revisión).
3. **Pérdida diaria máxima** (en USD o %).
4. **Instrumentos**: ¿solo Spot? ¿Futures? Si Futures: **apalancamiento máximo**.
5. **Cuántos traders** y asignación (1 trader al 100% o repartir).
6. **Comisión al líder** máxima aceptada (profit share).
7. Confirmar o cambiar los valores propuestos: stop duro por posición 12%, envolvente de
   caída temporal 6%, presupuesto de pérdida por trader 5%, bloqueo tras 3 promedios a
   la baja del líder.
8. **Autorización explícita** para: (a) Testnet, (b) el primer día con dinero real.

## 5. Camino más corto y verificable

1. **Claude Code local (hoy):** configurar la nueva clave en el PC del dueño como
   variables de entorno, **solo lectura, sin retiros, con restricción de IP**, y correr
   la verificación H1 (saldo y permisos, sin mostrar la clave). Confirmar en la app:
   disponibilidad de Spot Copy Trading para la región del dueño, mínimos reales y si el
   saldo de un portafolio de copia se ve por API de solo lectura.
2. **Dueño + Claude Code local:** capturar 10 a 20 líderes con la plantilla
   `docs/templates/copy_trading_snapshot.template.json`, **incluidos los que dejaron de
   liderar**. Subir el archivo al repo.
3. **Cloud:** evaluar la captura real y devolver la lista corta con motivos. Comparar en
   SHADOW durante 1 a 2 semanas (el sistema registra qué haría y por qué).
4. **Dueño:** decidir la sección 4.
5. **Piloto:** Ruta A, el dueño sigue al trader elegido con el monto decidido y el
   sistema vigila con la clave de solo lectura y recomienda mantener o salir según las
   reglas. Ruta B, Testnet (H2) y luego USD 30 con los límites decididos.
