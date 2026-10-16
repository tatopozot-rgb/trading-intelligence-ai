# Preregistro: ¿copiar a los traders que llevan un año ganando habría dejado plata? (2026-10-16)

Escrito el 2026-10-16, **antes** de correr nada. Pregunta del dueño (2026-10-16): "copiar a los top traders,
¿serviría? Creo que no, porque uno ve sus operaciones tarde". Nada se cambia después de ver el resultado.

## Por qué Hyperliquid y no Binance

- El historial de los lead traders de Binance solo se ve en la web (7, 30, 90 y 180 días) y la lista muestra a los
  que siguen vivos: los que quebraron desaparecen (sesgo del sobreviviente). No se puede reconstruir "el top de
  hace un año" ni su año siguiente. Desde esta sesión, además, `binance.com` está bloqueado; la corrida de GitHub
  intenta leer la lista actual solo como foto informativa.
- Las **bóvedas de Hyperliquid** son copy trading puro: el seguidor deposita y la bóveda hace las mismas
  operaciones del líder, sin retraso. El historial completo (valor y ganancia de cada bóveda) es público en la
  cadena y la lista incluye las bóvedas **cerradas**, así que el sesgo del sobreviviente es mucho menor.
- Es el **mejor caso** para copiar: cero retraso y las comisiones ya van dentro de la ganancia de la bóveda. Si
  esto no gana, copiar con retraso en Binance gana menos.

## Datos

- `https://stats-data.hyperliquid.xyz/Mainnet/vaults` (lista de bóvedas, con cerradas) y
  `https://api.hyperliquid.xyz/info` con `{"type": "vaultDetails"}` (historia "allTime" de valor y ganancia).
  Lectura pública, sin cuenta, sin clave, sin órdenes.
- Se excluyen las bóvedas del protocolo (HLP y sus hijas: relación "parent" o "child").
- Rentabilidad entre dos puntos de la historia: ganancia del tramo / valor de la bóveda al inicio del tramo
  (rentabilidad ponderada en el tiempo: no cuenta como ganancia los depósitos y retiros). Tramos con valor inicial
  menor a 1 USD se ignoran. Entre puntos, el índice se mantiene igual (sin interpolar).
- BTC comprar y mantener: velas diarias de `data-api.binance.vision`.

## Regla

- Años (los del protocolo): 2024-10-12 → 2025-10-12 y 2025-10-13 → 2026-10-13.
- En la fecha de inicio de cada año, **elegible** = bóveda creada al menos 365 días antes, con historia después de
  esa fecha (no cerrada antes), valor ≥ 10.000 USD ese día y **rentabilidad positiva en los 365 días previos**
  ("más de un año ganando").
- **A, los que más ganaron:** las 10 elegibles con mayor rentabilidad de los 365 días previos.
- **B, los más parejos:** las 10 elegibles con mayor rentabilidad / caída máxima de los 365 días previos.
- Partes iguales, se compra y se mantiene un año, sin rebalancear. Una bóveda que cierra o deja de tener historia
  queda en lo último que valía. Si hay menos de 10 elegibles, entran todas y se dice "muestra corta".
- **Parte del líder:** al final se descuenta el 10% de la ganancia de cada bóveda (lo que cobra Hyperliquid; en
  Binance el líder cobra 10% o más). La curva diaria lo descuenta sobre la ganancia acumulada de cada día.

## Sensibilidad (solo informativa, nunca decide)

- Parte del líder 30% (el tope que permiten algunas plataformas).
- Top 30 en vez de top 10, regla A.

## Lo que se mide aparte (no son pruebas: no operan reglas nuevas)

- **¿Siguen arriba?** De las 10 mejores al inicio de cada año, cuántas siguen en el top 10 y en la mitad de arriba
  al final del año siguiente, cuántas pierden plata, cuántas caen más de 50% y cuántas cierran.
- Correlación de rangos (Spearman) entre la rentabilidad del año previo y la del año siguiente, en todas las
  elegibles.
- Mediana de todas las elegibles en el año siguiente.
- Foto de Binance Futures (agregada tras la lectura de prueba, que confirmó que GitHub sí la lee): los primeros
  2.000 lead traders por ROI de 180 días; cuántos tienen a sus copiadores en ganancia o en pérdida y la suma de lo
  que ganaron los copiadores contra lo que ganaron los líderes. Solo líderes vivos: no es prueba.

## Cómo se juzga (fijado ahora)

- **Pasa a práctica** solo si su neto/caída supera al de la mesa de práctica en **los dos años** (referencia del
  líder: 1,67 y −0,21) **y** su Sharpe deflactado de 2025-26 es al menos 0,95, con N = 259 decisorias (257 + estas
  dos) y V = 1/T, sobre los rendimientos diarios de la curva.
- Se informa también contra BTC comprar y mantener.
- No es una estrategia que la mesa pueda operar sola: si pasara, el siguiente paso sería observar hacia adelante,
  con dinero ficticio, antes de pensar en depositar en una bóveda. El dinero real no cambia por este estudio.
