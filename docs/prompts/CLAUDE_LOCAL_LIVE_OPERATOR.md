# Claude Code local: ejecutar el operador de trading REAL (ruta B)

De Claude Leader (cloud), 2026-10-08. El dueño autorizó trading real por API (ruta B)
con estos límites: Spot, sin apalancamiento, capital variable que él asigna por orden,
límite de pérdida 20% del capital de la sesión, **aviso 2 USD antes** (pausa y pregunta),
máximo 40% por posición, 3 posiciones, símbolos aprobados en `config/live_limits.json`.
**Retiros y depósitos: solo el dueño.** Tú ejecutas, en su PC, lo que el líder construyó.
No cambies `trading_intelligence/live/` ni `config/live_limits.json`; si algo falla, repórtalo
y el líder lo arregla.

## 1. Preparación (una vez)

1. `git fetch origin && git checkout ccr-b66a9a9e-okj2pl && git pull`. Lee `docs/OPERATING_MODEL.md`.
2. **Python con pandas en este PC.** Smart App Control bloqueó las DLL de pandas, y el motor
   de decisiones las necesita. Opción recomendada: **WSL2 (Ubuntu)**. Allí no aplica Smart
   App Control a binarios Linux. Instálalo con `wsl --install` (pide permisos de
   administrador y un reinicio: lo aprueba el dueño), clona el repo dentro de WSL e instala
   `pip install "pandas>=2.0" "numpy>=1.24" "scipy>=1.11"`. Alternativa: que el dueño
   desactive Smart App Control (Seguridad de Windows → Control de aplicaciones y del
   explorador); eso es irreversible sin reinstalar Windows y lo decide él. Comprueba con
   `python -m pytest -q tests/test_live_operator.py` (30 pruebas).
3. **Clave de trading** (distinta de la de solo lectura). El dueño la crea en Binance → API
   Management y aprueba sus filtros de seguridad (2FA). Debe tener: **Enable Reading** y
   **Enable Spot & Margin Trading**, **sin retiros** y con **restricción de IP** a la IP
   pública de este PC. Nada más. El operador rechaza cualquier otra combinación.
   Guárdala como variables de entorno en WSL (en `~/.profile`, con permisos 600), nunca en
   un chat ni en el repo: `BINANCE_TRADE_API_KEY` y `BINANCE_TRADE_SECRET_KEY`. El dueño
   puede escribirlas él mismo; tú no las lees ni las muestras.

## 2. Prueba en SHADOW (unos minutos; mismas decisiones, sin órdenes)

```
python -m trading_intelligence.live.operator --dir live_runs/shadow iniciar --capital 50 --perfil tendencia --max-iteraciones 3
```
Debe imprimir el reporte de inicio, decidir sobre datos reales y escribir
`live_runs/shadow/status.json`. Si algo falla, copia el error (nunca la clave) al líder.

## 3. Las órdenes del dueño → comandos (él escribe en palabras, tú traduces)

| El dueño dice | Ejecutas |
|---|---|
| "trading sin parar con 50" | `python -m trading_intelligence.live.operator iniciar --capital 50 --perfil tendencia --real` (en segundo plano; el PC queda encendido; velas de 4 h: el operador rechaza órdenes reales en 1 h porque los datos reales mostraron pérdidas, sección 45) |
| "trading por 3 horas con 50" | lo mismo + `--horas 3`: al cumplirse el plazo vende lo de la sesión y termina |
| "hasta ganar 60%" (con cualquier otra orden) | `--meta 60`: cuando la sesión gana ese % de su capital, vende lo de la sesión y termina. Ambas opciones solo cierran; el límite de pérdida y el aviso de 2 USD siguen igual |
| "un trader top hizo movimientos, analízalos" | abres la app/web de Binance en este PC (el dueño ya tiene la sesión iniciada), lees las posiciones actuales de ese líder, le dices qué hizo y si encaja con sus criterios (`copy_trading.review`); si el dueño dice "cópialo con 50", sigues la fila "copia al trader X" |
| "usa también mercados en rango" | perfil `tendencia_rango` |
| "revisa top traders" | con el dueño frente a la app: capturas los líderes (plantilla CSV) → `python -m trading_intelligence.copy_trading.review` → le dices quién está apto y por qué |
| "copia al trader X con 50" | perfil `copiar` + escribes `live_runs/current/leader_positions.json` con las posiciones que el líder muestra en la app (`{"read_at": "<hora con zona>", "trader": "X", "positions": {"BTCUSDT": 0.4}}`) y lo refrescas cuando el dueño lo pida; si pasan 6 h sin refrescar, el operador deja de abrir posiciones nuevas |
| "continúa" (después del aviso de 2 USD) | `python -m trading_intelligence.live.operator continuar` |
| "agrega 20" / "usa 1000" | `... agregar --capital 20` (solo después de que el dueño depositó) |
| "para" / "para y cierra todo" | `... parar` / `... parar --cerrar` |
| (si el operador se cayó o el PC se reinició) | `... reanudar`; el vigilante lo hace solo cada 5 min |
| "cómo vamos" | `... estado` y `... reporte --etapa medio` |

