---
type: empresa
tags: [empresa, gobierno, terceros]
status: living
---

# Trading Intelligence AI como empresa de trading

Orden del dueño (2026-10-13): "manejes esto como una empresa de trading, tú eres el gerente ... después vamos a
recibir dinero de terceros para comisionar, por eso debes estar atento al mercado por si hay un boom y actuar rápido".

## 1. Organigrama

| Puesto | Quién | Qué hace |
|---|---|---|
| Dueño | El dueño | Aprueba el dinero real, los límites y la entrada de clientes. Acepta cada operación de la alarma. |
| Gerente | Claude Leader (nube) | Decide la estrategia con evidencia, coordina al equipo, revisa el mercado cada día y rinde cuentas al dueño. |
| Investigación | Quant, Tendencia, Rotación (sesiones en la nube) | Prueban estrategias con el protocolo (`docs/research/PROTOCOLO.md`). No tocan nada en vivo. |
| Operaciones | Claude local (PC del dueño) | Corre los bots, la alarma y las prácticas; vigila que sigan vivos; escribe el diario en Obsidian. |
| Análisis profundo | GPT Work | Revisión independiente desde el día 14. |
| Vigilancia 24/7 | Alarma de mercado (`live/alarma.py`) | Detecta choques en 1–2 minutos y avisa sin parar hasta que el dueño responde. |

## 2. Rutina de la empresa

| Cuándo | Qué |
|---|---|
| Cada minuto | La alarma de mercado revisa BTC, ETH y las monedas de la mesa. |
| Cada día, 06:52 Ecuador | Nota de inteligencia: Internet, macro, fechas de riesgo, régimen y una lección de teoría (`docs/inteligencia/`). |
| Cada 2 h | El gerente lee a Claude local y resuelve lo pendiente. |
| Cada 12 h | Monitor de la mesa: errores, bots vivos, órdenes del dueño. |
| Cada día | Revisión de la práctica y aprendizaje (`revision-futuros`). |
| Cada lunes | Prueba con datos reales de la semana y un informe semanal al dueño. |

## 3. Política de riesgo (no cambia sin el dueño)

- Retiros siempre apagados. Nunca transferencias automáticas. No se guardan secretos en GitHub, Notion, Obsidian ni logs.
- Sin martingala; nunca subir el riesgo después de perder.
- El dinero real solo opera una estrategia que pasó el protocolo, con la frase del dueño. Los límites están en
  `config/futures_limits.json`.
- Un choque de mercado no se opera solo: la alarma propone y el dueño acepta (`ACEPTO <código>`).

## 4. Camino para recibir dinero de terceros (por puertas; no se salta ninguna)

1. **Una estrategia que gane.** Debe pasar el protocolo: positiva en 3 de 4 trimestres, fuera de muestra y con
   costes reales. Hoy **no** la tenemos: la mesa perdió −53% en un año (CHECKPOINT §98).
2. **Historial real con dinero propio.** Al menos 6 meses en vivo con dinero del dueño, con los estados de Binance
   como prueba, la caída máxima medida y sin interrumpir las reglas. Nadie confía su dinero sin ese historial.
3. **Asesoría legal en Ecuador antes del primer dólar ajeno.** Recibir dinero de varias personas para invertirlo,
   sin autorización, puede ser **captación ilegal de dinero (COIP art. 323, 5 a 7 años de prisión)**. Ya hubo
   condenas en Quito por ofrecer inversiones en criptomonedas
   ([Fiscalía](https://www.fiscalia.gob.ec/5-anos-de-carcel-por-captacion-ilegal-de-dinero-con-criptomoneda/),
   [El Comercio](https://www.elcomercio.com/actualidad/seguridad/sentencia-captacion-dinero-criptomonedas-quito/)).
   No existe una ley específica de criptoactivos: el proyecto de blockchain se archivó en octubre de 2025, y la
   SCVS supervisa administradoras de fondos y el lavado de activos
   ([Metlabs](https://metlabs.io/regulacion-blockchain/ecuador/),
   [ExperTax](https://expertax.ec/regulacion-fiscal-trading-criptomonedas-forex-ecuador/)). Hay que hablar con un
   abogado de mercado de valores y con un contador (SRI).
4. **Estructura que no reciba el dinero de nadie.** La vía más limpia es que cada cliente tenga **su propia cuenta**
   y copie nuestras operaciones con la herramienta oficial del exchange: **Copy Trading de Binance Futures como
   "lead trader"**. El exchange cobra y reparte la comisión sobre la ganancia; nosotros nunca tocamos el dinero de
   un cliente. Esto se verifica con el abogado y con las reglas de Binance antes de abrirlo.
5. **Comisión justa:** un porcentaje de la ganancia sobre el máximo anterior (high-water mark), sin comisión
   cuando se pierde. Riesgo explicado por escrito a cada cliente.

## 5. Actuar rápido ante un boom o un desplome

- La alarma detecta y avisa en 1–2 minutos, sin parar, con una propuesta de operación lista para aceptar.
- La nota diaria anticipa lo que se puede ver venir: la Fed, la inflación, la guerra o la energía, los fondos de
  Bitcoin, el apalancamiento.
- Rápido no significa sin control: stop en el exchange, 1x, el riesgo aprobado y la aceptación del dueño.
