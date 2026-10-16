"""
Long-horizon trend on gold and BTC with one signal a month, research only.

Preregistered in docs/research/largo/PREREGISTRO.md before any run: Faber's 10-month mean (long or out), 12-month
time-series momentum (long or short, Moskowitz, Ooi and Pedersen) and Antonacci's dual momentum (the better of BTC and
gold over 12 months, only if positive). Signal at each month's last daily close, trade at the next open, 100% of the
capital at 1x, no stop. Gold: PAXGUSDT without weekends and XM's real GOLD costs (spread, swap per night, Wednesday
triple). BTC: perpetual costs with real funding. Judged against the practice desk in both years and by the deflated
Sharpe of 2025-26 with N = the decisive tests of docs/research/REGISTRO_PRUEBAS.md.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from trading_intelligence.backtesting import real_data_validation as rdv
from trading_intelligence.backtesting import research_deflactado as rd
from trading_intelligence.backtesting import two_way_backtest as tw

YEARS = (("2024-10-12", "2025-10-12"), ("2025-10-13", "2026-10-13"))
WARM_FROM = "2023-06-01"
CAPITAL = 1000.0
DESK = {"2024-10-12": {"líder": 1.67, "re-medida": 1.73}, "2025-10-13": {"líder": -0.21, "re-medida": 0.20}}
SYMBOLS = {"oro": "PAXGUSDT", "btc": "BTCUSDT"}
GOLD_HALF_SPREAD, GOLD_SLIP = 0.20, 0.05  # USD per ounce and side (XM GOLD: 0.40 spread)
GOLD_SWAP_LONG, GOLD_SWAP_SHORT = -0.84, 0.21  # USD per ounce and night
BTC_FEE, BTC_SLIP = 0.0005, 0.0002
FABER_MONTHS, MOM_MONTHS = 10, 12
DECISIVE_N = 252
OUT_DIR = Path("docs/research/largo")
RULES = {"faber_oro": "Media de 10 meses, oro", "faber_btc": "Media de 10 meses, BTC",
         "mom_oro": "Momento de 12 meses, oro", "mom_btc": "Momento de 12 meses, BTC",
         "dual": "Momento dual BTC u oro"}


@dataclass
class Asset:
    name: str
    open: pd.Series
    close: pd.Series
    funding: pd.Series  # % paid by a long that UTC day (BTC); zero for gold


def month_end_closes(close: pd.Series) -> pd.Series:
    """The last daily close of each calendar month, indexed by that day."""
    c = close.dropna()
    last = c.groupby(c.index.tz_localize(None).to_period("M")).tail(1)
    return last


def faber(close: pd.Series) -> pd.Series:
    me = month_end_closes(close)
    return (me > me.rolling(FABER_MONTHS).mean()).astype(int)


def momentum(close: pd.Series) -> pd.Series:
    me = month_end_closes(close)
    past = me.shift(MOM_MONTHS)
    return pd.Series(np.where(past.isna(), 0, np.sign(me - past)), index=me.index).astype(int)


def dual(btc: pd.Series, gold: pd.Series) -> pd.Series:
    """'btc', 'oro' or '' at each month end (on the BTC calendar)."""
    mb, mg = month_end_closes(btc), month_end_closes(gold)
    rb_ = (mb / mb.shift(MOM_MONTHS) - 1)
    rg = (mg / mg.shift(MOM_MONTHS) - 1)
    rg.index = rg.index.tz_localize(None).to_period("M")
    out = []
    for t, r_btc in rb_.items():
        r_gold = rg.get(t.tz_localize(None).to_period("M"), np.nan)
        best = max(((r_btc, "btc"), (r_gold, "oro")), key=lambda x: -np.inf if pd.isna(x[0]) else x[0])
        out.append(best[1] if pd.notna(best[0]) and best[0] > 0 else "")
    return pd.Series(out, index=rb_.index)


def targets_by_day(signal: pd.Series, days: pd.DatetimeIndex, to_target: Any) -> list[Any]:
    """The target in force on each day: the last month-end signal strictly before that day."""
    idx = signal.index.searchsorted(days, side="left") - 1
    return [to_target(signal.iloc[k]) if k >= 0 else to_target(None) for k in idx]


@dataclass
class Book:
    assets: dict[str, Asset]
    mult: float = 1.0
    cash: float = CAPITAL
    pos: Optional[dict] = None  # {asset, side, qty, fill, t, carry}
    equity: list[float] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    carry_total: float = 0.0
    days_in: int = 0

    def _fill(self, a: str, px: float, side: int, entry: bool) -> float:
        sign = side if entry else -side
        if a == "oro":
            return px + sign * (GOLD_HALF_SPREAD + GOLD_SLIP) * self.mult
        return px * (1 + sign * BTC_SLIP * self.mult)

    def _fee(self, a: str, notional: float) -> float:
        return 0.0 if a == "oro" else BTC_FEE * self.mult * notional

    def open_(self, a: str, side: int, px: float, t: pd.Timestamp) -> None:
        fill = self._fill(a, px, side, True)
        equity = self.cash
        qty = equity / fill
        fee = self._fee(a, qty * fill)
        self.cash -= fee
        self.pos = {"asset": a, "side": side, "qty": qty, "fill": fill, "t": t, "pnl": -fee}

    def close_(self, px: float, t: pd.Timestamp, why: str) -> None:
        p = self.pos
        assert p is not None
        out = self._fill(p["asset"], px, p["side"], False)
        pnl = p["side"] * p["qty"] * (out - p["fill"]) - self._fee(p["asset"], p["qty"] * out)
        self.cash += pnl
        total = p["pnl"] + pnl
        self.trades.append({"asset": p["asset"], "side": p["side"], "entry": str(p["t"].date()), "exit": str(t.date()),
                            "why": why, "ret_pct": total / (p["qty"] * p["fill"]) * 100})
        self.pos = None

    def carry(self, t: pd.Timestamp) -> None:
        """Gold swap for a night held (weekdays, Wednesday triple) or BTC funding for the UTC day."""
        p = self.pos
        if p is None:
            return
        a = self.assets[p["asset"]]
        if p["asset"] == "oro":
            if t.dayofweek >= 5:
                return
            nights = 3 if t.dayofweek == 2 else 1
            rate = GOLD_SWAP_LONG * self.mult if p["side"] > 0 else GOLD_SWAP_SHORT
            amount = rate * p["qty"] * nights
        else:
            f = float(a.funding.get(t, tw.FUNDING_PER_8H * 100 * 3))
            ref = float(a.open.get(t, p["fill"]))
            paid = p["side"] * f
            amount = -paid / 100 * p["qty"] * ref * (self.mult if paid > 0 else 1.0)
        self.cash += amount
        p["pnl"] += amount
        self.carry_total += amount

    def mark(self, t: pd.Timestamp) -> None:
        p = self.pos
        if p is None:
            self.equity.append(self.cash)
            return
        c = self.assets[p["asset"]].close.loc[:t].dropna()
        px = float(c.iloc[-1]) if len(c) else p["fill"]
        self.equity.append(self.cash + p["side"] * p["qty"] * (px - p["fill"]))
        self.days_in += 1


def simulate(assets: dict[str, Asset], days: pd.DatetimeIndex, wanted: list[tuple[str, int]],
             mult: float = 1.0) -> Book:
    """wanted[k] = (asset, side) to hold on days[k], ('', 0) for out. Trades at the open of an asset's own candle."""
    book = Book(assets, mult)
    for k, t in enumerate(days):
        a_want, s_want = wanted[k]
        cur = (book.pos["asset"], book.pos["side"]) if book.pos else ("", 0)
        if cur != (a_want, s_want):
            if book.pos is not None:
                px = book.assets[cur[0]].open.get(t, np.nan)
                if pd.notna(px):
                    book.close_(float(px), t, "señal")
            if book.pos is None and a_want:
                px = assets[a_want].open.get(t, np.nan)
                if pd.notna(px):
                    book.open_(a_want, s_want, float(px), t)
        if k == len(days) - 1:
            book.mark(t)
            if book.pos is not None:
                c = book.assets[book.pos["asset"]].close.loc[:t].dropna()
                book.close_(float(c.iloc[-1]), t, "fin")
                book.equity[-1] = book.cash
            break
        book.carry(t)
        book.mark(t)
    return book


