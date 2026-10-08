# Binance Spot y XM/MetaTrader: alcance PAPER

Fecha de revisión documental: 28 de septiembre de 2026.

Estado: existen lectores locales de snapshots y pruebas sintéticas. No existe
conexión de estos adaptadores con Binance, XM, MT4 o MT5, ni integración suya con
el runner, el dashboard o la contabilidad PAPER. La lectura de un snapshot no
significa que una cuenta o un instrumento estén disponibles ni autoriza operar.

## Decisión de arquitectura

Se mantiene separado el modelo de activos Spot del modelo de contratos MT5.
Solo comparten validadores de forma, números, tiempo y serialización. No se
unifican sus fórmulas económicas, unidades, comisiones ni restricciones.

| Propiedad | Binance Spot | Contrato XM MT5 |
|---|---|---|
| Lector | `BinanceSpotPaperAdapter` | `XmMt5PaperAdapter` |
| Tipo devuelto | `SpotPaper` | `ContratoMt5Paper` |
| Volumen | Cantidad del activo base | Lotes del contrato |
| Identidad | Símbolo, activo base y cotizado | Símbolo exacto, servidor, alias demo, tipo de cuenta |
| Metadatos | Incrementos de precio/cantidad y rango | Tamaño de contrato, tick, valores de tick, divisas, modo de cálculo, volumen y swaps |
| Economía | No implementada en este lector | Lectura opcional de resultados ya aportados para un escenario exacto |
| Transporte, login y envío | No implementados | No implementados |

`broker_adapters.py` solo usa la biblioteca estándar. No importa `config`, módulos
de ejecución, clientes HTTP, MetaTrader5 ni persistencia. Sus métodos reciben
diccionarios o JSON textual y devuelven objetos inmutables. No contienen rutas
de red, lectura de credenciales, descubrimiento de terminales o envío de órdenes.

La auditoría limitada confirmó que `config.py` conserva `MODO = "PAPER"` y
`USAR_DINERO_REAL = False`. La comisión PAPER de 0,1% figura como hipótesis de
simulación; no se traslada a XM ni se convierte en tarifa verificada de Binance.
Los contratos `execution_*` existentes usan fixtures OFFLINE/Testnet orientados
a Binance. No se modificaron ni se convierten snapshots MT5 a esos contratos.

## Lo que permiten realmente las plataformas