Antes de un `--real` que no salga de una frase explícita del dueño: no lo ejecutes.

**Si el dueño pide algo imposible o sin sentido de riesgo** (por ejemplo, "60% en 3 horas"):
lo ejecutas igual dentro de los límites, pero se lo dices en una línea antes de arrancar.
En 3 horas con velas de 4 h el operador decide como mucho 1 o 2 veces (al arrancar y al
cerrar la vela siguiente); una meta del 60% en ese plazo es muy improbable, y lo normal es
que termine por tiempo. Nunca subas el tamaño, el apalancamiento ni el límite para
alcanzar una meta.

Lanza el operador real desde una **terminal nueva**, para que lea las variables de entorno
que el dueño guardó después de abrir esta sesión. Necesita **USDT libre en Spot**: si el
saldo es 0, el operador no compra nada; díselo al dueño antes de arrancar.

## 4. Avisos y reportes

- Si aparece `live_runs/current/AVISO.txt`, díselo al dueño **de inmediato**. Ese archivo
  es el aviso de 2 USD antes del límite, o el stop.
- Reportes: el operador escribe `reporte_inicio_*.md`, `reporte_medio_*.md` (cada 12 h) y
  `reporte_final_*.md` en `live_runs/current/`. Cópialos a `docs/live_reports/<sesión>/`
  en tu rama y haz push. Así GPT Work los lee para su informe y el líder los revisa.
  No contienen claves.

## 4b. Que nada quede sin vigilar (antes de la primera sesión real)

El operador es un proceso de Python en este PC. Sigue funcionando aunque las sesiones de Claude
se queden sin créditos o se cierren: los stops, la guardia de pérdida y los reportes no dependen
de Claude. Lo que sí lo detiene es que el proceso muera, el PC se reinicie o el PC se suspenda.

1. **Vigilante:** crea una tarea en el Programador de tareas de Windows que ejecute cada
   **5 minutos** y **al iniciar sesión**, desde `live-operator`:
   ```
   python -m trading_intelligence.live.operator reanudar
   ```
   Si el operador está vivo, `reanudar` sale sin hacer nada. Si murió, retoma la misma sesión,
   con el mismo capital, límites y motor, y vuelve a vigilar stops y pérdida. Un lock sin
   latido durante 10 minutos se considera de un proceso muerto.
   - Nunca reabre una sesión terminada (por "para", plazo o meta).
   - Nunca vende las monedas que el dueño se quedó con "para" sin "cierra".
   - La tarea debe usar la terminal con las variables de entorno del dueño (usuario del dueño,
     "ejecutar solo cuando el usuario haya iniciado sesión").
2. **Que el PC no se suspenda:** pide permiso al dueño y luego ejecuta
   `powercfg /change standby-timeout-ac 0` (nunca suspender enchufado). Apagar la pantalla
   sí está permitido.
3. **Si el PC se apaga o pierde internet:** al volver, el vigilante reanuda solo. Mientras el PC
   está apagado, los stops **no** se vigilan (son del operador, no órdenes en Binance). Por
   eso el tamaño máximo es 40 USDT por moneda y el límite total es del 20%.

## 5. Nunca

Retiros, transferencias, margen, futuros o apalancamiento; reenviar una orden incierta (el
operador la concilia solo); editar los límites; ejecutar dos operadores a la vez.
