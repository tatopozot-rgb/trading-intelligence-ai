# Cómo funciona Trading Intelligence AI (modelo operativo)

Escrito por Claude Leader (cloud), 2026-10-08. Para el dueño: qué hace cada agente,
cómo se toma y se ejecuta una operación, qué es automático y qué decide usted.

## 1. La idea en una frase

El sistema **estudia** a los traders líderes de Binance y al mercado, **decide** a quién
copiar y cuándo dejar de copiar con reglas auditables y un motor de riesgo con veto, y
**aprende** de cada captura si sus decisiones aciertan. En el piloto, **Binance ejecuta**
la copia (Copy Trading nativo) y **usted hace el clic** de seguir o dejar de seguir.
Ningún agente mueve dinero por su cuenta.

## 2. Quién hace qué

| Quién | Dónde trabaja | Qué hace | Qué NO hace nunca |
|---|---|---|---|
| **Claude Leader (cloud)** | la nube y GitHub | El cerebro: evaluación y selección de traders, reglas de riesgo, aprendizaje, simulación, reportes, automatizaciones en GitHub Actions, revisión del código de los demás, coordinación y checkpoints | ver claves, tocar su cuenta, enviar órdenes |
| **Claude Code local** | su PC (tiene red real y la app abierta con usted) | Las manos: configura la clave **en su PC** (solo lectura, sin retiros), comprueba permisos y saldo, captura con usted las cifras de los líderes desde la app, sube las capturas, prueba órdenes en **Testnet** (dinero ficticio) | guardar o mostrar claves, operar en real sin su autorización |
| **GPT Work** | revisión independiente | El auditor: intenta romper lo que hacen los otros dos con pruebas propias y reporta fallas (ya encontró varias reales) | implementar el sistema o tocar su cuenta |
| **Usted (dueño)** | la app de Binance y este chat | Decide límites y ruta, aprueba el piloto por escrito, hace el clic de copiar o dejar de copiar, y es el único que puede quitar un apagado de emergencia | — |

**Sobre "¿uno solo va a operar?":** en el piloto **ningún agente opera**. Opera Binance (Copy
Trading nativo), con el dinero que usted asigne en la app. El sistema elige, vigila y
avisa. Si más adelante usted autoriza la ruta B (ejecución propia por API), habrá **un solo
componente** que pueda enviar órdenes: el transporte de Claude Code local, primero en
Testnet y siempre detrás del motor de riesgo, que puede vetar cualquier orden.

## 3. Cómo se hace una operación (ruta A, piloto)

```
 App de Binance ──(usted + Claude local copian las cifras)──► captura CSV ──► docs/snapshots/
                                                                               │
                         GitHub Actions "Trader review" se ejecuta solo ◄──────┘
                                                                               │
                ranking con motivos  +  "copiar / mantener / DEJAR DE COPIAR YA"  +  aprendizaje
                                                                               │
                           usted decide y hace el clic en la app ◄─────────────┘
                                                                               │
                Binance ejecuta la copia (comisiones, deslizamiento y profit share incluidos)
                                                                               │
          Claude local (clave de solo lectura) lee saldo y posiciones ──► la siguiente revisión
```

1. **Captura (semanal, unos 15 minutos):** usted abre Copy Trading en la app; Claude Code
   local anota con usted, por líder: ROI 7/30/90/180 días, caída máxima, días como líder,
   operaciones, activos y las últimas ganancias o pérdidas cerradas. Incluye a los que
   **dejaron de liderar**: si se omiten, el sistema solo vería a los ganadores y se engañaría.
2. **Revisión (automática):** al subir la captura, GitHub ejecuta la revisión y publica en
   Actions el ranking, el motivo de cada decisión y qué hacer con cada trader que usted copia.
   Si hay que dejar de copiar a alguien ya, la ejecución sale **en rojo**.
3. **Decisión:** usted copia al candidato elegido con el monto aprobado, o deja de copiar
   cuando el sistema lo indica.
4. **Seguimiento:** Claude Code local lee el resultado con la clave de solo lectura (sin
   tocar nada) y se registra en `docs/snapshots/followed.json` a quién copia usted.
5. **Aprendizaje:** con cada captura nueva el sistema mide si los que eligió antes
   **realmente** lo hicieron mejor que el resto después, cuántos desaparecieron y qué
   criterio predice mejor. Si la selección no acierta, se ve en números y se corrige.

## 4. Cómo decide a quién copiar (resumen de las reglas)

- Rendimiento **neto** de la comisión del líder; se descuenta la suerte de los historiales
  cortos.
- Caída máxima, consistencia (cuántas ventanas en positivo), dependencia de pocas
  operaciones afortunadas, concentración en un solo activo, liquidez de lo que opera,
  apalancamiento.
- Un dato desconocido **no aprueba**: se trata como fallo.
- No cambia de trader por ruido: un nuevo candidato tiene que ser claramente mejor (30%)
  para desplazar a uno que ya se copia.
- **Dejar de copiar YA:** si el líder deja de liderar, su caída se vuelve demasiado profunda,
  sube el apalancamiento o pasa a un mercado no permitido.
- **Dejar que cierre y salir:** si solo baja en el ranking.
- En simulación también: nunca promedia a la baja; bloquea al líder que promedia a la baja
  repetidamente (martingala); distingue una caída temporal (mantener) de una tesis
  invalidada por el mercado (salir); tiene stop duro por posición.

## 5. Qué corre solo, sin nadie

| Qué | Cuándo | Dónde se ve |
|---|---|---|
| PAPER loop: estrategias propias sobre datos reales de Binance, en simulación | cada 4 h | GitHub → Actions → "PAPER loop" |
| Revisión de traders | cada vez que se sube una captura | GitHub → Actions → "Trader review" |
| Revisión general del proyecto por Claude Leader | cada 8 h | checkpoints en `docs/CHECKPOINT.md` y Notion |

Rojo en cualquiera de ellos = algo requiere atención. El PAPER loop además se detiene en
rojo si pierde su estado; nunca se reinicia en silencio.

## 6. Lo que nunca pasa

- Retiros: siempre desactivados; una clave con retiros es rechazada por el código.
- Ninguna clave pasa por un chat, GitHub, Notion ni logs: vive solo en su PC.
- Sin martingala, sin subir el riesgo para recuperar pérdidas.
- Nada de dinero real sin su aprobación escrita de los límites (`docs/PILOT_DECISION_FORM.md`).
- Nada de fuentes no oficiales de Binance (scrapers): el código las rechaza.

## 7. Ruta B (después, solo si usted la autoriza)

Ejecución propia por la API Spot oficial: totalmente automática, con el motor de riesgo
decidiendo cada orden. Hoy está lista la parte técnica en Testnet (dinero ficticio). Falta
lo esencial: **ninguna estrategia propia ha demostrado ventaja** con datos reales. El PAPER
loop las sigue midiendo cada 4 horas. Cuando una pase la validación, se presenta con
cifras y usted decide.
