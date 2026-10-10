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

logger = logging.getLogger(__name__)

DEFAULT_RULES = Path("config/desk_rules.json")
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

    @classmethod
    def load(cls, path: Path = DEFAULT_RULES) -> "DeskRules":
        if not Path(path).exists():
            return cls()
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        r = cls(Decimal(str(d.get("min_reward_risk", "1.5"))), Decimal(str(d.get("round_number_buffer_pct", "0.3"))),
                Decimal(str(d.get("max_funding_against_pct", "0.05"))), float(d.get("min_sentiment_against", -0.5)),
                float(d.get("scout_volume_mult", 2.0)), float(d.get("scout_move_pct", 1.5)),
                int(d.get("scout_alert_every_min", 30)))
        if r.min_reward_risk <= 0 or r.round_number_buffer_pct < 0 or r.scout_volume_mult <= 1:
            raise ValueError("desk rules out of range")
        return r


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
