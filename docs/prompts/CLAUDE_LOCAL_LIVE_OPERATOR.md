# Claude Code local: ejecutar el operador de trading REAL (ruta B)

De Claude Leader (cloud), 2026-10-08. El dueño autorizó trading real por API (ruta B)
con estos límites: Spot, sin apalancamiento, capital variable que él asigna por orden,
límite de pérdida 35% del capital de la sesión por defecto, 20-50% a la palabra del dueño (`--limite-perdida N`), **aviso 2 USD antes** (pausa y pregunta),
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
| (el Spot tiene USD, no USDT) | añade `--convertir-usd` al `iniciar --real`: antes de arrancar compra en USDTUSD solo el USDT que le falta al capital, con el USD que ya está en Spot (mínimo 5 USD). No mueve nada fuera de la cuenta |
| "trading sin parar con 50" | `python -m trading_intelligence.live.operator iniciar --capital 50 --perfil tendencia --real` (en segundo plano; el PC queda encendido; velas de 4 h: el operador rechaza órdenes reales en 1 h porque los datos reales mostraron pérdidas, sección 45) |
| "trading por 3 horas con 50" | lo mismo + `--horas 3`: al cumplirse el plazo vende lo de la sesión y termina |
| "hasta ganar 60%" (con cualquier otra orden) | `--meta 60`: cuando la sesión gana ese % de su capital, vende lo de la sesión y termina. Ambas opciones solo cierran; el límite de pérdida y el aviso de 2 USD siguen igual |
| "un trader top hizo movimientos, analízalos" | abres la app/web de Binance en este PC (el dueño ya tiene la sesión iniciada), lees las posiciones actuales de ese líder, le dices qué hizo y si encaja con sus criterios (`copy_trading.review`); si el dueño dice "cópialo con 50", sigues la fila "copia al trader X" |
| "esta vez arriesgo al 50" / "al 20" | `--limite-perdida 50` / `--limite-perdida 20` en el `iniciar` (fuera de 20-50 el operador lo rechaza) |
| "el stop debe ser más alto, con lógica, de 3 a 15, no siempre lo mismo" (orden del dueño, 2026-10-10) | Las sesiones de 1m, 5m y 20m ponen el stop por defecto **entre 3% y 15% por debajo de la entrada, según cómo se mueva cada moneda**: 2,5 veces su volatilidad proyectada a 4 horas. Una moneda tranquila queda en ~3%; una muy movida tiene más espacio, hasta 15%. Si la estrategia pone el stop dentro de esa banda, se respeta; si lo pone más lejos que el máximo, se sube al máximo. El motor ajusta el tamaño a cada stop, así que la pérdida máxima por operación no crece. Para otros límites: `--stop-minimo 4 --stop-maximo 10`. Con `--stop-minimo 0` se usa el stop de la estrategia |
| "stop y take profit con análisis del mercado, no siempre lo mismo" (orden del dueño, 2026-10-10) | En las sesiones nuevas de 1m, 5m y 20m, cada compra lee el mercado en ese momento (`strategy/exit_plan.py`): volatilidad de ~4 horas, soporte y resistencia recientes y régimen (tendencia o rango). Con eso fija su **stop** (bajo el soporte o 2,5× la volatilidad, entre 3% y 15%) y su **toma de ganancia**. En tendencia la deja correr: la meta es la resistencia o más, entre 1,2 y 3 veces el riesgo. En rango la meta es más cercana, en la resistencia, entre 0,6 y 1,5 veces el riesgo. Así sale "stop 15 / ganancia 10" en un rango o "stop 10 / ganancia 15" en una tendencia, según el momento. El aviso de compra en Telegram muestra el plan (stop, meta y por qué) y queda en el diario de la sesión. Desde +1R, el stop sigue la ganancia. XM usa la misma lógica (`xm_demo` sin `--sl/--tp`) |
| "sin stop móvil" / "stop móvil al 5" | `--trailing 0` / `--trailing 5` |
| "usa también mercados en rango" | perfil `tendencia_rango` |
| "dentro del horario cada 2 minutos y fuera cada 5" (orden fija del dueño, 2026-10-10) | `--temporalidad 1m` en el `iniciar --real`: velas de 1 minuto. Dentro de sus horarios (07–10 y 17–19 Ecuador, todos los días) decide **cada 2 minutos**; fuera de ellos, **cada 5 minutos**, comprando y vendiendo a cualquier hora. Los stops y el límite se vigilan cada minuto. Ajustes posibles: `--cada-dentro N` y `--cada-fuera N`. El dueño dijo "queda así fijado" y que XM seguirá las mismas reglas. Para cambiar una sesión abierta: `parar` (sin `--cerrar`), esperar a que el operador se detenga, `iniciar` con los mismos `--meta` y `--limite-perdida` más `--temporalidad 1m`, y `adoptar --simbolo BTCUSDT` |
| "en mis horarios sin parar y fuera cada 20 minutos" (orden del dueño, 2026-10-09) | `--temporalidad 5m` en el `iniciar --real`. **Dentro de sus horarios** (07–10 y 17–19 Ecuador, todos los días; `--ventanas` para cambiarlos) decide en cada vela de 5 minutos: "sin parar". **Fuera de ellos** decide cada 20 minutos y también compra y vende. Los stops, el stop móvil y el límite de pérdida se vigilan cada minuto, a cualquier hora. Telegram avisa al empezar y al terminar cada horario. Con `--temporalidad 20m` decide cada 20 minutos dentro y fuera de los horarios. El dueño eligió esto sabiendo que operar tan seguido perdió en los datos de referencia; no hace falta repetírselo. Para cambiar una sesión abierta: `parar` (sin `--cerrar`), esperar a que el operador se detenga, `iniciar` con los mismos `--meta` y `--limite-perdida` más `--temporalidad 5m`, y `adoptar --simbolo BTCUSDT` |
| "revisa top traders" | con el dueño frente a la app: capturas los líderes (plantilla CSV) → `python -m trading_intelligence.copy_trading.review` → le dices quién está apto y por qué |
| "copia al trader X con 50" | perfil `copiar` + escribes `live_runs/current/leader_positions.json` con las posiciones que el líder muestra en la app (`{"read_at": "<hora con zona>", "trader": "X", "positions": {"BTCUSDT": 0.4}}`) y lo refrescas cuando el dueño lo pida; si pasan 6 h sin refrescar, el operador deja de abrir posiciones nuevas |
| "continúa" (después del aviso de 2 USD) | `python -m trading_intelligence.live.operator continuar`. Con el operador en marcha, la orden va a su buzón (`ORDENES.jsonl`) y él la aplica en su próxima vuelta (menos de 1 minuto) y avisa por Telegram. Antes se escribía `session.json`, y el operador en marcha lo sobrescribía. |
| "agrega 20" / "usa 1000" | `... agregar --capital 20` (solo después de que el dueño depositó); también por el buzón |
| "usa también mi BTC" / "trabaja con todo lo que tengo" | `... adoptar --simbolo BTCUSDT`: suma a la sesión las monedas que ya están en Spot, a su valor actual (sube el capital, no es ganancia). Desde ahí las manejan la estrategia, los stops y el límite. Requiere el operador en marcha |
| "pasa ese BTC a USDT" | `... pasar-a-usdt --simbolo BTCUSDT`: vende todo lo libre de esa moneda. Si vale menos que el mínimo de Binance (5 USDT), primero compra lo justo para pasarlo (máximo 10 USDT). No toca una moneda que la sesión esté operando |
| "¿hay promociones de comisión?" | `... comisiones` (solo lectura): la comisión de esta cuenta en cada moneda, según Binance, con promociones y descuento BNB |
| "para" / "para y cierra todo" | `... parar` / `... parar --cerrar` |
| (si el operador se cayó o el PC se reinició) | `... reanudar`; el vigilante lo hace solo cada 5 min |
| "cómo vamos" | `... estado` y `... reporte --etapa medio` |
| "haz una prueba a ver si funciona" | `... prueba` (por defecto BTCUSDT por unos 6 USDT; `--simbolo ETHUSDT` para otra moneda). **No mueve dinero:** Binance valida la clave, la firma y la orden con su endpoint de prueba, sin ejecutarla. Usa su propio diario (`live_runs/prueba/`) y no toca la sesión |
| "haz la prueba real" | `... prueba --real` (máximo 10 USDT): valida la orden, compra lo justo para que la venta supere el mínimo de Binance tras la comisión, y vende exactamente lo que esa compra entregó, nunca otras monedas del dueño. Cuesta unos centavos de comisión. Es dinero real: solo con esa frase del dueño escrita aquí |

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
3. **Si el PC se apaga o pierde internet:** cada posición tiene además un **stop puesto en
   Binance** (orden STOP_LOSS al precio del stop del motor), que Binance ejecuta aunque el PC
   esté apagado. Al volver, el operador ve que se ejecutó y lo registra, sin volver a vender.
   Lo único que no corre con el PC apagado son las decisiones nuevas, es decir, las compras.
   Si el dueño ve órdenes "Stop-Loss" abiertas en Binance, son estas; no hay que tocarlas.

