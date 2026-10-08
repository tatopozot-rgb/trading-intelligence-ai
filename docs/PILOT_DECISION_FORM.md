# Formulario de aprobación del piloto real (USD 30)

Todos los valores de abajo son una **PROPUESTA** de Claude Leader. No están aprobados. El
piloto empieza solo cuando usted responda con la frase de la sección 3, sin cambios o con
los cambios que quiera. Hasta entonces el sistema sigue en revisión y simulación.

## 1. Propuesta (ruta A: Copy Trading nativo de Spot)

| Punto | Propuesta | Por qué |
|---|---|---|
| Ruta | **A: Copy Trading nativo de Binance, Spot** | Es la única vía oficial para copiar a top traders; la API oficial no permite seguir líderes |
| Capital del piloto | **30 USDT** en el portafolio de copia | Lo que usted indicó |
| Traders | **1 trader con los 30 USDT** (alternativa: 2 de 15) | Hay un mínimo de unos 10 USDT por copia, y repartir poco capital deja órdenes bajo el mínimo del exchange |
| Quién | Solo un trader que la revisión marque **"candidato a copiar"** | Criterios auditables, no la ganancia reciente |
| Pérdida máxima del piloto | **6 USDT (20%)**: al llegar, se deja de copiar y se revisa | Limita el costo de aprender |
| Stop de la copia en la app | **20%** si la app lo permite (lo confirma Claude Code local) | Que Binance corte aunque nadie mire |
| Instrumentos | **Solo Spot. Sin Futures. Sin apalancamiento** | El apalancamiento multiplica pérdidas; queda para otra decisión |
| Comisión al líder (profit share) | **máximo 10%** | El evaluador la descuenta del rendimiento |
| Duración | **4 semanas**, con una captura por semana | El aprendizaje necesita varias capturas |
| Retiros | **Siempre desactivados** | No negociable |
| Clave API | **Solo lectura** con restricción de IP, solo para vigilar | La copia la ejecuta Binance, no nuestro código |

## 2. Qué pasa durante el piloto

- Cada semana: captura y revisión automática. Usted recibe "mantener" o "dejar de copiar ya".
- Si la pérdida llega a 6 USDT: se deja de copiar y se revisa antes de seguir.
- No se añade capital para recuperar pérdidas.
- Al final de las 4 semanas: informe con resultado neto, comparación con el líder y lo
  aprendido. Usted decide si sigue, cambia o agrega capital.

## 3. Cómo aprobar

Responda en el chat (o en un comentario del PR #1) con:

> **APRUEBO PILOTO A: 30 USDT, 1 trader, pérdida máxima 6 USDT, stop de copia 20%, solo Spot sin apalancamiento, profit share máximo 10%, 4 semanas, retiros desactivados.**

Si quiere otros valores, cambie los números en la frase. Cualquier punto que no apruebe
queda en espera; el sistema no lo rellena por su cuenta.
