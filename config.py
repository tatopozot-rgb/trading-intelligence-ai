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

# Halt persistente por drawdown desde el pico de equity (Finding 3).
# None = politica NO aprobada: mientras sea None no se abren entradas (fail-closed).
# Valor pendiente de Trading Claude-Work; no copiar valores de docs/ ni de trading_intelligence/.
DRAWDOWN_HALT_PCT = None

# Rutas independientes de la carpeta desde la que se lance Python.
from pathlib import Path
DIRECTORIO = Path(__file__).resolve().parent
BASE_DATOS = DIRECTORIO / "trading.db"
INTERVALO_SCANNER_SEG = 900
INTERVALO_MONITOR_SEG = 60
# Hipótesis conservadora de simulación, no tarifa verificada de un exchange.
COMISION_PAPER_PCT = 0.1
DESVIACION_MAXIMA_PRECIO_PCT = 0.25