## 4c. Publicar los reportes para que el líder y GPT Work vigilen

El operador corre aparte y nadie en la nube puede leer `live_runs/` directamente. Una tarea
del Programador de tareas, creada por el dueño o con su permiso, ejecuta **cada hora** desde
`live-operator`:
```
..\venv-live\Scripts\python.exe tools\publish_live_reports.py --state live_runs\current --repo ..\live-reports-repo
```
Copia solo `status.json`, los `reporte_*.md` y `AVISO.txt` a `docs/live_reports/<sesión>/` en
un clon aparte, en la rama `live-reports`, y hace push. Nunca copia el diario de órdenes, la
sesión, el motor ni nada con claves, y no toca el checkout del operador.

## 4d. Alertas al celular por Telegram (privadas, sin publicar nada)

El operador manda a Telegram cada compra y venta, cada stop puesto en Binance, el aviso de
pérdida, el STOP, los errores, el cierre y un resumen cada 4 horas. Sin las dos variables no
envía nada y funciona igual que antes. **El token nunca se escribe en el chat, el repo ni un
log**: lo guarda el propio dueño.

1. El dueño, en Telegram: @BotFather → `/newbot` → copia el token. En PowerShell, **él mismo**:
   `setx TI_TELEGRAM_TOKEN "<token>"`
