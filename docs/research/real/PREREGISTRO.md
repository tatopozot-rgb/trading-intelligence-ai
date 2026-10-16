# Preregistro: el bot real de futuros por los dos listones (2026-10-16)

Escrito el 2026-10-16, **antes** de correr nada. Encargo del líder (2026-10-16): pasar por los dos listones la
estrategia que opera con dinero real (`trading_intelligence/live/binance_futures.py --modo real`) con sus parámetros
y su lista de monedas actuales, y recomendar para el real: seguir igual, bajar el tamaño o pausar las entradas nuevas.
Solo análisis: nada en `config/` ni en `live/` cambia. Las filas quedan como "pendiente" en
`docs/research/REGISTRO_PRUEBAS.md` en este mismo commit.

## Qué corre el real hoy

- La mesa de práctica (señal por defecto de 5 minutos, meta 3R, `config/desk_rules.json`) con el freno de régimen
  de BTC (media de 50 días: bajo ella cierra y solo abre largos) y el freno de eventos (±2 h, `config/eventos.json`).
- `config/futures_limits.json`: 1x aislado, riesgo 1-15% por calidad de la señal, cada posición hasta 50% del
  capital, 3 posiciones, límite de pérdida 45%, meta mensual +58%, las 12 monedas de `allowed_symbols`.
- Capital real: 31,69 USDT.

## Cómo se mide

- El mismo motor que `research_saturado` (`research_mesa.replay` con régimen b y freno de eventos), los dos años
  2024-10-12 → 2025-10-12 y 2025-10-13 → 2026-10-13.
- Costes de Binance Futuros: comisión 0,05% por lado (taker), deslizamiento 0,02% por lado, financiación real cada
  8 h. Mínimos de Binance por orden: BTC 100 USDT, ETH 20 USDT, el resto 5 USDT.
- Bloques de 30 días **encadenados**: cada bloque empieza con el capital con el que terminó el anterior (la meta y el
  límite se cuentan desde el inicio de cada mes, como en el real). Capital diario guardado en el JSON.

## Filas

1. **Real tal cual**: 31,69 USDT, riesgo 1-15% por calidad. Re-medición de la mesa (no cuenta en N).
2. **Real con 1.000 USDT**: lo mismo sin el efecto de los mínimos. Re-medición (no cuenta en N).
3. **Real con riesgo fijo 2%**: 31,69 USDT. Sensibilidad (cuenta en el total, no en las decisorias).

## Listones

La mesa en sí no puede "ganarle a la mesa": es ella misma. Por eso el primer listón es absoluto:

1. **Neto positivo y neto/caída ≥ 1 en los dos años**, con costes.
2. **Sharpe deflactado ≥ 0,95 en 2025-26** con N = 257 decisorias y V = 1/T, sobre los rendimientos diarios (días
   naturales; cripto opera todos los días). Bailey y López de Prado (2014), `research_deflactado`.

Pasa solo si cumple los dos con la fila 1.

## Recomendación, decidida antes de ver el resultado

- Pasa los dos listones: seguir igual.
- Pasa el primero pero no el segundo: bajar el tamaño (fila 3) si la fila 3 también tiene neto positivo los dos años;
  si no, pausar entradas nuevas.
- No pasa el primero: pausar las entradas nuevas y dejar que las posiciones abiertas terminen con su stop o meta.

Ninguna recomendación se aplica sola: cambiar el bot real o `config/futures_limits.json` exige la frase escrita del
dueño.
