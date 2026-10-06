MODO = "PAPER"

CAPITAL_USD = 100.0

RIESGO_POR_OPERACION_PCT = 1.0

RIESGO_MAXIMO_DIARIO_PCT = 3.0

MAX_OPERACIONES_ABIERTAS = 3

USAR_DINERO_REAL = False

# Compatibilidad histórica del modo asistido; no gobierna --reglas-paper.
REQUERIR_AUTORIZACION_CLAUDE = True

CONFIANZA_MINIMA_CLAUDE = 70

MINUTOS_MAXIMOS_RESPUESTA_CLAUDE = 15

# Riesgo por drawdown desde el pico de equity en ventana rodante de 30 dias
# (ratificado en docs/RISK_POLICY_DECISIONS_2026-10-06.md, fuente docs/RISK_ENGINE_SPEC.md).
# Pausa al 8 % con reanudacion automatica; halt persistente al 15 % (solo liberar_halt).
DRAWDOWN_PAUSE_PCT = 8.0
DRAWDOWN_HALT_PCT = 15.0

# Rutas independientes de la carpeta desde la que se lance Python.
from pathlib import Path
DIRECTORIO = Path(__file__).resolve().parent
BASE_DATOS = DIRECTORIO / "trading.db"
INTERVALO_SCANNER_SEG = 900
INTERVALO_MONITOR_SEG = 60
# Hipótesis conservadora de simulación, no tarifa verificada de un exchange.
COMISION_PAPER_PCT = 0.1
DESVIACION_MAXIMA_PRECIO_PCT = 0.25