2. El dueño le escribe "hola" a su bot. En una terminal nueva:
   `python -m trading_intelligence.live.telegram_notify chat-id` → imprime el número del chat.
   `setx TI_TELEGRAM_CHAT_ID "<número>"`
3. Terminal nueva: `python -m trading_intelligence.live.telegram_notify prueba` → llega
   "alertas de Telegram activas" al celular.
4. Un operador que ya corre lee las variables solo al arrancar. Para que la sesión abierta
   mande alertas, cierra la ventana del operador: el vigilante la reanuda en unos 15 minutos
   con las variables nuevas, y mientras tanto los stops puestos en Binance siguen activos.
   **No uses `parar` para esto**, porque termina la sesión.

Si Telegram falla, el operador lo anota y sigue operando: una alerta nunca detiene un stop.

## 4e. Vigilante del mercado (avisos de movimientos fuertes; nunca opera)

`trading_intelligence/live/market_watch.py` lee velas públicas de Binance de las 12 monedas
aprobadas y de PAXG (oro, solo vigilado). Avisa por Telegram y en consola cuando una moneda se
mueve al menos 2,5% en ~1h, 4% en ~4h o 7% en ~24h, en cualquier dirección. También avisa cuando
el régimen de 4h cambia a tendencia alcista o bajista, o a ruptura. No usa claves ni envía
órdenes. Cada movimiento se avisa una vez; vuelve a avisar solo si el movimiento se duplica o si
pasan 4 horas.

1. Prueba: `python -m trading_intelligence.live.market_watch resumen` muestra la tabla de todas
   las monedas y la envía a Telegram si está configurado.
