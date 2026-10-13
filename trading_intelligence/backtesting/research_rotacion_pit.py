"""
Point-in-time top-30 momentum rotation (research only: public archive, no key, no orders).

Pre-registered in docs/research/rotacion/PREREGISTRO.md before any result. The earlier study
(research_rotacion) ranked TODAY's top 30 by volume, which is survivorship bias. Here the universe is
rebuilt every day from Binance USDⓈ-M perpetuals as they were then:
  - every USDT perpetual in the public archive (data.binance.vision, delisted ones included), without
    quarterly contracts, stablecoins or index products;
  - on each day, the 30 with the largest quote volume over the 30 previous days (through yesterday),
    each with 30 full days of history.
One fixed rule, not re-tuned: at 00:00 UTC every day rank those 30 by their 14-day return, long the top
3 (a third each) while BTC's last daily close is above its 50-day mean, else flat (research_rotacion
mode "largo3_btc50"). Costs, sizing and 30-day windows as research_rotacion (1h perpetual bars here).
Two years of 12 windows: the blind year (≈2024-10 to 2025-10) decides; the recent year is reported.
Sensitivity: rerun each year without its 2 largest contributors. Baselines: mesa_r3 and BTC buy-and-hold.

    python -m trading_intelligence.backtesting.research_rotacion_pit
"""
from __future__ import annotations

import argparse
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import research_rotacion as rr
from trading_intelligence.backtesting import two_way_backtest as tw

VISION = tw.VISION  # https://data.binance.vision/data/futures/um
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
LIST_PREFIX = "data/futures/um/monthly/klines/"
RULE: dict[str, Any] = {"lookback": 14, "rebalance": 1, "mode": "largo3_btc50"}
TOP_N, VOL_DAYS, YEAR_WINDOWS = 30, 30, 12
NOT_COINS = {"USDC", "FDUSD", "TUSD", "USDP", "DAI", "BUSD", "USDE", "USD1", "RLUSD", "PYUSD", "USDS", "EUR",
             "BTCDOM", "DEFI", "FOOTBALL", "BLUEBIRD"}
OUT_DIR = Path("docs/research/rotacion")

Getter = Callable[[str], Optional[bytes]]  # None when the file does not exist


def _get(url: str) -> Optional[bytes]:
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:  # public archive: no key, no account
                return resp.read(200_000_001)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
        except Exception:  # noqa: BLE001 - network hiccup: retry
            pass
        time.sleep(2 ** attempt)
    return None


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------

def list_symbols(get: Getter = _get) -> list[str]:
    """Every symbol with monthly futures klines in the archive (delisted ones too)."""
    out: list[str] = []
    marker = ""
    while True:
        blob = get(f"{S3}?delimiter=/&prefix={LIST_PREFIX}&marker={urllib.parse.quote(marker)}")
        if blob is None:
            break
        xml = blob.decode("utf-8")
        out += re.findall(re.escape(LIST_PREFIX) + r"([^/<]+)/</Prefix>", xml)
        nxt = re.search(r"<NextMarker>([^<]+)</NextMarker>", xml)
        if "<IsTruncated>true</IsTruncated>" not in xml or nxt is None:
            break
        marker = nxt.group(1)
    return sorted(set(out))


def is_candidate(symbol: str) -> bool:
    return symbol.endswith("USDT") and "_" not in symbol and symbol[:-4] not in NOT_COINS


