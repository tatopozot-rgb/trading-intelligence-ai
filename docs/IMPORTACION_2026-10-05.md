# Importación del programa existente

## Alcance y procedencia

Fuente: `C:\Users\tatop\trading-ai`, checkpoint técnico 30-09-2026 (547 pruebas OK).
Copiados inicialmente 90 archivos Python (47 módulos y 43 archivos de tests) y 18 Markdown,
943.870 bytes. No se recorrieron subdirectorios ni se modificó la carpeta operativa original.
Los módulos Python originales se conservan byte a byte en la importación inicial.
Se mantienen reglas de agentes y plantilla de PR del repositorio. No integrar sin revisión cruzada.

## Exclusiones deliberadas

- Entorno virtual, cachés, backups, claves/.env, logs y archivos de sesión.
- SQLite y auxiliares, solicitudes/respuestas de chat, runner.lock/status y señales de parada.
- Datasets históricos locales. Los informes Markdown conservan evidencia fechada, pero reproducir
  esos resultados completos exige recuperar los datos y hashes originales; la suite usa fixtures temporales.

Barrido limitado de patrones de credenciales: sin coincidencias en los 108 archivos originales.
No equivale a certificación de ausencia de secretos. Revisar lista publicada y hashes antes de cada envío.

## Reproducción y límites del entorno

Windows, Python 3.13, venv real y Tkinter. Requests 2.34.2 y pandas 3.0.6 son las únicas dependencias
directas; no hace falta el SDK Binance de la carpeta original. Tests UI crean Tk; el test del launcher
lee pyvenv.cfg. No asumir soporte Linux sin revisar controles Windows y entorno gráfico.

Reproducción 05-10-2026: 547 tests OK en 56,717s desde copia sin BD/datasets/runtime, usando
el Python del venv original. Esto verifica aislamiento del código, no instalación limpia de dependencias.
El primer intento fue bloqueado por permisos del sandbox; la ejecución autorizada pasó.
Los mensajes de error HTTP/disco forman parte de fallos simulados esperados.

La copia de ingeniería está bajo la carpeta local de esta tarea, en `trading-intelligence-ai/`.
Se publica mediante conector GitHub: Git CLI no dispone de credenciales. Esta copia NO es un clon
Git completo; no hacer pull/push allí. Antes de cada bloque contrastar commit, rama, PR y coordinación
remota, y aplicar solo cambios revisados; nunca publicar automáticamente una carpeta entera.

## Integración continua y costes

Workflow manual para Windows/Python 3.13 en venv, sin cron/órdenes/secretos/permisos de escritura.
Comprobar disponibilidad y cuota incluida de Actions antes de lanzarlo; aún NO ejecutado en GitHub.
Las dependencias directas PAPER están fijadas en requirements-paper.txt; no hay lock transitivo ni reproducibilidad binaria certificada.
El requirements.txt remoto de investigación, pytest.ini y paquete trading_intelligence se preservan sin modificaciones.
Los tests PAPER se seleccionan solo de la raíz; pytest de tests/ es evidencia separada pendiente de reproducción.
Hashes de checkout v4/setup-python v5 verificados en repositorios oficiales el 05-10-2026.

## Faltantes no resueltos por esta migración

Filtros MARKET/quoteOrderQty/lotes/dust versionados, calibración de fees/slippage, validación fuera de muestra,
transporte privado/Testnet, adaptador XM real/requisitos de cuenta y auditoría final PAPER.
H6c mostró resultados negativos y una posición abierta no valorada a mercado. No elegir el mejor
escenario retrospectivo ni presentar el saldo realizado como valor final de cartera.