2. Con permiso del dueño, crea una tarea del Programador de tareas,
   `TradingIntelligence-Vigilante`, que corra **cada 15 minutos** desde `live-operator`:
   ```
   ..\venv-live\Scripts\python.exe -m trading_intelligence.live.market_watch
   ```
   Su estado queda en `live_runs/market_watch.json`. Sin tarea, también sirve dejarlo abierto
   con `--continuo` (revisa cada 5 minutos).
3. Las alertas son información para el dueño. Una orden suya ("corto en BTC con 20") sigue el
   camino normal: confirmación del dueño a Claude Code local, límites y stops.

## 4f. Memoria en Obsidian y automatización (orden del dueño, 2026-10-09)

"Que siempre actualicen toda la memoria con Obsidian, así no gastan recursos recordando."
Todo el detalle está en `docs/AUTOMATIZACION.md`.

1. **Al empezar**, lee `C:\Users\tatop\TATO\09 Checkpoints\Memoria viva.md` y después
   `docs/CHECKPOINT.md`. Si la nota no existe, créala.
2. **Al terminar cada bloque**, escribe en esa nota:
   - la fecha;
   - qué hiciste;
   - qué decidió el dueño, con sus palabras;
   - el estado de la sesión real (saldo y operaciones; aquí sí puede ir, porque el vault es privado);
   - lo que queda pendiente.
3. **Copia de la nube:**
   - Con permiso del dueño, crea la tarea `TradingIntelligence-Memoria`, que corra todos los
     días a las 20:00 de Ecuador.
   - La tarea hace `git pull` y copia a `Memoria viva.md` las secciones nuevas de
     `docs/CHECKPOINT.md`. Ahí escriben el líder, Quant y GPT Work.
   - Hazlo también cuando un agente te lo pida.
4. **Nunca** escribas claves, tokens ni códigos en el vault.
5. **Ya corren solos:**
   - el operador (24 h);
   - `reanudar` (cada 5 min);
   - el vigilante del mercado (cada 15 min);
   - la publicación de reportes (cada hora).
   Si alguno falta, créalo según 4b–4e, con permiso del dueño.

## 4g. XM / MetaTrader 5: segundo bróker, mismo automatizador (fase 1: solo lectura y SHADOW)

Orden del dueño, 2026-10-09: "conectemos nuestro automatizador a XM, no reestructurar todo, solo
cambiar de bróker"; "que el bot lea spread, tamaño mínimo, margen y swap de cada instrumento antes de
autorizar una entrada". Código: `trading_intelligence/live/xm_mt5.py`. **No envía órdenes**: la
conexión solo deja pasar funciones de lectura, y el operador rechaza `--broker xm --real`.

1. **Preparación**:
   - `..\venv-live\Scripts\python.exe -m pip install MetaTrader5`. Si Smart App Control lo bloquea,
     **no desactives protecciones**: avisa al líder.
   - El dueño abre MT5 e inicia sesión **él mismo** en su cuenta XM. Mejor una cuenta **DEMO** para
     las fases 1 y 2. El código nunca recibe usuario, contraseña ni servidor.
2. **Cuenta**: `python -m trading_intelligence.live.xm_mt5 cuenta`. Muestra si la cuenta es
   DEMO o REAL, la divisa, el apalancamiento que permite XM (p. ej. 1:1000; el automatizador usa como
   máximo 2x), el balance, la equity y el margen libre.
3. **Fichas**: `... xm_mt5 fichas GOLD EURUSD US30Cash OILCash BTCUSD`. Los nombres exactos se ven en
   la Observación del Mercado de MT5 y cambian según el tipo de cuenta. Por cada instrumento muestra:
   - spread;
   - lote mínimo, paso y tamaño de contrato;
   - cuánto expone el lote mínimo y cuánto margen pide;
   - el swap por noche;
   - si hoy se **autorizaría** una compra y una venta, y por qué no.
   Pégale el resultado al líder: con eso se eligen los instrumentos que caben en la cuenta.
