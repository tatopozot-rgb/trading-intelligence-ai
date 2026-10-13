# Rechazos por mínimo de Binance en la mesa (mesa_r3): qué son y si sesgan el resultado

Se repiten solo las dos ventanas con picos de rechazos, con las mismas reglas que el informe de tendencia (mesa_r3, velas de 5 min, 1.000 USDT por ventana, tamaño de la mesa). Cada rechazo guarda cuánto permitía cada tope: el riesgo hasta el stop, el 50% por posición y el capital libre con 1x. Un "episodio" junta los rechazos de la misma moneda y sentido en velas seguidas (la misma señal vista vela tras vela). Para cada episodio se mira 24 h hacia adelante, como con los vetos: ¿tocaba antes el stop o la meta de 3R?

## 2025-08-08 a 2025-09-07

- Rechazos: **190**, en **62 episodios** (mediana de 1.0 velas seguidas por episodio).
- Por moneda (rechazos): {'TRXUSDT': 54, 'LINKUSDT': 41, 'AVAXUSDT': 32, 'ETHUSDT': 18, 'DOGEUSDT': 17, 'ADAUSDT': 16, 'XRPUSDT': 6, 'DOTUSDT': 3, 'LTCUSDT': 2, 'BTCUSDT': 1}; episodios: {'TRXUSDT': 19, 'LINKUSDT': 14, 'ADAUSDT': 7, 'AVAXUSDT': 7, 'XRPUSDT': 4, 'DOGEUSDT': 3, 'DOTUSDT': 3, 'ETHUSDT': 3, 'BTCUSDT': 1, 'LTCUSDT': 1}.
- Tope que fijó el tamaño: {'capital ya usado (1x)': 190}.
- Posiciones abiertas en ese momento: {2: 190}; capital ya usado (mediana): 100.4%; distancia al stop (mediana): 4.67%.
- Qué habría pasado en 24 h (por episodio): {'sin resultado': 55, 'evitó pérdida': 7}; acierto de los episodios con resultado: 0.0% frente a 28.6% de las 56 operaciones que la mesa sí hizo en la ventana.

## 2025-10-12 a 2025-11-11

- Rechazos: **105**, en **32 episodios** (mediana de 1.5 velas seguidas por episodio).
- Por moneda (rechazos): {'AVAXUSDT': 25, 'ADAUSDT': 24, 'DOGEUSDT': 23, 'DOTUSDT': 16, 'BNBUSDT': 5, 'LTCUSDT': 5, 'ETHUSDT': 3, 'TRXUSDT': 1, 'XRPUSDT': 1, 'LINKUSDT': 1, 'BTCUSDT': 1}; episodios: {'AVAXUSDT': 7, 'ADAUSDT': 6, 'DOTUSDT': 6, 'DOGEUSDT': 4, 'LTCUSDT': 3, 'BNBUSDT': 1, 'BTCUSDT': 1, 'ETHUSDT': 1, 'LINKUSDT': 1, 'TRXUSDT': 1, 'XRPUSDT': 1}.
- Tope que fijó el tamaño: {'capital ya usado (1x)': 105}.
- Posiciones abiertas en ese momento: {2: 105}; capital ya usado (mediana): 101.0%; distancia al stop (mediana): 8.48%.
- Qué habría pasado en 24 h (por episodio): {'sin resultado': 32}; acierto de los episodios con resultado: None% frente a 37.5% de las 56 operaciones que la mesa sí hizo en la ventana.

