"""
XSP 1-wide bull call spreads with Interactive Brokers costs, research only.

Rules, costs and verdict preregistered in docs/research/opciones_xsp/PREREGISTRO.md before any run. There are no
recorded option prices: each option is valued with Black-Scholes, using the day's VIX as the volatility of both
strikes. XSP = SPX / 10, European, cash-settled. No account, no key, no orders.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as st

from trading_intelligence.backtesting import research_deflactado as rd

YEARS = (("2024-10-12", "2025-10-12"), ("2025-10-13", "2026-10-13"))
WARM_FROM = "2023-09-01"  # 200 trading days before the first year
CAPITAL = 200.0
RATE, DIV = 0.04, 0.013
BLOCK, DTE, WIDTH, MULT = 21, 30, 1.0, 100
COMMISSION, OCC, EXCHANGE, SLIP = 0.65, 0.025, 0.30, 0.03
SAVINGS = 4.0
DECISIVE_N = 259
OUT_DIR = Path("docs/research/opciones_xsp")
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{}?period1=1672531200&period2=1798761600&interval=1d"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
CBOE = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{}_History.csv"


def bs_call(s: float, k: float, t: float, vol: float, r: float = RATE, q: float = DIV) -> float:
    """Black-Scholes price of a European call (t in years)."""
    if t <= 0 or vol <= 0:
        return max(s - k, 0.0)
    sq = vol * math.sqrt(t)
    d1 = (math.log(s / k) + (r - q + vol * vol / 2) * t) / sq
    return s * math.exp(-q * t) * st.norm.cdf(d1) - k * math.exp(-r * t) * st.norm.cdf(d1 - sq)


def spread_value(s: float, k1: float, t: float, vol: float) -> float:
    """Value of one call spread K1/K1+WIDTH in USD (one contract)."""
    if t <= 0:
        return min(max(s - k1, 0.0), WIDTH) * MULT
    return (bs_call(s, k1, t, vol) - bs_call(s, k1 + WIDTH, t, vol)) * MULT


@dataclass
class Book:
    capital: float = CAPITAL
    equity: list[float] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    fees: float = 0.0


def entry_cost(mult: float) -> tuple[float, float]:
    """(fees, slippage) in USD for opening one spread (2 contracts)."""
    return 2 * (COMMISSION + OCC + EXCHANGE) * mult, 2 * SLIP * MULT * mult


def expiry_day(days: pd.DatetimeIndex, start: pd.Timestamp) -> pd.Timestamp:
    """Last trading day on or before start + DTE calendar days (XSP lists daily expiries)."""
    target = start + pd.Timedelta(days=DTE)
    i = int(days.searchsorted(target, side="right")) - 1
    return days[i] if i >= 0 and days[i] > start else target


def run(px: pd.DataFrame, a: str, b: str, trend: bool, mult: float = 1.0) -> Book:
    """px: daily 'spx', 'vix', 'sma200' indexed by date. Trades inside [a, b]; open spread marked on the last day."""
    lo, hi = pd.Timestamp(a), pd.Timestamp(b)
    days = px.index
    year = px[(days >= lo) & (days <= hi)]
    book = Book()
    pos: Optional[dict] = None
    pending = False
    for n, (day, row) in enumerate(year.iterrows()):
        pending = pending or n % BLOCK == 0
        s, vol = row["spx"] / 10, row["vix"] / 100
        if pos is not None and day >= pos["expiry"]:
            payoff = spread_value(s, pos["k1"], 0.0, vol)
            book.capital += payoff
            pos["salida"], pos["pago"] = str(day.date()), round(payoff, 2)
            pos["neto"] = round(payoff - pos["pagado"], 2)
            book.trades.append(pos)
            pos = None
        enter = pos is None and pending and (not trend or row["spx"] > row["sma200"])
        if pos is None:
            pending = False
        if enter:
            k1 = float(round(s))
            fees, slip = entry_cost(mult)
            premium = spread_value(s, k1, DTE / 365, vol)
            paid = premium + slip + fees
            if paid <= book.capital:
                book.capital -= paid
                book.fees += fees
                pos = {"entrada": str(day.date()), "k1": k1, "xsp": round(s, 2), "vix": round(row["vix"], 2),
                       "prima": round(premium, 2), "pagado": round(paid, 2), "expiry": expiry_day(days, day)}
        mark = 0.0
        if pos is not None:
            t = max((pos["expiry"] - day).days, 0) / 365
            mark = spread_value(s, pos["k1"], t, vol)
        book.equity.append(book.capital + mark)
    if pos is not None:
        pos["salida"], pos["pago"] = "abierto (marcado a modelo)", round(book.equity[-1] - book.capital, 2)
        pos["neto"] = round(pos["pago"] - pos["pagado"], 2)
        book.trades.append(pos)
    for t in book.trades:
        t["expiry"] = str(pd.Timestamp(t["expiry"]).date())
    return book


def daily_returns(equity: list[float]) -> pd.Series:
    return pd.Series([CAPITAL] + list(equity)).pct_change().dropna()


def max_drawdown(equity: list[float]) -> float:
    e = np.array([CAPITAL] + list(equity))
    peak = np.maximum.accumulate(e)
    return float(((peak - e) / peak).max() * 100)


def summarize(book: Book, n_decisive: int) -> dict:
    r = daily_returns(book.equity)
    m = rd.moments(r)
    net = (book.equity[-1] / CAPITAL - 1) * 100 if book.equity else 0.0
    wins = sum(1 for t in book.trades if t["neto"] > 0)
    dsr = rd.deflated_sharpe(m["sr_dia"], m["T"], m["asimetria"], m["curtosis"], n_decisive, 1 / m["T"]) if m["T"] > 2 else 0.0
    return {"neto_pct": round(net, 2), "caida_pct": round(max_drawdown(book.equity), 2), "spreads": len(book.trades),
            "ganadores": wins, "comisiones": round(book.fees, 2), "sr_anual": round(m["sr_anual"], 2),
            "dsr": round(dsr, 3), "operaciones": book.trades, "capital_diario": [round(x, 2) for x in book.equity]}


RULES = (("siempre", False, 1.0, True), ("media200", True, 1.0, True),
         ("siempre, costes ×2", False, 2.0, False), ("media200, costes ×2", True, 2.0, False))


def evaluate(px: pd.DataFrame, n_decisive: int) -> dict:
    out: dict = {"reglas": {}, "referencia": {}}
    for name, trend, mult, decisive in RULES:
        years = [summarize(run(px, a, b, trend, mult), n_decisive) for a, b in YEARS]
        ok = all(y["neto_pct"] > SAVINGS for y in years) and years[1]["dsr"] >= rd.PASS_DSR
        out["reglas"][name] = {"decisoria": decisive, "años": years, "pasa": ok if decisive else None}
    for a, b in YEARS:
        y = px[(px.index >= pd.Timestamp(a)) & (px.index <= pd.Timestamp(b))]["spx"]
        out["referencia"][a] = round((y.iloc[-1] / y.iloc[0] - 1) * 100, 2)
    return out


def render(res: dict, n_decisive: int) -> str:
    lines = ["# Spreads alcistas de 1 USD en XSP (Black-Scholes con VIX, costes de IBKR)", "",
             f"Preregistro: `PREREGISTRO.md`. Capital {CAPITAL:.0f} USD por año. N del Sharpe deflactado = {n_decisive}.",
             "**Sin precios grabados de opciones: es un modelo.** Muestra corta (~12 spreads por año).", "",
             "| Regla | Año | Neto % | Caída % | Spreads | Ganadores | Comisiones USD | Sharpe anual | Sharpe deflactado |",
             "|---|---|---|---|---|---|---|---|---|"]
    for name, r in res["reglas"].items():
        for (a, _), y in zip(YEARS, r["años"]):
            lines.append(f"| {name} | {a[:4]}-{int(a[2:4]) + 1} | {y['neto_pct']:+.2f} | {y['caida_pct']:.2f} | {y['spreads']} | "
                         f"{y['ganadores']} | {y['comisiones']:.2f} | {y['sr_anual']:.2f} | {y['dsr']:.3f} |")
    lines += ["", "Referencia, SPX comprar y mantener: " +
              " ; ".join(f"{a[:4]}: {v:+.2f}%" for a, v in res["referencia"].items()), "", "## Veredicto", ""]
    for name, r in res["reglas"].items():
        if r["decisoria"]:
            lines.append(f"- **{name}:** {'pasa' if r['pasa'] else 'no pasa'} (listón: neto > {SAVINGS:.0f}% en los dos "
                         f"años y Sharpe deflactado 2025-26 ≥ {rd.PASS_DSR}).")
    lines += ["", "Aunque pasara, no va a práctica sin repetir la prueba con precios reales de opciones."]
    return "\n".join(lines) + "\n"


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8")


def parse_close(text: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip().lower() for c in df.columns]
    value_col = "close" if "close" in df.columns else df.columns[1]
    idx = pd.to_datetime(df[df.columns[0]], format="mixed")
    values = pd.to_numeric(df[value_col], errors="coerce").values
    return pd.Series(values, index=idx).dropna().sort_index()


def parse_yahoo(text: str) -> pd.Series:
    res = json.loads(text)["chart"]["result"][0]
    idx = pd.to_datetime(res["timestamp"], unit="s").normalize()
    close = pd.to_numeric(pd.Series(res["indicators"]["quote"][0]["close"]), errors="coerce").values
    return pd.Series(close, index=idx).dropna().sort_index()


def fetch(sources: list[tuple[str, str]]) -> pd.Series:
    """First source that answers: ("yahoo" | "csv", url). Errors are printed so the report says which source was used."""
    for kind, url in sources:
        try:
            out = parse_yahoo(_get(url)) if kind == "yahoo" else parse_close(_get(url))
            if len(out) > 300:
                print(f"datos: {url.split('?')[0]}")
                return out
        except Exception as exc:  # next source
            print(f"fuente sin respuesta: {url.split('?')[0]} ({type(exc).__name__})")
    raise RuntimeError("no data source answered")


def load() -> pd.DataFrame:
    series = {
        "spx": fetch([("yahoo", YAHOO.format("%5EGSPC")), ("csv", FRED.format("SP500"))]),
        "vix": fetch([("yahoo", YAHOO.format("%5EVIX")), ("csv", CBOE.format("VIX")), ("csv", FRED.format("VIXCLS"))]),
    }
    px = pd.concat(series, axis=1).dropna()
    px = px[px.index >= pd.Timestamp(WARM_FROM)]
    px["sma200"] = px["spx"].rolling(200).mean()
    return px.dropna()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Spreads XSP de 1 USD (investigación)")
    parser.add_argument("--decisorias", type=int, default=DECISIVE_N)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    px = load()
    res = evaluate(px, args.decisorias)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / f"opciones_xsp_{stamp}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    report = render(res, args.decisorias)
    (args.salida / f"opciones_xsp_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