4. **SHADOW con el motor real** (sin órdenes, en carpeta aparte):
   `python -m trading_intelligence.live.operator --dir live_runs/xm_shadow iniciar --broker xm
   --simbolos GOLD EURUSD --capital 100 --temporalidad 20m --perfil tendencia_rango --max-iteraciones 3`.
   - Usa las velas de MT5 y los mismos detectores y estrategias que en Binance.
   - Agrupa instrumentos con horarios parecidos (forex y oro juntos; índices aparte): el motor solo
     procesa las velas en que **todos** los símbolos cotizan.
   - Que el mercado cierre los fines de semana no detiene el motor.
5. **Fase 2 (lista en el código; probar cuando el dueño tenga MT5 con una cuenta DEMO)**:
   `python -m trading_intelligence.live.xm_demo --simbolo EURUSD --lado BUY --sl 0.5 --tp 1.0 --riesgo 1`.
   - Abre una posición con SL y TP en la cuenta **DEMO** y la cierra.
   - Con `--mantener` la deja abierta, con su SL y su TP.
   - Si la cuenta activa en MT5 no es DEMO, se niega.
   - Antes de operar pasa por la ficha y por `order_check` de MT5.
   - El tamaño sale del riesgo (por defecto 0,5% de la equity) y nunca se redondea hacia arriba.
   - Diario: `live_runs/xm_demo/orders.json`.
6. **Operador automático en los dos sentidos (DEMO)**. El dueño eligió la opción "A" el 2026-10-10:
   trabajar XM como funciona el mercado, comprando cuando sube y vendiendo en corto cuando baja, 24/7.
   - Arranque, cuando la prueba de fase 2 salga bien:
     `python -m trading_intelligence.live.xm_auto --simbolos EURUSD GOLD BTCUSD`.
     Usa los nombres exactos que muestre `fichas`.
   - Cadencia: cada 2 minutos dentro de las ventanas 07–10 y 17–19 de Ecuador, y cada 5 minutos fuera
     de ellas. Ajustes: `--ventanas`, `--cada-dentro` y `--cada-fuera`.
   - Señal del régimen en velas de 5 minutos:
     - tendencia o ruptura al alza: **compra**;
     - tendencia o ruptura a la baja: **venta en corto**;
     - rango o sin ventaja: no abre nada.
   - Con una señal contraria, cierra la posición abierta; en la siguiente decisión puede abrir al revés.
   - El stop y la meta salen del plan según el mercado para ese lado, con la banda propia de XM (0,2–5%).
     Quedan **puestos en el servidor de XM**, así que protegen la posición aunque el PC esté apagado.
   - Controles:
     - riesgo fijo de 0,5% de la equity por operación (`--riesgo`), que nunca sube después de una pérdida;
     - máximo 3 posiciones (`--max-posiciones`);
     - si la cuenta pierde 5% en el día (`--perdida-diaria`), cierra todo y no abre más hasta las 19:00
       de Ecuador.
   - Avisos por Telegram al abrir, al cerrar y cuando XM ejecuta un stop o una meta.
   - Estado y diario: `live_runs/xm_auto/state.json` y `live_runs/xm_auto/orders.json`.
   - Solo toca sus propias posiciones (marcadas con su número MAGIC), nunca las manuales del dueño.
   - El forex y el oro cierran el fin de semana: esas horas se saltan solas. Las criptos de XM operan
     cuando XM las cotice.
   - Dejarlo corriendo como el operador de Binance: con un vigilante que lo reinicie si se cae.
   **Fase 3**: dinero real, solo con la frase del dueño y con límites XM aprobados por él por escrito.

## 4h. Binance Futuros en los dos sentidos (orden del dueño, 2026-10-10)

Palabras del dueño: "Ya active cuenta de futuros en binance ... opera como lo ordenado y como si fuese
en xm ... el sistema es el mismo, los 2 mercados son futuros ... no vuelvas a comprar criptos almenos
qué sea una alcista brutal".

1. **Spot deja de comprar.** Si no hay ninguna posición abierta, `parar` sin `--cerrar`. Que el
   vigilante `reanudar` no lo vuelva a arrancar. El vigilante del mercado (`market_watch`) avisa si BTC
   entra en una alcista brutal; comprar en Spot después de ese aviso necesita el "sí" del dueño.