def parse_klines(blob: bytes) -> pd.DataFrame:
    """A kline zip from the archive (with or without a header row, ms or µs open times)."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        text = z.read(z.namelist()[0]).decode("utf-8")
    rows = [line.split(",") for line in text.splitlines() if line[:1].isdigit()]
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "quote_volume"], dtype=float)
    t = np.array([int(r[0]) for r in rows], dtype=np.int64)
    t = np.where(t > 10**14, t // 1000, t)  # microseconds -> milliseconds
    cols = {"open": 1, "high": 2, "low": 3, "close": 4, "volume": 5, "quote_volume": 7}
    data = {k: np.array([float(r[j]) for r in rows]) for k, j in cols.items()}
    return pd.DataFrame(data, index=pd.to_datetime(t, unit="ms", utc=True))


def fetch_um(symbol: str, interval: str, start: datetime, end: datetime, get: Getter = _get) -> pd.DataFrame:
    """Perpetual klines in [start, end): monthly files, and daily files for the month of `end`."""
    parts = []
    this_month = end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while month < end:
        if month < this_month:
            blob = get(f"{VISION}/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{month:%Y-%m}.zip")
            if blob is not None:
                parts.append(parse_klines(blob))
        else:
            day = month
            while day < end:
                blob = get(f"{VISION}/daily/klines/{symbol}/{interval}/{symbol}-{interval}-{day:%Y-%m-%d}.zip")
                if blob is not None:
                    parts.append(parse_klines(blob))
                day += timedelta(days=1)
        month = (month + timedelta(days=32)).replace(day=1)
    if not parts:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "quote_volume"], dtype=float)
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df[(df.index >= pd.Timestamp(start)) & (df.index < pd.Timestamp(end))]


# ---------------------------------------------------------------------------
# Universe and rule
# ---------------------------------------------------------------------------

def daily_universe(quote_volume: pd.DataFrame, exclude: tuple[str, ...] = (), top_n: int = TOP_N,
                   days: int = VOL_DAYS) -> pd.DataFrame:
    """Per day: is the symbol among the `top_n` by quote volume over the `days` previous days?"""
    qv = quote_volume.drop(columns=[c for c in exclude if c in quote_volume.columns])
    vol = qv.rolling(days, min_periods=days).sum().shift(1)  # through yesterday, 30 full days
    rank = vol.rank(axis=1, ascending=False, method="first")
    return (rank <= top_n).reindex(columns=quote_volume.columns, fill_value=False)


def hourly_mask(universe: pd.DataFrame, m: rr.Market) -> np.ndarray:
    u = universe.reindex(columns=m.symbols, fill_value=False)
    return u.reindex(m.times.normalize()).fillna(False).to_numpy(dtype=bool)


def run_rule(m: rr.Market, eligible: np.ndarray, wins: list[rr.Window]) -> tuple[pd.Series, list[dict]]:
    btc = rr.btc_above_mean(m)
    curves, trades = [], []
    for _, lo, hi in wins:
        run = rr.simulate(m, rr.rotation_signals(m, lo, hi, _btc=btc, eligible=eligible, **RULE), lo, hi)
        curves.append(run.curve)
        trades += run.trades
    return rr.chain(curves), trades


def top_contributors(trades: list[dict], n: int = 2) -> list[str]:
    by: dict[str, float] = {}
    for t in trades:
        by[t["key"]] = by.get(t["key"], 0.0) + t["pnl"]
    return [k for k, v in sorted(by.items(), key=lambda kv: -kv[1])[:n] if v > 0]


def full_quarters(daily: pd.Series, min_days: int = 85) -> dict[str, float]:
    """Net % per calendar quarter, only quarters the period covers almost entirely."""
    if daily.empty:
        return {}
    labels = [rr.quarter(t) for t in daily.index]
    g = daily.groupby(labels)
    return {k: round(float(v) / rr.CAPITAL * 100, 2) for k, v in g.sum().items() if g.size()[k] >= min_days}


def passes(rule: dict, desk: Optional[dict], without_top: Optional[dict], quarters: dict[str, float]) -> dict:
    pos = sum(v > 0 for v in quarters.values())
    out = {"100_operaciones": rule["operaciones"] >= rr.MIN_OOS_TRADES,
           "neto_y_neto_caida_mejor_que_mesa": rule["neto_pct"] > 0 and (
               desk is None or (rule["neto_caida"] is not None
                                and (desk["neto_caida"] is None or rule["neto_caida"] > desk["neto_caida"]))),
           "3_de_4_trimestres": len(quarters) > 0 and pos / len(quarters) >= 0.75,
           "sin_las_2_mejores_sigue_ganando": without_top is not None and without_top["neto_pct"] > 0}
    out["pasa"] = all(out.values())
    return out


# ---------------------------------------------------------------------------
# Study
# ---------------------------------------------------------------------------

def evaluate(m: rr.Market, qv: pd.DataFrame, wins: list[rr.Window], desk: Optional[tuple[pd.Series, list[dict]]],
             btc_curve: pd.Series, walk: bool = True) -> dict:
    eligible = hourly_mask(daily_universe(qv), m)
    curve, trades = run_rule(m, eligible, wins)
    rule = rr.metrics(trades, curve)
    daily = rr.daily_pnl(curve)
    top2 = top_contributors(trades)
    curve2, trades2 = run_rule(m, hourly_mask(daily_universe(qv, exclude=tuple(top2)), m), wins)
    without = rr.metrics(trades2, curve2)
    desk_m = rr.metrics(desk[1], desk[0]) if desk is not None else None
    corr = rr.correlation(daily, rr.daily_pnl(desk[0])) if desk is not None else None
    quarters = full_quarters(daily)
    used: dict[str, int] = {}
    for t in trades:
        used[t["key"]] = used.get(t["key"], 0) + 1
    out = {"desde": str(m.times[wins[0][1]])[:10], "hasta": str(m.times[wins[-1][2] - 1])[:10],
           "regla": rule, "trimestres_completos": quarters, "mesa": desk_m, "btc": rr.metrics([], btc_curve),
           "corr_mesa": corr, "mejores_2": top2, "sin_mejores_2": without,
           "monedas_operadas": dict(sorted(used.items(), key=lambda kv: -kv[1])),
           "criterios": passes(rule, desk_m, without, quarters)}
    if walk:
        wf = rr.walk_forward(m, "rotacion", rr.GRIDS["rotacion"], wins, eligible)
        wf.pop("curva")
        out["walk_forward"] = {"oos": wf["oos"], "folds": wf["folds"]}
    return out


def _fetch_daily(sym: str, start: datetime, end: datetime) -> tuple[str, pd.Series]:
    df = fetch_um(sym, "1d", start, end)
    return sym, df["quote_volume"] if not df.empty else pd.Series(dtype=float)


def _fetch_hourly(sym: str, start: datetime, end: datetime) -> tuple[str, pd.DataFrame, pd.Series]:
    return sym, fetch_um(sym, "1h", start, end), tw.fetch_funding(sym, start, end)


def load(start: datetime, end: datetime, threads: int) -> tuple[rr.Market, pd.DataFrame]:
    symbols = [s for s in list_symbols() if is_candidate(s)]
    print(f"{len(symbols)} perpetuos USDT en el archivo (incluidos los retirados)")
    with ThreadPoolExecutor(threads) as ex:
        got = list(ex.map(lambda s: _fetch_daily(s, start, end), symbols))
    days = pd.date_range(start, end - timedelta(days=1), freq="1D", tz="UTC")
    qv = pd.DataFrame({s: v.reindex(days) for s, v in got if not v.empty}, index=days)
    print(f"volumen diario: {qv.shape[1]} monedas con datos")
    universe = daily_universe(qv)
    needed = sorted(set(universe.columns[universe.any(axis=0)]) | {"BTCUSDT"})
    print(f"{len(needed)} monedas entran al top {TOP_N} algún día")
    with ThreadPoolExecutor(threads) as ex:
        hourly = list(ex.map(lambda s: _fetch_hourly(s, start, end), needed))
    times = pd.date_range(start, end - rr.HOUR, freq="1h", tz="UTC")
    bars = {s: b for s, b, _ in hourly if not b.empty}
    funding = {s: f for s, b, f in hourly if not b.empty}
    return rr.build_market(bars, funding, times), qv


def render(result: dict) -> str:
    lines = ["# Rotación en el top 30 de cada día (prueba pre-registrada)", "",
             "Regla fija de `PREREGISTRO.md`, escrita antes de ver resultados: cada día, de los 30 perpetuos USDⓈ-M "
             "con más volumen en los 30 días anteriores (lista de ese día, incluidas monedas luego retiradas), largo "
             "en las 3 con mejor rendimiento de 14 días, solo si BTC está sobre su media de 50 días. Velas de 1 hora de "
             "los perpetuos, comisión 0,05% y deslizamiento 0,02% por lado, financiación real, 1.000 USDT, 1x. "
             "Ventanas de 30 días que empiezan con 1.000 USDT; el año es la suma de 12 ventanas; la caída se mide en "
             "% de los 1.000 USDT.", ""]
    for name, title in (("ciego", "Año ciego (decide)"), ("reciente", "Año reciente (solo informa)")):
        r = result.get(name)
        if r is None:
            continue
        lines += [f"## {title}: {r['desde']} a {r['hasta']}", "",
                  "| Estrategia | Operaciones | Neto % | Máx. caída | Neto/caída | Acierto | Ganancia / pérdida media | "
                  "Comisiones | Financiación | Correlación con la mesa | Por trimestre |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        rows = [("**Regla pre-registrada**", r["regla"], r["corr_mesa"]),
                (f"Sin {', '.join(r['mejores_2']) or '—'}", r["sin_mejores_2"], None)]
        if r.get("walk_forward"):
            rows.append(("Walk-forward de 18 combinaciones (no decide)", r["walk_forward"]["oos"], None))
        if r["mesa"]:
            rows.append((f"{rr.DESK_BASELINE} (la mesa)", r["mesa"], None))
        rows.append(("BTC comprar y mantener", r["btc"], None))
        for label, s, corr in rows:
            q = " · ".join(f"{k}: {v:+.1f}%" for k, v in s["trimestres"].items())
            lines.append(f"| {label} | {s['operaciones']} | {s['neto_pct']:+.2f}% | {s['max_caida_pct']}% | "
                         f"{s['neto_caida']} | {s['acierto_pct']}% | {s['ganancia_media']:+.2f} / "
                         f"{s['perdida_media']:+.2f} | {s['comisiones_usdt']:.2f} | {s['financiacion_usdt']:+.2f} | "
                         f"{corr if corr is not None else '—'} | {q} |")
        c = r["criterios"]
        marks = {True: "sí", False: "no"}
        lines += ["", f"Criterios: 100+ operaciones {marks[c['100_operaciones']]} · neto positivo y neto/caída mejor que "
                      f"la mesa {marks[c['neto_y_neto_caida_mejor_que_mesa']] if r['mesa'] else '(la mesa no se midió en esta corrida)'} · 3 de 4 trimestres completos "
                      f"{marks[c['3_de_4_trimestres']]} ({r['trimestres_completos']}) · sin las 2 monedas que más "
                      f"aportaron sigue ganando {marks[c['sin_las_2_mejores_sigue_ganando']]}.",
                  "", "Monedas más operadas: " + ", ".join(f"{k} ({v})" for k, v in list(r["monedas_operadas"].items())[:10])
                  + ".", ""]
    blind = result.get("ciego")
    lines += ["## Veredicto", ""]
    if blind is None:
        lines.append("Sin datos suficientes para el año ciego.")
    elif blind["criterios"]["pasa"]:
        lines.append("**Pasa la prueba pre-registrada en el año ciego.** Se propone práctica con dinero ficticio, no dinero "
                     "real.")
    else:
        failed = [k for k, v in blind["criterios"].items() if k != "pasa" and not v]
        lines.append("**No pasa la prueba pre-registrada en el año ciego** (falla: " + ", ".join(failed) + "). Según lo "
                     "escrito antes, no se busca otra combinación que sí pase.")
    lines += ["", "Advertencias: el archivo público puede no tener todas las monedas retiradas; el volumen de un día cuenta "
              "desde el día siguiente; un resultado pasado no promete uno futuro."]
    return "\n".join(lines) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Rotación top 30 de cada día (pre-registrada)")
    parser.add_argument("--sin-mesa", action="store_true", help="skip the mesa_r3 baseline (faster)")
    parser.add_argument("--sin-walk-forward", action="store_true")
    parser.add_argument("--procesos", type=int, default=4)
    parser.add_argument("--hilos", type=int, default=24)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    span = 2 * YEAR_WINDOWS * rr.TEST_DAYS
    start = end - timedelta(days=span + rr.FIT_DAYS + rr.WARM_DAYS + 2)
    m, qv = load(start, end, args.hilos)
    wins = rr.windows(m, span)
    years = {"ciego": wins[:YEAR_WINDOWS], "reciente": wins[YEAR_WINDOWS:]}
    spot, funding = rr.load_market(list(tw.SYMBOLS), start, end)
    prepared = None if args.sin_mesa else rr.load_desk(spot, funding, wins, args.procesos)
    result: dict = {"regla": RULE, "top_n": TOP_N, "dias_volumen": VOL_DAYS}
    for name, w in years.items():
        if len(w) < YEAR_WINDOWS:
            continue
        desk = rr.desk_curve(prepared, spot, w) if prepared is not None else None
        result[name] = evaluate(m, qv, w, desk, rr.buy_and_hold(spot, w), walk=not args.sin_walk_forward)
        r = result[name]
        print(f"{name}: {r['regla']['operaciones']} operaciones, neto {r['regla']['neto_pct']:+.2f}%, caída "
              f"{r['regla']['max_caida_pct']}%, sin {r['mejores_2']}: {r['sin_mejores_2']['neto_pct']:+.2f}% -> "
              f"{'pasa' if r['criterios']['pasa'] else 'no pasa'}")
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = end.date().isoformat()
    (args.salida / f"top30_dia_{stamp}.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    report = render(result)
    (args.salida / f"top30_dia_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
