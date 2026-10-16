"""
Copying traders with a winning year: Hyperliquid vaults, research only.

Preregistered in docs/research/copiar/PREREGISTRO.md before any run. A vault is pure copy trading with no delay, so
it is the best case for a follower. At the start of each protocol year, eligible vaults (created 365+ days before,
still alive, 10k USD or more, positive return over the previous 365 days) are ranked; rule A takes the 10 best by
return, rule B the 10 best by return / max drawdown. Equal parts, buy and hold one year, 10% of each vault's gain
goes to the leader. Also measures whether the top vaults stay on top. Public reads only: no account, no key, no orders.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from scipy import stats as st

from trading_intelligence.backtesting import research_deflactado as rd

VAULTS_URL = "https://stats-data.hyperliquid.xyz/Mainnet/vaults"
INFO_URL = "https://api.hyperliquid.xyz/info"
BINANCE_LIST = "https://www.binance.com/bapi/futures/v1/friendly/future/copy-trade/home-page/query-list"
KLINES = "https://data-api.binance.vision/api/v3/klines"
YEARS = (("2024-10-12", "2025-10-12"), ("2025-10-13", "2026-10-13"))
DESK = {"2024-10-12": 1.67, "2025-10-13": -0.21}
DECISIVE_N = 259
MIN_TVL, TOP, LEADER_CUT = 10_000.0, 10, 0.10
DAY_MS = 86_400_000
OUT_DIR = Path("docs/research/copiar")


@dataclass
class Vault:
    address: str
    name: str
    created_ms: int
    closed: bool
    times: np.ndarray   # ms, ascending
    index: np.ndarray   # time-weighted return index, 1.0 at the first point
    value: np.ndarray   # account value, USD


def _get(url: str, body: Optional[dict] = None, tries: int = 4) -> Any:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json",
                                                           "User-Agent": "research"})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:  # public read, no key
                return json.loads(r.read())
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** (i + 1))


def build_index(av: list, pnl: list) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Index from allTime [ms, value] and [ms, cumulative pnl] histories: r = d(pnl) / value before."""
    a = {int(t): float(v) for t, v in av}
    p = {int(t): float(v) for t, v in pnl}
    ts = sorted(set(a) & set(p))
    if not ts:
        return np.array([], dtype=np.int64), np.array([]), np.array([])
    idx = [1.0]
    for k in range(1, len(ts)):
        prev = a[ts[k - 1]]
        r = (p[ts[k]] - p[ts[k - 1]]) / prev if prev >= 1.0 else 0.0
        idx.append(idx[-1] * max(1.0 + r, 0.0))
    return np.array(ts, dtype=np.int64), np.array(idx), np.array([a[t] for t in ts])


def at(v: Vault, ms: int, arr: Optional[np.ndarray] = None) -> float:
    """Last value at or before ms (step function); NaN before the first point."""
    arr = v.index if arr is None else arr
    k = int(np.searchsorted(v.times, ms, side="right")) - 1
    return float(arr[k]) if k >= 0 else float("nan")


def max_dd(x: np.ndarray) -> float:
    if len(x) == 0:
        return 0.0
    peak = np.maximum.accumulate(x)
    return float(np.max(1 - x / np.where(peak > 0, peak, 1)) * 100)


def window(v: Vault, a: int, b: int) -> np.ndarray:
    """Index values from a to b, starting with the value at a."""
    m = (v.times > a) & (v.times <= b)
    return np.r_[at(v, a), v.index[m]]


def formation(v: Vault, start: int) -> Optional[dict]:
    a = start - 365 * DAY_MS
    if v.created_ms > a or len(v.times) == 0 or v.times[-1] <= start:
        return None
    if at(v, start, v.value) < MIN_TVL:
        return None
    w = window(v, a, start)
    if not np.isfinite(w[0]) or w[0] <= 0:
        return None
    ret = (w[-1] / w[0] - 1) * 100
    dd = max_dd(w)
    return {"ret": ret, "dd": dd, "score": ret / dd if dd > 0 else ret * 1e6}


