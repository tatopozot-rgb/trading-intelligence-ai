"""
Trading desk: six agents on one floor, the owner's design (2026-10-10, "AI Trading Desk: 6 agentes, un
chat, un piso de operaciones"), built on this project's own rules and percentages and optimized for
futures. Every agent here is deterministic code: an LLM may read the journal and research (the
.claude/agents/ subagents), but no model sends an order or overrides the risk rules.

- Scout (24/7, every loop): unusual volume or a sharp move in any watched symbol -> it alerts the Chief,
  who evaluates that symbol at once, even between scheduled decisions (the owner's schedule stays).
- News: recent headlines that name the coin, from fixed, known outlets (RSS), with link and time. Context
  for the journal; it never opens a trade on its own.
- Sentiment: funding rate (crowded side pays), Binance's top traders and the Fear & Greed index ->
  a score from -1 (bearish) to +1 (bullish).
- Charts: the signal (strategy/two_way_signals, "tendencia_rango" mirrored for shorts, 1-hour trend, top
  traders) and the stop/target read from the market (exit_plan).
- Skeptic: hard rules from config/desk_rules.json, never decided by an AI: minimum reward/risk, no stop
  sitting right on a round number where everyone puts theirs, no trade against crowded funding or a
  strongly opposite sentiment. Every veto is journaled and later scored (did it avoid a loss?).
- Chief: the engine (live/two_way.py) — it asks the others, sizes the risk (1-15% with the quality,
  sentiment included), executes, ignores or watches, and journals every decision for Obsidian.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_RULES = Path("config/desk_rules.json")
DEFAULT_EVENTS = Path("config/eventos.json")
NEWS_FEEDS = ("https://www.coindesk.com/arc/outboundfeeds/rss/", "https://cointelegraph.com/rss")
FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1"
COIN_NAMES = {"BTC": ("bitcoin", "btc"), "ETH": ("ether", "ethereum", "eth"), "BNB": ("bnb", "binance coin"),
              "SOL": ("solana", "sol"), "XRP": ("xrp", "ripple"), "DOGE": ("dogecoin", "doge"),
              "ADA": ("cardano", "ada"), "LINK": ("chainlink", "link"), "AVAX": ("avalanche", "avax"),
              "LTC": ("litecoin", "ltc"), "TRX": ("tron", "trx"), "DOT": ("polkadot", "dot")}

Getter = Callable[[str], bytes]


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "trading-intelligence-desk"})
    with urllib.request.urlopen(req, timeout=10) as resp:  # public pages only: no key, no account
        return resp.read(2_000_001)


@dataclass(frozen=True)
class DeskRules:
    min_reward_risk: Decimal = Decimal("1.5")
    round_number_buffer_pct: Decimal = Decimal("0.3")  # a stop this close to a round number is refused
    max_funding_against_pct: Decimal = Decimal("0.05")  # paying more than this per 8h to hold the side: crowded
    min_sentiment_against: float = -0.5  # sentiment at or below this, against the side: refused
    scout_volume_mult: float = 2.0
    scout_move_pct: float = 1.5  # in the last 15 minutes
    scout_alert_every_min: int = 30
    # Take profit 3-5% from the entry (owner, 2026-10-11: "en cada operación intente tener un profit del 3% al 5%
    # ... ese porcentaje después lo controles tu con lo aprendido y lo varies"). None switches the band off.
    target_min_pct: Optional[Decimal] = Decimal("3")
    target_max_pct: Optional[Decimal] = None  # 5% capped the winners in the 2026-10-11 backtest: off (see docs)
    # Bull-run mode (owner, 2026-10-11: "si algún día alguna moneda se va en alza debe dejar el trade de largo ...
    # arriesgar algo no todo"): a coin up this much over these days lets its longs run with the trailing stop.
    rally_lookback_days: int = 14
    rally_min_gain_pct: float = 25.0
    rally_target_pct: Optional[Decimal] = Decimal("50")  # only the trailing stop reaches it; None turns the mode off
    # Reward as a multiple of the risk taken (owner, 2026-10-11: "replantea la ganancia que recompense el riesgo"):
    # the target sits target_r times the stop distance away; None keeps the market's own target.
    target_r: Optional[Decimal] = None
    # Regime brake (leader, 2026-10-13, from research_mesa over two years): only longs, and only while BTC's last
    # closed daily close is above its N-day mean; otherwise flat. None switches it off.
    regime_btc_sma: Optional[int] = None

    @classmethod
    def load(cls, path: Path = DEFAULT_RULES) -> "DeskRules":
        if not Path(path).exists():
            return cls()
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        r = cls(Decimal(str(d.get("min_reward_risk", "1.5"))), Decimal(str(d.get("round_number_buffer_pct", "0.3"))),
                Decimal(str(d.get("max_funding_against_pct", "0.05"))), float(d.get("min_sentiment_against", -0.5)),
                float(d.get("scout_volume_mult", 2.0)), float(d.get("scout_move_pct", 1.5)),
                int(d.get("scout_alert_every_min", 30)),
                _opt_dec(d.get("target_min_pct", "3")), _opt_dec(d.get("target_max_pct")),
                int(d.get("rally_lookback_days", 14)), float(d.get("rally_min_gain_pct", 25.0)),
                _opt_dec(d.get("rally_target_pct", "50")), _opt_dec(d.get("target_r")),
                None if d.get("regime_btc_sma") is None else int(d["regime_btc_sma"]))
        if r.min_reward_risk <= 0 or r.round_number_buffer_pct < 0 or r.scout_volume_mult <= 1:
            raise ValueError("desk rules out of range")
        if (r.target_min_pct is not None and r.target_max_pct is not None and not 0 < r.target_min_pct <= r.target_max_pct) \
                or r.rally_lookback_days < 2 or r.rally_min_gain_pct <= 0 or (r.rally_target_pct is not None and r.rally_target_pct <= 0) \
                or (r.target_r is not None and r.target_r <= 0) \
                or (r.regime_btc_sma is not None and r.regime_btc_sma < 2):
            raise ValueError("desk rules out of range")
        return r


def _opt_dec(x: object) -> Optional[Decimal]:
    return None if x is None else Decimal(str(x))


# --- Take profit and bull-run mode ---------------------------------------------------------------------

def shape_target(entry: Decimal, target: Decimal, side: str, rules: DeskRules, rally: bool = False,
                 stop: Optional[Decimal] = None) -> Decimal:
    """The target: target_r times the risk when set (else the market's), kept within the % band; a long in a bull
    run gets a target only the trailing stop reaches."""
    sign = 1 if side == "BUY" else -1
    if rally and side == "BUY" and rules.rally_target_pct is not None:
        return entry * (1 + rules.rally_target_pct / 100)
    if rules.target_r is not None and stop is not None and stop != entry:
        target = entry + sign * rules.target_r * abs(entry - stop)
    pct = abs(target - entry) / entry * 100
    if rules.target_min_pct is not None:
        pct = max(pct, rules.target_min_pct)
    if rules.target_max_pct is not None:
        pct = min(pct, rules.target_max_pct)
    return entry * (1 + sign * pct / 100)


def btc_regime_up(daily: pd.DataFrame, days: int, now: datetime) -> Optional[bool]:
    """True when BTC's last CLOSED daily close is above its ``days``-day mean; None without enough history."""
    index = pd.DatetimeIndex(daily.index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    closes = daily[index + timedelta(days=1) <= pd.Timestamp(now)]["close"].astype(float)
    if len(closes) < days:
        return None
    return bool(closes.iloc[-1] > closes.tail(days).mean())


def rally(symbol: str, daily: pd.DataFrame, rules: DeskRules) -> Optional[Alert]:
    """A bull run: up ``rally_min_gain_pct`` over the lookback, above its 20-day mean and still rising."""
    if rules.rally_target_pct is None:  # bull-run mode off
        return None
    closes = daily["close"].astype(float)
    n = rules.rally_lookback_days
    if len(closes) < n + 1:
        return None
    last, then = closes.iloc[-1], closes.iloc[-1 - n]
    gain = (last / then - 1) * 100 if then > 0 else 0.0
    rising = last >= closes.iloc[-4] if len(closes) >= 4 else True
    if gain >= rules.rally_min_gain_pct and last > closes.tail(20).mean() and rising:
        return Alert(symbol, f"alcista fuerte: +{gain:.0f}% en {n} días, sobre su media de 20 días y todavía subiendo")
    return None


# --- Scout ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Alert:
    symbol: str
    text: str


def scout(symbol: str, bars, rules: DeskRules) -> Optional[Alert]:
    """Unusual volume on the last closed bar, or a sharp move over the last 3 bars."""
    if bars is None or len(bars) < 25:
        return None
    vol = bars["volume"]
    base = float(vol.iloc[-22:-2].mean())
    last = float(vol.iloc[-2])  # the last CLOSED bar
    close = bars["close"]
    move = (float(close.iloc[-1]) / float(close.iloc[-4]) - 1) * 100 if float(close.iloc[-4]) > 0 else 0.0
    parts = []
    if base > 0 and last / base >= rules.scout_volume_mult:
        parts.append(f"volumen {last / base:.1f}x lo normal")
    if abs(move) >= rules.scout_move_pct:
        parts.append(f"precio {move:+.1f}% en 15 min")
    return Alert(symbol, " y ".join(parts)) if parts else None


# --- News ----------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Headline:
    title: str
    link: str
    published: str
    source: str


def news(symbol: str, get: Getter = _get, now: Optional[datetime] = None, hours: int = 6,
         feeds: tuple[str, ...] = NEWS_FEEDS) -> list[Headline]:
    """Headlines naming the coin in the last hours, from fixed outlets. Never raises: news is context."""
    coin = symbol.replace("USDT", "")
    names = COIN_NAMES.get(coin, (coin.lower(),))
    pattern = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b", re.IGNORECASE)
    now = now or datetime.now(timezone.utc)
    out: list[Headline] = []
    for url in feeds:
        try:
            root = ET.fromstring(get(url))
        except Exception as error:  # noqa: BLE001 - one outlet down must not stop the desk
            logger.info("news: %s unavailable (%s)", url, type(error).__name__)
            continue
        source = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
        for item in root.iter("item"):
            title, link = (item.findtext("title") or "").strip(), (item.findtext("link") or "").strip()
            try:
                when = parsedate_to_datetime(item.findtext("pubDate") or "")
            except (TypeError, ValueError):
                continue
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if title and link.startswith("https://") and now - when <= timedelta(hours=hours) and pattern.search(title):
                out.append(Headline(title, link, when.isoformat(), source))
    return out[:5]


# --- Sentiment -----------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Mood:
    score: float  # -1 bearish .. +1 bullish
    parts: dict = field(default_factory=dict)


def fear_greed(get: Getter = _get) -> Optional[int]:
    try:
        return int(json.loads(get(FEAR_GREED_URL))["data"][0]["value"])
    except Exception:  # noqa: BLE001
        return None


def sentiment(funding_pct: Optional[float], top_ratio: Optional[float], fng: Optional[int]) -> Mood:
    """Funding: longs paying a lot = crowded long (bearish lean), shorts paying = bullish lean.
    Top traders: net long above 1.1, net short below 0.9. Fear & Greed: extreme fear leans bullish
    (contrarian), extreme greed leans bearish."""
    parts: dict = {}
    score = 0.0
    if funding_pct is not None:
        f = max(-1.0, min(1.0, -funding_pct / 0.1))  # -0.1%/8h -> +1, +0.1% -> -1
        parts["financiación"] = round(f, 2)
        score += 0.4 * f
    if top_ratio is not None:
        t = max(-1.0, min(1.0, (top_ratio - 1.0) / 0.5))
        parts["top traders"] = round(t, 2)
        score += 0.4 * t
    if fng is not None:
        g = max(-1.0, min(1.0, (50 - fng) / 50))
        parts["miedo/codicia"] = round(g, 2)
        score += 0.2 * g
    return Mood(round(max(-1.0, min(1.0, score)), 3), parts)


# --- Skeptic -------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Verdict:
    approved: bool
    reasons: tuple[str, ...]


def _near_round(price: Decimal, buffer_pct: Decimal) -> Optional[Decimal]:
    """The nearest 'obvious' round level (1, 2, 5 x a power of ten, two steps below the price's magnitude)."""
    if price <= 0:
        return None
    magnitude = Decimal(10) ** (len(str(int(price))) - 2) if price >= 10 else Decimal("0.1") if price >= 1 else \
        Decimal(10) ** (price.adjusted() - 1)
    for step in (magnitude * 10, magnitude * 5):
        level = (price / step).to_integral_value() * step
        if level > 0 and abs(price - level) / price * 100 <= buffer_pct:
            return level
    return None


def skeptic(side: str, entry: Decimal, stop: Decimal, target: Decimal, mood: Mood,
            funding_pct: Optional[float], rules: DeskRules) -> Verdict:
    reasons = []
    risk, reward = abs(entry - stop), abs(target - entry)
    rr = reward / risk if risk > 0 else Decimal("0")
    if rr < rules.min_reward_risk:
        reasons.append(f"beneficio/riesgo {rr:.2f}:1, menor que el mínimo {rules.min_reward_risk}:1")
    level = _near_round(stop, rules.round_number_buffer_pct)
    if level is not None:
        reasons.append(f"el stop ({stop}) queda pegado al número redondo {level}, donde lo pone todo el mundo")
    if funding_pct is not None:
        against = funding_pct if side == "BUY" else -funding_pct
        if Decimal(str(against)) > rules.max_funding_against_pct:
            reasons.append(f"la financiación ({funding_pct:+.3f}%/8h) dice que ese lado está saturado")
    lean = mood.score if side == "BUY" else -mood.score
    if lean <= rules.min_sentiment_against:
        reasons.append(f"el sentimiento va fuerte en contra ({mood.score:+.2f})")
    return Verdict(not reasons, tuple(reasons))


# --- Journal (for Obsidian) ------------------------------------------------------------------------------

def journal(directory: Path, now: datetime, title: str, lines: list[str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{now.date().isoformat()}.md"
    head = "" if path.exists() else f"# Mesa de trading — {now.date().isoformat()}\n\n"
    body = "\n".join(f"- {line}" for line in lines)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"{head}## {now:%H:%M} UTC · {title}\n\n{body}\n\n")


def event_near(now: datetime, path: Path = DEFAULT_EVENTS) -> Optional[str]:
    """Name of a macro event (FOMC, CPI) within its blackout window around now, else None. Theory §3
    (docs/APRENDIZAJE_TEORIA.md): those hours bring sharp moves and slippage, so the desk opens nothing new.
    A missing or unreadable file blocks nothing."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        window = timedelta(hours=float(data.get("hours", 2)))
        for e in data.get("events", []):
            at = datetime.fromisoformat(str(e["at"]).replace("Z", "+00:00"))
            if abs(now - at) <= window:
                return str(e.get("name", "evento macro"))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return None
