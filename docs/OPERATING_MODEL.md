# Cómo funciona Trading Intelligence AI (modelo operativo, ruta B)

Escrito por Claude Leader (cloud), actualizado el 2026-10-08, cuando el dueño eligió la
**ruta B**: el sistema opera solo por la API oficial de Binance Spot. Todas las órdenes
salen del operador del proyecto. El dueño solo inicia sesión, aprueba los filtros de
seguridad (2FA) y deposita o retira dinero.

## 1. Quién hace qué

| Quién | Dónde | Qué hace |
|---|---|---|
| **Claude Leader (cloud)** | nube + GitHub | El cerebro y el responsable: construye y mantiene el motor de decisiones, el riesgo, el operador real, los reportes y los automatizadores; revisa el trabajo de los demás; coordina. Si algo falla funcionalmente, es su responsabilidad. |
| **Claude Code local** | el PC del dueño (encendido) | Las manos: ejecuta el operador real con las órdenes del dueño; configura la clave **en el PC**; lee la app de Binance cuando el dueño pide revisar top traders; avisa al dueño de inmediato si aparece un aviso; sube los reportes. |
| **Sesión Quant (cloud)** | nube | Mide con datos reales si las estrategias ganan después de comisiones (resultado honesto, sin retocarlas para que parezcan buenas). |
| **GPT Work** | revisión independiente | El auditor: informe al **inicio, mitad y final** de cada sesión (decisiones, agentes usados y no usados, dinero, monedas) y búsqueda de fallas. |
| **Dueño** | celular / app de Binance | Da las órdenes en palabras, aprueba el 2FA, deposita y retira, y decide si continuar cuando llega el aviso de 2 USD. |

**¿Quién opera?** Uno solo: **el operador** (`trading_intelligence/live/operator.py`),
corriendo en el PC del dueño. Decide el motor del proyecto, el motor de riesgo puede vetar
cualquier orden y, por encima de todo, la guardia de pérdida del dueño.

## 2. Cómo se hace una operación

```
 datos reales de Binance ─► detector de régimen ─► estrategia (tendencia / rango) ─► motor de riesgo (veto)
                                                                                         │ aprobada
 guardia de pérdida del dueño (aviso 2 USD antes · stop al límite) ◄──────────────────────┘
                                                                                         │
 operador: tamaño = fracción × capital de la sesión, máx. 40% por posición, 3 posiciones ─► orden MARKET real en Binance Spot
                                                                                         │
 stop protector vigilado cada minuto · diario de órdenes · reportes inicio / medio / final
```

- **Varios mercados a la vez** (12 monedas aprobadas). Si un mercado no da señal o está en
  contra, no se opera ahí y el capital queda para otro.
- **Tres opciones de trading continuo:**
  1. `tendencia`: compra en tendencia alcista o ruptura, en cualquiera de los mercados.
  2. `tendencia_rango`: lo anterior más reversión en mercados laterales.
  3. `copiar`: replica, con nuestra API, las posiciones que un top trader muestra en la app
     (leídas por Claude Code local cuando usted lo pide).
- **Solo compra y vende lo suyo.** Las otras monedas de su cuenta nunca se tocan.

## 3. Las órdenes que usted da (desde el celular)

| Usted dice | Pasa |
|---|---|
| "trading sin parar con 50" | arranca una sesión real con 50 USDT, perfil tendencia |
| "revisa top traders" | Claude Code local lee la app con usted; el sistema ordena a los líderes con motivos |
| "copia al trader X con 50" | perfil copiar |
| "agrega 20" / "usa 1000" | suma capital a la sesión (después de que usted depositó) |
| "continúa" | sigue después del aviso de 2 USD, hasta el límite |
| "para" / "para y cierra" | se detiene; con "cierra" vende las posiciones de la sesión |
| "cómo vamos" | estado y reporte |

## 4. La regla de pérdida (la que usted pidió)

- Límite: **20% del capital de la sesión** (50 → 10 USDT).
- **2 USD antes del límite** (50 → a los 8 USDT de pérdida): no abre nada nuevo y le
  **pregunta** si continuar. Las salidas y los stops siguen funcionando.
- Si dice "continúa", sigue hasta el límite. En el límite se detiene y cierra las
  posiciones de la sesión.
- El sistema nunca agrega capital ni sube el riesgo para recuperar. Si usted agrega capital,
  el límite se recalcula sobre el nuevo total.

## 5. Lo que nunca pasa

Retiros o transferencias (una clave con retiros se rechaza), margen, futuros o
apalancamiento, claves en chats o en GitHub, reenviar una orden dudosa (se concilia),
martingala, dos operadores a la vez.

## 6. Qué corre solo

- El **operador**: mientras el PC esté encendido. Decide en cada vela de **4 horas** y
  vigila la pérdida y los stops cada minuto.
- El **PAPER loop**: en GitHub cada 4 h, como laboratorio paralelo.
- La **revisión de traders**: en GitHub, cada vez que se sube una captura.
- La revisión del proyecto por **Claude Leader**: cada 8 h.

## 7. Lo que dicen los datos reales (sección 45 del checkpoint)

La sesión Quant probó ambas estrategias con 1 a 4 años de datos reales de Binance, en las
12 monedas, con comisiones incluidas y sin retocarlas:

| Configuración | Resultado por operación después de comisiones | Veredicto |
|---|---|---|
| tendencia, velas de 1 h | **−0,80%** (408 operaciones) | **pierde dinero** de forma demostrada |
| tendencia + rango, 1 h | **−0,67%** (473 operaciones) | **pierde dinero** de forma demostrada |
| tendencia, velas de 4 h | +3,51% (206 operaciones) | positiva, **no demostrada** (p ≈ 0,09) |
| tendencia + rango, 4 h | +3,06% (235 operaciones) | positiva, no demostrada (p ≈ 0,09) |

Decisión del líder: **el operador no envía órdenes reales en 1 h**; solo en 4 h. En 4 h, la
operación típica (la mediana) pierde, y el resultado depende de pocas ganancias grandes.
Se esperan rachas de pérdidas pequeñas. Cada sesión real sigue siendo un experimento con la
pérdida acotada por su regla del 20% y el aviso de 2 USD.
