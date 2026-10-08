# Diagnóstico técnico de sólo lectura

29-09-2026. `paper_doctor.py` no inicia el programa, consulta mercado, modifica la base, libera bloqueos ni instala dependencias. Los imports de requests/pandas se prueban en subprocesos acotados del mismo Python, sin bytecode; no se arranca MetaTrader.

```powershell
cd C:\Users\tatop\trading-ai
.\.venv\Scripts\python.exe -B paper_doctor.py
```

Opciones para otra copia de prueba: `--directorio RUTA --base RUTA_DB --max-edad-estado-seg 180`. La configuración suministrada se inspecciona estáticamente; sus literales no demuestran qué haría código arbitrario al ejecutarse. No se ejecuta `config.py` de la ruta alternativa.

- Código 0 / OK_LOCAL: comprobaciones locales pasaron; NO autoriza operar ni acredita rentabilidad, conexión o vida del proceso.
- Código 1 / BLOQUEADO: configuración no PAPER, dependencia no importable, discrepancia/error contable, cooldown o salud reciente degradada. Se conserva todo y se explica el motivo.
- Código 2 / NO_VERIFICADO: evidencia local ausente, antigua o imposible de interpretar. No equivale a límite de créditos ni exige iniciar el programa.

Un ACTIVO guardado no es una prueba de vida. Se distingue el latido `heartbeat_utc` de la `fecha` final. Cooldown ausente/expirado tampoco demuestra acceso de red; nunca se borra. Archivos JSON se leen con tamaño limitado, rechazando duplicados y valores no finitos. Bases con WAL/journal se dejan sin abrir para no crear sidecars ni realizar una recuperación automática.

Importación fallida de DLL/Application Control se informa sin desactivar ni evadir protecciones. Comprobar instalación no sustituye las pruebas completas. Lectura puntual29sep: Python3.13.15, requests2.34.2 y pandas3.0.6 importables; configuración PAPER correcta, conciliaciónOK con0trades/2solicitudes/11eventos. Estado guardadoDETENIDO23sep es antiguo: NO_VERIFICADO resulta esperado; no significa que haya un proceso en ejecución. Los lectores Binance/XM existen pero no conectan cuentas.

Continuidad y resultados definitivos: `ESTADO_PROYECTO.md`. Tests: `python -B -m unittest test_paper_doctor -v` usando el intérprete del entorno.