2. **SHADOW ya, sin clave.** Lee precios reales y simula las posiciones con su stop, su meta y la
   comisión de 0,05%:
   `python -m trading_intelligence.live.binance_futures --modo shadow --capital 37`.
   Corre con el mismo motor, la misma cadencia (2/5 min) y la misma señal que XM.
   Estado: `live_runs/futures_auto/shadow/`.
3. **REAL, solo cuando estén las cuatro cosas:**
   a) ✅ Aprobado el 2026-10-10. El dueño aprueba por escrito `config/futures_limits.json`. Ese día rechazó la primera
      propuesta: "deben ser analizados y usar los mismos porcentajes y mismo horario que el anterior
      programado". Ahora son los mismos números del programa de Spot:
      - 1% de la cuenta en riesgo por operación;
      - cada posición, máximo 40% de la cuenta;
      - máximo 3 posiciones;
      - apalancamiento 1x y margen aislado;
      - límite de pérdida de la sesión de 45% (banda del dueño 20–50%), con aviso 2 USD antes;
      - meta de +58%;
      - horario 07–10 y 17–19 de Ecuador cada 2 minutos y cada 5 fuera, 24/7;
      - stop y meta del mercado (3–15%), con el stop que sigue la ganancia desde +1R a R/2.
      Antes de pedirle la aprobación, se mide con datos reales: workflow
      "Futuros en los dos sentidos" → `docs/two_way_backtest/`.
      El líder lo marca como aprobado en GitHub.
   b) **La misma clave de siempre** (orden del dueño, 2026-10-10: "usa la misma clave de ser necesario
      es la misma cuenta"). Si no hay `BINANCE_FUTURES_API_KEY`, el operador usa `BINANCE_TRADE_API_KEY`.
      El dueño solo tiene que marcar **"Habilitar Futuros"** en esa clave (Binance → Gestión de API →
      Editar restricciones), con los retiros desactivados y la IP restringida. El operador de Spot ya
      acepta claves con Futuros, y nunca llama a futuros.
   c) El dueño pasa él mismo los USDT de Spot a Futuros en la app. El sistema nunca transfiere.
   d) La frase del dueño escrita a ti.
   Arranque: `python -m trading_intelligence.live.binance_futures --modo real` (opcional:
   `--limite-perdida N` dentro de 20–50, y `--senal` con la variante que gane la prueba).
   - "continuar" del dueño tras el aviso de pérdida: `python -m trading_intelligence.live.binance_futures
     continuar --modo real`. En XM: `python -m trading_intelligence.live.xm_auto continuar`.
   - Verifica la clave y que la cuenta esté en modo unidireccional (One-way), no cobertura.
   - Pone margen aislado y el apalancamiento del archivo en cada símbolo.
   - Cada entrada lleva un STOP_MARKET y un TAKE_PROFIT_MARKET que cierran toda la posición. Van en el
     servicio Algo de Binance, que es donde están desde 2025-12-09.
   - Si el stop no entra, cierra la posición al momento.
   - Una respuesta dudosa se busca por su id y nunca se reenvía.
   - Diario: `live_runs/futures_auto/real/orders.json`.
4. **Con poco saldo:** con unos 37 USDT y riesgo de 1%, cada operación arriesga unos 0,37 USDT y cada
   posición puede llegar a unos 14,8 USDT (40%).
   BTC (mínimo 100 USDT) no cabe con 1x, y ETH (mínimo 20 USDT) tampoco con 40% de 37: el operador los
   salta y lo anota una vez. Las otras monedas, con mínimo de 5 USDT, sí entran.
5. Los avisos de Telegram dicen "Binance Futuros" o "Binance Futuros (SHADOW)", y "XM DEMO" para XM,
   para comparar cuál rinde más con el mismo sistema.

## 5. Nunca

Retiros, transferencias, margen, futuros o apalancamiento; reenviar una orden incierta (el
operador la concilia solo); editar los límites; ejecutar dos operadores a la vez.