def follower_curve(vs: list[Vault], a: int, b: int, cut: float) -> pd.Series:
    """Equal parts at a, held to b; each part's running gain pays `cut` to the leader. Daily marks at 00:00 UTC."""
    days = np.arange(a, b + 1, DAY_MS)
    parts = []
    for v in vs:
        base = at(v, a)
        g = np.array([at(v, int(d)) / base for d in days]) - 1
        parts.append(1 + g - cut * np.maximum(g, 0))
    eq = np.mean(parts, axis=0) if parts else np.ones(len(days))
    return pd.Series(eq, index=pd.to_datetime(days, unit="ms", utc=True))


def hold_return(v: Vault, a: int, b: int) -> float:
    return (at(v, b) / at(v, a) - 1) * 100


def year(vaults: list[Vault], a_s: str, b_s: str, n_tests: int) -> dict:
    a = int(pd.Timestamp(a_s, tz="UTC").value // 1_000_000)
    b = int(pd.Timestamp(b_s, tz="UTC").value // 1_000_000)
    elig = [(v, f) for v in vaults if (f := formation(v, a)) and f["ret"] > 0]
    by_ret = sorted(elig, key=lambda x: -x[1]["ret"])
    by_score = sorted(elig, key=lambda x: -x[1]["score"])
    rules = {"A, los que más ganaron": (by_ret[:TOP], LEADER_CUT, True),
             "B, los más parejos": (by_score[:TOP], LEADER_CUT, True),
             "A con 30% para el líder": (by_ret[:TOP], 0.30, False),
             "A, top 30": (by_ret[:30], LEADER_CUT, False)}
    rows = {}
    for name, (pick, cut, decisive) in rules.items():
        c = follower_curve([v for v, _ in pick], a, b, cut)
        net = (c.iloc[-1] - 1) * 100
        dd = max_dd(c.to_numpy())
        r = c.pct_change().dropna()
        dsr = None
        if len(r) > 2 and r.std() > 0:
            m = rd.moments(r)
            dsr = round(rd.deflated_sharpe(m["sr_dia"], m["T"], m["asimetria"], m["curtosis"], n_tests, 1 / m["T"]), 3)
        rows[name] = {"decisoria": decisive, "n": len(pick), "neto_pct": round(net, 1), "caida_pct": round(dd, 1),
                      "neto_caida": round(net / dd, 2) if dd > 0 else None, "dsr": dsr,
                      "vaults": [{"name": v.name, "address": v.address, "previo_pct": round(f["ret"], 1),
                                  "previo_caida": round(f["dd"], 1), "siguiente_pct": round(hold_return(v, a, b), 1),
                                  "caida_siguiente": round(max_dd(window(v, a, b)), 1), "cerro": v.closed}
                                 for v, f in pick],
                      "capital_diario": [round(x, 5) for x in c.tolist()]}
    # persistence (not tests)
    nxt = {v.address: hold_return(v, a, b) for v, _ in elig}
    order = sorted(nxt, key=lambda k: -nxt[k])
    rank = {k: i for i, k in enumerate(order)}
    top = [v for v, _ in by_ret[:TOP]]
    half = len(order) / 2
    pers = {"elegibles": len(elig),
            "top10_sigue_top10": sum(rank[v.address] < TOP for v in top),
            "top10_mitad_de_arriba": sum(rank[v.address] < half for v in top),
            "top10_pierde": sum(nxt[v.address] < 0 for v in top),
            "top10_cae_mas_50": sum(max_dd(window(v, a, b)) > 50 for v in top),
            "top10_cerradas": sum(v.closed for v in top),
            "mediana_elegibles_siguiente_pct": round(float(np.median(list(nxt.values()))), 1) if nxt else None,
            "elegibles_que_pierden": sum(x < 0 for x in nxt.values())}
    if len(elig) >= 5:
        rho, pv = st.spearmanr([f["ret"] for _, f in elig], [nxt[v.address] for v, _ in elig])
        pers["spearman"], pers["p"] = round(float(rho), 2), round(float(pv), 3)
    return {"from": a_s, "to": b_s, "rows": rows, "persistencia": pers, "desk": DESK.get(a_s)}


def btc_hold(a_s: str, b_s: str) -> Optional[float]:
    try:
        a = int(pd.Timestamp(a_s, tz="UTC").value // 1_000_000)
        b = int(pd.Timestamp(b_s, tz="UTC").value // 1_000_000)
        k = _get(f"{KLINES}?symbol=BTCUSDT&interval=1d&startTime={a}&endTime={b}&limit=1000")
        return round((float(k[-1][4]) / float(k[0][1]) - 1) * 100, 1)
    except Exception:
        return None


def load_vaults(probe: bool) -> tuple[list[Vault], dict]:
    raw = _get(VAULTS_URL)
    info = {"lista": len(raw), "muestra": raw[:2] if probe else None}
    keep = []
    for e in raw:
        s = e.get("summary", e)
        rel = (s.get("relationship") or {}).get("type", "normal")
        if rel in ("parent", "child"):
            continue
        keep.append(s)
    info["sin_protocolo"] = len(keep)
    # only vaults old enough for the second year's formation can matter
    last_needed = int(pd.Timestamp(YEARS[1][0], tz="UTC").value // 1_000_000) - 365 * DAY_MS
    keep = [s for s in keep if int(s.get("createTimeMillis", 0)) <= last_needed]
    info["con_edad"] = len(keep)
    out = []
    failed = 0
    for i, s in enumerate(keep):
        try:
            d = _get(INFO_URL, {"type": "vaultDetails", "vaultAddress": s["vaultAddress"]})
        except Exception:
            failed += 1
            continue
        if probe and i == 0:
            info["detalle_muestra"] = {k: (v if k != "portfolio" else [[p[0], {kk: vv[:3] if isinstance(vv, list) else vv
                                                                              for kk, vv in p[1].items()}] for p in v])
                                       for k, v in d.items() if k != "followers"}
        port = dict(d.get("portfolio", []))
        allt = port.get("allTime", {})
        t, idx, val = build_index(allt.get("accountValueHistory", []), allt.get("pnlHistory", []))
        if len(t):
            out.append(Vault(s["vaultAddress"], s.get("name", ""), int(s.get("createTimeMillis", 0)),
                             bool(s.get("isClosed", d.get("isClosed", False))), t, idx, val))
        time.sleep(1.0)
        if probe and i >= 4:
            break
    info["fallidas"] = failed
    info["con_historia"] = len(out)
    info["primer_punto_mas_viejo"] = min((int(v.times[0]) for v in out), default=None)
    return out, info


def binance_snapshot(pages: int = 100) -> dict:
    """Current Binance Futures lead traders, last 180 days (informative: only the living ones are listed)."""
    rows: list[dict] = []
    try:
        for page in range(1, pages + 1):
            body = {"pageNumber": page, "pageSize": 20, "timeRange": "180D", "dataType": "ROI", "favoriteOnly": False,
                    "hideFull": False, "nickname": "", "order": "DESC", "portfolioType": "PUBLIC"}
            data = (_get(BINANCE_LIST, body, tries=2) or {}).get("data") or {}
            lst = data.get("list") or []
            rows += [{k: r.get(k) for k in ("roi", "pnl", "aum", "mdd", "copierPnl", "currentCopyCount")} for r in lst]
            if not lst:
                break
            time.sleep(0.5)
    except Exception as e:  # informative only
        if not rows:
            return {"ok": False, "error": str(e)[:200]}
    def f(x: Any) -> float:
        try:
            return float(x)
        except (TypeError, ValueError):
            return 0.0
    cp = [f(r["copierPnl"]) for r in rows]
    top = rows[:20]
    return {"ok": True, "lideres": len(rows), "copiadores_ganan": sum(c > 0 for c in cp),
            "copiadores_pierden": sum(c < 0 for c in cp), "suma_copier_pnl": round(sum(cp)),
            "suma_pnl_lider": round(sum(f(r["pnl"]) for r in rows)),
            "top20_roi_mediana": round(float(np.median([f(r["roi"]) for r in top])), 1) if top else None,
            "top20_copiadores_pierden": sum(f(r["copierPnl"]) < 0 for r in top),
            "top20_suma_copier_pnl": round(sum(f(r["copierPnl"]) for r in top)),
            "top20_mdd_mediana": round(float(np.median([f(r["mdd"]) for r in top])), 1) if top else None}


def judge(years: list[dict], name: str) -> tuple[bool, str]:
    ok = all((y["rows"][name]["neto_caida"] or -1e9) > y["desk"] for y in years)
    dsr = years[-1]["rows"][name]["dsr"] or 0.0
    return ok and dsr >= rd.PASS_DSR, "; ".join(f"{y['rows'][name]['neto_caida']} contra {y['desk']}" for y in years) + f"; DSR {dsr}"


def report(years: list[dict], info: dict, bnb: dict) -> str:
    L = ["# Copiar a los que llevan un año ganando: bóvedas de Hyperliquid", "",
         f"Corrido {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. Preregistro: `PREREGISTRO.md`. "
         f"Bóvedas en la lista: {info.get('lista')}; sin las del protocolo: {info.get('sin_protocolo')}; con edad "
         f"suficiente: {info.get('con_edad')}; con historia leída: {info.get('con_historia')}.", ""]
    for name in ("A, los que más ganaron", "B, los más parejos"):
        ok, why = judge(years, name)
        L.append(f"- **{name}: {'pasa' if ok else 'no pasa'}** ({why}).")
    for y in years:
        L += ["", f"## {y['from']} → {y['to']} (BTC comprar y mantener {y.get('btc_pct')}%; mesa neto/caída "
                  f"{y['desk']})", "", "| Regla | Bóvedas | Neto % | Caída % | Neto/caída | DSR | Tipo |",
              "|---|---|---|---|---|---|---|"]
        for n, r in y["rows"].items():
            L.append(f"| {n} | {r['n']} | {r['neto_pct']} | {r['caida_pct']} | {r['neto_caida']} | {r['dsr']} | "
                     f"{'decisoria' if r['decisoria'] else 'sensibilidad'} |")
        p = y["persistencia"]
        L += ["", f"¿Siguen arriba? Elegibles: {p['elegibles']}. De las 10 mejores del año previo: "
                  f"{p['top10_sigue_top10']} siguen en el top 10, {p['top10_mitad_de_arriba']} quedan en la mitad de "
                  f"arriba, {p['top10_pierde']} pierden plata, {p['top10_cae_mas_50']} caen más de 50% y "
                  f"{p['top10_cerradas']} están cerradas hoy. Mediana de todas las elegibles el año siguiente: "
                  f"{p['mediana_elegibles_siguiente_pct']}%; pierden {p['elegibles_que_pierden']}. "
                  f"Spearman año previo contra siguiente: {p.get('spearman')} (p {p.get('p')}).", "",
              "| Bóveda (regla A) | Año previo % | Caída previa % | Año siguiente % | Caída siguiente % |",
              "|---|---|---|---|---|"]
        for v in y["rows"]["A, los que más ganaron"]["vaults"]:
            L.append(f"| {v['name'][:40]} | {v['previo_pct']} | {v['previo_caida']} | {v['siguiente_pct']} | "
                     f"{v['caida_siguiente']} |")
    if bnb.get("ok"):
        L += ["", "## Foto de Binance Futures, últimos 180 días (informativa, solo líderes vivos)", "",
              f"Líderes leídos (por ROI, de mayor a menor): {bnb['lideres']}. Con copiadores en ganancia: "
              f"{bnb['copiadores_ganan']}; en pérdida: {bnb['copiadores_pierden']}. Suma de la ganancia de los "
              f"copiadores: {bnb['suma_copier_pnl']} USDT; de los líderes: {bnb['suma_pnl_lider']} USDT. Los 20 de "
              f"mayor ROI: ROI mediano {bnb['top20_roi_mediana']}%, caída mediana {bnb['top20_mdd_mediana']}%, "
              f"copiadores en pérdida en {bnb['top20_copiadores_pierden']} de 20, suma de los copiadores "
              f"{bnb['top20_suma_copier_pnl']} USDT."]
    else:
        L += ["", f"Foto de Binance: no se pudo leer ({bnb.get('error')})."]
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="only dump the data shape, no test")
    args = ap.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    vaults, info = load_vaults(args.probe)
    bnb = binance_snapshot(2 if args.probe else 100)
    if args.probe:
        (OUT_DIR / "probe.json").write_text(json.dumps({"info": info, "binance": bnb}, indent=1, default=str)[:400_000])
        print(json.dumps(info, default=str)[:3000])
        return
    years = []
    for a, b in YEARS:
        y = year(vaults, a, b, DECISIVE_N)
        y["btc_pct"] = btc_hold(a, b)
        years.append(y)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (OUT_DIR / f"copiar_{stamp}.json").write_text(json.dumps({"info": info, "years": years,
                                                              "binance": bnb}, indent=1))
    text = report(years, info, bnb)
    (OUT_DIR / f"copiar_{stamp}.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
