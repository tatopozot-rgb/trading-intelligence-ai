---
type: runbook
tags: [automatizacion, memoria, obsidian, agentes]
status: active
---

# Automatización y memoria compartida

Orden del dueño (2026-10-09): automatizar todo en los tres agentes (Claude local, GPT Work y
Claude Leader) y guardar la memoria en Obsidian, para no gastar recursos recordando.

> Los bots operan; los modelos de IA solo supervisan. Ningún agente tiene que recordar nada de
> memoria: todo está en GitHub y en la nota de memoria de Obsidian.

## 1. Regla de memoria (obligatoria para todos los agentes)

1. **Al empezar**, cada agente lee primero:
   - la nota de memoria `09 Checkpoints/Memoria viva.md` del vault de Obsidian del dueño
     (`C:\Users\tatop\TATO`);
   - después, `docs/CHECKPOINT.md` en GitHub.
2. **Al terminar cada bloque de trabajo**, cada agente actualiza la memoria con:
   - qué hizo;
   - qué decidió y por qué;
   - qué queda pendiente;
   - qué orden nueva dio el dueño (con sus palabras).
3. **Quién escribe en Obsidian:**
   - **Claude local** escribe directamente en el vault, porque es el único que tiene el PC.
   - **Claude Leader, Quant y GPT Work** están en la nube y no ven el PC. Dejan su resumen en
     `docs/CHECKPOINT.md` (GitHub). Claude local lo copia a `Memoria viva.md` al menos una vez
     al día (ver 2.1) y siempre que un agente se lo pida.
4. **GitHub sigue siendo la fuente de verdad.** Obsidian es la memoria de trabajo; si algo no
   coincide, gana GitHub.
5. **Nunca** se escriben en Obsidian, ni en ninguna otra parte, claves, tokens, contraseñas ni
   códigos 2FA. Los saldos sí pueden ir en Obsidian, que es privado, pero **nunca en GitHub**,
   porque el repositorio es público.

## 2. Qué corre solo, sin nadie

### 2.1 En el PC del dueño (Claude local)

| Qué | Cuándo | Qué hace |
|---|---|---|
| Operador real (`operator iniciar --real`) | 24 horas, todos los días | Revisa precios y stops cada minuto y decide en cada vela de 4 horas. Compra y vende solo, y avisa por Telegram. |
| Vigilante (watchdog) `operator reanudar` | Cada 5 minutos (Programador de tareas) | Si el operador se cayó o el PC se reinició, lo vuelve a arrancar. |
| Vigilante del mercado (`market_watch`) | Cada 15 minutos (Programador de tareas) | Avisa por Telegram de movimientos fuertes y cambios de tendencia. No opera. |
| Memoria Obsidian | Una vez al día, a las 20:00 de Ecuador, y al final de cada bloque | Copia el resumen nuevo de `docs/CHECKPOINT.md` a `Memoria viva.md`. |

### 2.2 En GitHub (Actions, sin gastar tokens de IA)

| Qué | Cuándo | Resultado |
|---|---|---|
| Experimento de horarios (PAPER) | Cada día, 00:20 UTC (19:20 Ecuador) | `docs/experimento_horarios/`: análisis cada 20 min en todas las ventanas, incluidas la del dueño (07–10) y la del líder (17–19). |
| TSMOM en dos sentidos (PAPER) | Cada lunes | `docs/paper_two_way/` |
| Lista de las 30 monedas principales | Cuando la lanza Quant | `docs/universe/` |

### 2.3 Claude Leader (rutinas programadas en la nube)

| Rutina | Cuándo | Qué hace |
|---|---|---|
| Revisión diaria del experimento | 00:50 UTC (19:50 Ecuador) | Comprueba el reporte del día y le manda al dueño un resumen de máximo 8 líneas. |
| Monitor de la sesión real | Cada 12 horas | Lee lo que hizo Claude local y revisa los reportes. Si hay un fallo, lo corrige. Solo escribe al dueño si pasó algo importante. |

### 2.4 GPT Work (desde el 2026-10-14, cuando tenga créditos)

- **Cada día:** la revisión independiente del experimento, con el texto de
  `docs/prompts/GPT_WORK_HORARIOS.md`.
- **Al terminar:** deja su resumen en GitHub (issue o PR) para que Claude local lo pase a la
  memoria de Obsidian.
- **Hasta el 14:** el líder cubre esta revisión.

## 3. Lo que ningún automatismo hace

- **No mueve dinero real sin la frase del dueño escrita a Claude local.** Esto incluye
  empezar una sesión, sumar capital y adoptar monedas.
- **No cambia `config/live_limits.json`** sin la aprobación escrita del dueño.
- **No salta el motor de riesgo**, no usa martingala y no sube el riesgo para recuperar
  pérdidas.
- **No hace retiros, transferencias, margen, futuros ni apalancamiento.**