Binance publica datos de mercado Spot mediante endpoints sin API key en
`data-api.binance.vision`, incluidos `exchangeInfo`, velas, profundidad y
`bookTicker`. Esto permite una futura captura pública sin abrir una cuenta.
Los adaptadores de este archivo no realizan esa captura. [Binance: URLs de datos
de mercado](https://developers.binance.com/en/docs/products/spot/faqs/market_data_only).

Los filtros de Binance distinguen precio, cantidad, importe, condiciones dinámicas
y límites de cuenta/exchange. Los pocos metadatos Spot de este lector son una
proyección para diagnóstico: no sustituyen `exchangeInfo`, su respuesta original,
la evaluación de filtros, permisos o saldo. Un snapshot que se puede leer no es
una operación aprobada. [Binance: filtros](https://developers.binance.com/docs/binance-spot-api-docs/filters).

Binance documenta comisiones estándar, especiales y fiscales, con componentes
maker/taker y buyer/seller, descuentos y posible pago en otro activo. Las tasas
de cuenta y los resultados de una consulta de comisión requieren contexto propio.
No se presupone que una comisión pública fija cubra todos los casos. No se
implementan consultas privadas ni órdenes de prueba. [Binance: comisiones](https://developers.binance.com/en/docs/products/spot/faqs/commission_faq).

XM publica plataformas MT4 y MT5 con soporte de Expert Advisors. Su documentación
de cuentas describe diferencias de instrumentos entre ambas y aclara que no todos
los instrumentos de ciertas cuentas son libres de swaps. La oferta genérica de la
web no demuestra las condiciones de la cuenta concreta del usuario. [XM: MT4](https://www.xm.com/mt4),
[XM: MT5](https://www.xm.com/mt5), [XM: cuentas y swaps](https://www.xm.com/help-center/trading-accounts/are-all-instruments-swap-free-for-ultra-low-account-holders).

La integración oficial de Python consultada comunica con el terminal MetaTrader 5.
No es una API HTTP genérica de XM ni acredita una conexión equivalente con MT4.
Un navegador o la aplicación móvil no sustituyen ese terminal para esta vía de
Python. [MetaQuotes: integración Python](https://www.mql5.com/en/docs/python_metatrader5).

`initialize()` puede encontrar y arrancar un terminal, reutilizar la última cuenta
y tomar contraseña/servidor guardados si se omiten parámetros. Por ello este
trabajo no llama a `initialize()` ni siquiera como comprobación de instalación.
[MetaQuotes: initialize](https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py).

MT4 dispone de Expert Advisors escritos en MQL4, ejecutados en su terminal. Una
futura exportación desde MT4 exigiría un componente propio de esa plataforma o
un puente evaluado expresamente. No se instala ni se presupone ese puente.
Para una futura integración basada en Python se recomienda priorizar MT5 por
su vía oficial documentada. Esta elección es una recomendación de arquitectura,
no una afirmación de compatibilidad ya probada. [MetaQuotes: EA de MT4](https://www.metatrader4.com/en/trading-platform/help/autotrading/experts).

## Contrato local y significado de sus resultados

El esquema `BROKER_PAPER_V1` exige `modo=PAPER`, broker y origen explícitos,
`obtenido_ms`, cuenta, instrumento y cotización con bid, ask y tiempo. Se rechazan
campos ausentes/adicionales, decimales no textuales, NaN, infinitos, cotizaciones
cruzadas y datos futuros o más antiguos que el límite suministrado. El llamador
debe aportar `ahora_ms` y `max_edad_ms`; no hay un reloj ni una caducidad universal
ocultos. Ese límite es una política local, no una garantía de frescura del broker.

Los orígenes admitidos son `SINTETICO`, `EXPORTACION_PUBLICA_BINANCE` para Spot y
`EXPORTACION_DEMO_MT5` para MT5. La cadena de origen es una declaración suministrada;
no autentica al emisor. Tampoco lo hace SHA256: solo identifica el contenido.
Los ejemplos completos y reproducibles están en `test_broker_adapters.py`,
funciones `snapshot_spot()`, `snapshot_mt5()` y `BrokerAdaptersTests.economia()`.
Todos esos datos son inventados para probar el programa y no describen una cuenta.

Spot exige `cuenta=SIN_CUENTA`. MT5 exige alias, servidor, tipo de cuenta, `DEMO`,
divisa y modo de margen de cuenta. No se acepta un campo de contraseña, token,
login o clave; tampoco se busca esa información. El alias es un identificador
local sin capacidad de autenticación. La procedencia demo de un archivo todavía
deberá verificarse cuando exista un proceso de exportación real.

Los modos de cálculo reconocidos en esta primera versión son `FOREX`,
`FOREX_NO_LEVERAGE`, `CFD`, `CFDINDEX` y `CFDLEVERAGE`. Se conservan como metadatos;
no se ejecutan fórmulas. Otros modos requieren ampliar explícitamente el contrato.
Los swaps conservan modo, valores largo/corto y día de triple swap, sin convertirlos
a dinero. No se reconstruye el calendario de financiación a partir de esas tres
propiedades. Los valores de tick son positivos y se exige su divisa de cuenta.
Un valor ausente o cero se rechaza en esta versión conservadora, aunque eso pueda
obligar a recapturar una especificación válida del terminal. [MetaQuotes:
propiedades de símbolos](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants),
[symbol_info](https://www.mql5.com/en/docs/python_metatrader5/mt5symbolinfo_py).

`leer_economia()` acepta únicamente un `ContratoMt5Paper`, un escenario exacto
(lado, lotes, precios y horizonte) y evidencia `ECONOMIA_MT5_PAPER_V1` ligada al
hash del snapshot. Comprueba el rango/incremento de lotes, incrementos de precio,
divisa, tiempo y métodos declarados. Devuelve los importes aportados de beneficio
bruto, comisiones como débito, swap con signo y margen aislado; no los recalcula,
no produce rentabilidad neta ni decide tamaño de posición.

Para un origen sintético exige métodos `SINTETICO`. Para una exportación demo exige
`ORDER_CALC_PROFIT` y `ORDER_CALC_MARGIN`. También exige importe de comisiones,
swap y referencia de costes; no convierte datos desconocidos en cero. Esta
comprobación verifica la forma y coherencia local, no la autenticidad ni la
corrección financiera de los importes. La etiqueta de método no ejecuta MT5.

`order_calc_profit` devuelve una estimación en divisa de cuenta según el entorno
actual de la cuenta. Si las divisas difieren, no debe reemplazarse ese contexto
con una fórmula Spot: hacen falta las conversiones/cotizaciones pertinentes o
resultados exportados del terminal para el escenario. Un resultado capturado
hoy no calibra automáticamente un replay histórico. [MetaQuotes: order_calc_profit](https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcprofit_py).

`order_calc_margin` calcula margen en la divisa de cuenta sin considerar las
órdenes pendientes y posiciones abiertas actuales. Su resultado aislado no es
margen disponible ni una evaluación de cartera o del riesgo de liquidación.
[MetaQuotes: order_calc_margin](https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcmargin_py).

## Bloqueos concretos para una captura real futura

| Dato o dependencia | Estado en este trabajo | Qué falta comprobar |
|---|---|---|
| Acceso Binance público | No probado por este módulo | Disponibilidad regional/red y captura original fechada del símbolo |
| Cuenta XM demo | No consultada | Cuenta demo correspondiente a MT5 y entidad que la ofrece |
| Servidor | No identificado | Nombre exacto asignado a esa demo; no deducirlo de la marca |
| Tipo de cuenta | No identificado | Tipo efectivo y sus condiciones; no asumir Standard, Micro o Ultra Low |
| Terminal e integración Python | No inspeccionados ni instalados | Ruta/versión/compatibilidad y sesión demo elegida expresamente |
| Instrumentos | No consultados | Nombres/sufijos exactos, disponibilidad, horarios y propiedades del servidor |
| Contrato y divisas | Solo fixtures | Exportación de las especificaciones; no inferirlas del ticker |
| Costes y conversiones | Solo fixtures | Tarifas de la cuenta, swaps/calendario y valoración en divisa de cuenta |
| Ejecución PAPER MT5 | No integrada | Contabilidad de contratos, escenarios y política de simulación propios |

No hace falta resolver esos accesos para ejecutar las pruebas locales. El siguiente
paso técnico puede ser un importador de archivos exportados y anonimizados, que
conserve fuente y hora de captura, valide la identidad y muestre bloqueos en PAPER.
Ese importador no existe todavía. Cualquier captura desde terminal o consulta de
cuenta sería un alcance nuevo y separado; este módulo no las activa.

## Verificación y límites pendientes

Se ejecutaron 16 pruebas sintéticas con resultado correcto mediante:

```text
.venv\Scripts\python.exe -B -m unittest test_broker_adapters -v
```

Cubren separación de mercados, capacidades, inmutabilidad, caducidad, números,
metadatos obligatorios, cuenta demo, secretos/campos inesperados, swaps,
escenarios fuera de incrementos, vinculación de evidencia y ausencia de imports
de transporte/terminal/persistencia. No constituyen una prueba de conexión ni
validación contra una cuenta XM/Binance. Tampoco validan el comportamiento de
fills, slippage, cartera, impuestos, financiación histórica o tarifas actuales.

Fuentes actualizables: revisar documentación de APIs y terminal al implementar
una captura o cambiar de versión; recapturar las condiciones de cuenta/símbolo y
costes para el escenario estudiado. Las pruebas sintéticas son material de prueba,
no una fuente de parámetros financieros.