def stats(book: Book, days: pd.DatetimeIndex) -> dict:
    e = np.r_[CAPITAL, book.equity]
    peak = np.maximum.accumulate(e)
    dd = float(((peak - e) / peak).max() * 100)
    net = (e[-1] / CAPITAL - 1) * 100
    T, a, q = len(book.equity), 0, []
    for k in range(4):
        b = min(T, a + (T - a) // (4 - k))
        q.append(round((e[b] / e[a] - 1) * 100, 2))
        a = b
    r = pd.Series(e).pct_change().dropna()
    m = rd.moments(r)
    return {"net_pct": round(net, 2), "max_dd_pct": round(dd, 2), "net_dd": round(net / dd, 2) if dd > 0 else None,
            "trades": len(book.trades), "days_in": book.days_in, "days": T, "carry_usd": round(book.carry_total, 2),
            "quarters": q, "sharpe_anual": round(m["sr_anual"], 2), "moments": m,
            "worst_pct": round(min((x["ret_pct"] for x in book.trades), default=0.0), 2),
            "trade_list": book.trades,
            "daily_equity": {str(d.date()): round(v, 2) for d, v in zip(days, book.equity)}}


def wanted_for(rule: str, assets: dict[str, Asset], days: pd.DatetimeIndex) -> list[tuple[str, int]]:
    if rule == "dual":
        sig = dual(assets["btc"].close, assets["oro"].close)
        return targets_by_day(sig, days, lambda x: (x, 1) if x else ("", 0))
    kind, a = rule.split("_")
    sig = faber(assets[a].close) if kind == "faber" else momentum(assets[a].close)
    return targets_by_day(sig, days, lambda x: (a, int(x)) if x else ("", 0))


def calendar(rule: str, assets: dict[str, Asset], a: str, b: str) -> pd.DatetimeIndex:
    src = assets["oro"] if rule.endswith("_oro") else assets["btc"]
    idx = src.close.dropna().index
    return idx[(idx >= pd.Timestamp(a, tz="UTC")) & (idx < pd.Timestamp(b, tz="UTC"))]


def year(assets: dict[str, Asset], a: str, b: str, n_decisive: int) -> dict:
    rows: dict[str, Any] = {}
    for rule in RULES:
        days = calendar(rule, assets, a, b)
        want = wanted_for(rule, assets, days)
        for mult, label in ((1.0, ""), (2.0, ", costes ×2")):
            s = stats(simulate(assets, days, want, mult), days)
            m = s["moments"]
            s["dsr"] = round(rd.deflated_sharpe(m["sr_dia"], m["T"], m["asimetria"], m["curtosis"], n_decisive,
                                                1 / m["T"]), 3)
            rows[rule + label] = s
    hold = {}
    for name, asset in assets.items():
        c = asset.close.dropna()
        c = c[(c.index >= pd.Timestamp(a, tz="UTC")) & (c.index < pd.Timestamp(b, tz="UTC"))]
        hold[name] = round((c.iloc[-1] / c.iloc[0] - 1) * 100, 2) if len(c) else None
    return {"from": a, "to": b, "rows": rows, "hold_pct": hold, "desk": DESK.get(a, {})}


def verdict(years: list[dict]) -> list[str]:
    lines = []
    for rule, name in RULES.items():
        beats = all((y["rows"][rule]["net_dd"] or -99) > y["desk"]["líder"] for y in years)
        beats_now = all((y["rows"][rule]["net_dd"] or -99) > y["desk"]["re-medida"] for y in years)
        dsr = years[-1]["rows"][rule]["dsr"]
        ok = beats and dsr >= rd.PASS_DSR
        nd = " ; ".join(f"{y['rows'][rule]['net_dd']}" for y in years)
        extra = "" if beats == beats_now else f" (contra la mesa re-medida: {'gana' if beats_now else 'no gana'})"
        lines.append(f"- **{name}: {'pasa' if ok else 'no pasa'}.** Neto/caída {nd} contra 1,67 ; −0,21 "
                     f"({'gana' if beats else 'no gana'} los dos años{extra}); Sharpe deflactado 2025-26 {dsr} "
                     f"(listón {rd.PASS_DSR}).")
    lines.append("- Todas son muestra corta: una señal al mes da pocas operaciones.")
    return lines


def render(years: list[dict], n_decisive: int) -> str:
    L = ["# Tendencia de horizonte largo en oro y BTC (una señal al mes)", "",
         "Preregistro: `docs/research/largo/PREREGISTRO.md`, escrito antes de correr. 100% del capital, 1x, sin stop. "
         "Oro con los costes reales de GOLD en XM demo (diferencial 0,40, swap largo −0,84 y corto +0,21 USD por onza y "
         "noche, miércoles triple). BTC como perpetuo con financiación real. Sharpe deflactado con N = "
         f"{n_decisive} pruebas decisorias (`docs/research/REGISTRO_PRUEBAS.md`).", "", "## Veredicto", "",
         *verdict(years)]
    for y in years:
        L += ["", f"## {y['from']} → {y['to']} (comprar y mantener: oro {y['hold_pct'].get('oro')}%, BTC "
              f"{y['hold_pct'].get('btc')}%; mesa de práctica neto/caída {y['desk'].get('líder')}, re-medida "
              f"{y['desk'].get('re-medida')})", "",
              "| Regla | Neto % | Máx. caída | Neto/caída | Ops | Días dentro | Swap o financiación (USD) | "
              "Peor op. | Sharpe anual | Sharpe deflactado | Trimestres (neto %) |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for key, r in y["rows"].items():
            base, _, extra = key.partition(",")
            name = RULES[base] + ("," + extra if extra else "")
            L.append(f"| {name} | {r['net_pct']:+.1f}% | {r['max_dd_pct']}% | {r['net_dd']} | {r['trades']} | "
                     f"{r['days_in']} de {r['days']} | {r['carry_usd']:+.1f} | {r['worst_pct']:+.1f}% | "
                     f"{r['sharpe_anual']} | {r['dsr']} | " + " / ".join(f"{q:+.1f}" for q in r["quarters"]) + " |")
    L += ["", "Con costes ×2 se doblan el diferencial, el deslizamiento, la comisión y lo que se paga de swap o "
          "financiación; lo que se cobra queda igual. El capital diario de cada regla está en el JSON.", "",
          "Advertencias: PAXG como precio del oro; BTC Spot como precio del perpetuo; pocas operaciones por año. Un "
          "resultado pasado no promete uno futuro."]
    return "\n".join(L) + "\n"


def load() -> dict[str, Asset]:
    start = datetime.fromisoformat(WARM_FROM).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(YEARS[-1][1]).replace(tzinfo=timezone.utc) + timedelta(days=2)
    rdv.INTERVAL_MS.setdefault("1d", 86_400_000)
    out = {}
    for name, sym in SYMBOLS.items():
        k = rdv.fetch_klines(sym, "1d", start, end)
        if name == "oro":
            k = k[k.index.dayofweek < 5]
            fund = pd.Series(0.0, index=k.index)
        else:
            f = tw.fetch_funding(sym, start, end)
            fund = (f.groupby(pd.DatetimeIndex(f.index).floor("D")).sum() if not f.empty else pd.Series(dtype=float))
            fund = fund.reindex(k.index).fillna(tw.FUNDING_PER_8H * 100 * 3)
        out[name] = Asset(name, k["open"].astype(float), k["close"].astype(float), fund.astype(float))
        print(f"{name}: {len(k)} días")
    return out


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Tendencia de horizonte largo en oro y BTC (investigación)")
    parser.add_argument("--decisorias", type=int, default=DECISIVE_N)
    parser.add_argument("--salida", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    assets = load()
    years = [year(assets, a, b, args.decisorias) for a, b in YEARS]
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).date().isoformat()
    (args.salida / f"largo_{stamp}.json").write_text(json.dumps(years, indent=1, default=str), encoding="utf-8")
    report = render(years, args.decisorias)
    (args.salida / f"largo_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
