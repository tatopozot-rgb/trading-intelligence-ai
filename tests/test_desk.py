"""The trading desk's agents: Scout, News, Sentiment, Skeptic and the journal (owner's design, 2026-10-10)."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import numpy as np
import pandas as pd

from trading_intelligence.live import desk as D

NOW = datetime(2026, 10, 12, 13, 0, tzinfo=timezone.utc)
RULES = D.DeskRules()


def _bars(volumes, closes=None):
    n = len(volumes)
    c = np.array(closes if closes is not None else [100.0] * n, dtype=float)
    idx = pd.date_range(end=NOW, periods=n, freq="5min")
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": np.array(volumes, dtype=float)},
                        index=idx)


def test_scout_flags_unusual_volume_and_sharp_moves_only():
    normal = [10.0] * 40
    assert D.scout("BTCUSDT", _bars(normal), RULES) is None
    spike = [10.0] * 38 + [24.0, 10.0]  # last closed bar 2.4x
    alert = D.scout("BTCUSDT", _bars(spike), RULES)
    assert alert is not None and "2.4x" in alert.text
    jump = D.scout("SOLUSDT", _bars(normal, [100.0] * 37 + [100.0, 101.0, 102.0]), RULES)
    assert jump is not None and "+2.0% en 15 min" in jump.text


RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Bitcoin ETF inflows hit a record</title><link>https://example-news.com/a</link>
<pubDate>Mon, 12 Oct 2026 11:30:00 +0000</pubDate></item>
<item><title>Solana upgrade ships</title><link>https://example-news.com/b</link>
<pubDate>Mon, 12 Oct 2026 12:00:00 +0000</pubDate></item>
<item><title>Bitcoin story from last week</title><link>https://example-news.com/c</link>
<pubDate>Mon, 05 Oct 2026 12:00:00 +0000</pubDate></item>
<item><title>Bitcoin over plain http</title><link>http://example-news.com/d</link>
<pubDate>Mon, 12 Oct 2026 12:00:00 +0000</pubDate></item>
</channel></rss>"""


def test_news_keeps_recent_headlines_that_name_the_coin_with_their_link():
    items = D.news("BTCUSDT", lambda url: RSS.encode(), now=NOW, feeds=("https://example-news.com/rss",))
    assert [h.title for h in items] == ["Bitcoin ETF inflows hit a record"]
    assert items[0].link.startswith("https://") and items[0].source == "example-news.com"


def test_news_never_breaks_the_desk_when_an_outlet_is_down():
    def down(url):
        raise OSError("offline")
    assert D.news("BTCUSDT", down, now=NOW) == []


def test_sentiment_reads_crowded_funding_top_traders_and_fear():
    crowded_longs = D.sentiment(funding_pct=0.08, top_ratio=0.8, fng=85)
    assert crowded_longs.score < -0.5
    fear_and_shorts_paying = D.sentiment(funding_pct=-0.05, top_ratio=1.4, fng=15)
    assert fear_and_shorts_paying.score > 0.5
    assert D.sentiment(None, None, None).score == 0.0


def test_the_skeptic_refuses_the_video_trade():
    """The owner's example: a BTC long at 81,900 with the stop at 79,900, 1.4:1, stop under the $80K everyone uses."""
    v = D.skeptic("BUY", Decimal("81900"), Decimal("79900"), Decimal("84700"), D.Mood(0.0), None, RULES)
    assert not v.approved
    assert any("1.40:1" in r for r in v.reasons) and any("80000" in r for r in v.reasons)


def test_the_skeptic_approves_a_sound_plan_and_refuses_crowded_or_opposed_ones():
    ok = D.skeptic("BUY", Decimal("142.10"), Decimal("137.40"), Decimal("152.30"), D.Mood(0.2), 0.01, RULES)
    assert ok.approved and ok.reasons == ()
    crowded = D.skeptic("BUY", Decimal("142.10"), Decimal("137.40"), Decimal("152.30"), D.Mood(0.0), 0.08, RULES)
    assert not crowded.approved and "saturado" in crowded.reasons[0]
    opposed = D.skeptic("SELL", Decimal("142.10"), Decimal("147.40"), Decimal("131.90"), D.Mood(0.7), None, RULES)
    assert not opposed.approved and "en contra" in opposed.reasons[0]


def test_round_numbers_by_magnitude():
    assert D._near_round(Decimal("79900"), Decimal("0.3")) == Decimal("80000")
    assert D._near_round(Decimal("142.68"), Decimal("0.3")) is None
    assert D._near_round(Decimal("2.499"), Decimal("0.3")) == Decimal("2.5")


def test_rules_come_from_the_committed_file():
    rules = D.DeskRules.load()
    assert rules.min_reward_risk == Decimal("1.5") and rules.scout_volume_mult == 2.0


def test_the_journal_is_markdown_for_obsidian(tmp_path):
    D.journal(tmp_path, NOW, "Chief ejecuta BUY SOLUSDT", ["entrada 142.1", "noticia: [x](https://a)"])
    D.journal(tmp_path, NOW, "Escéptico rechaza", ["motivo: beneficio/riesgo"])
    text = (tmp_path / "2026-10-12.md").read_text(encoding="utf-8")
    assert text.startswith("# Mesa de trading — 2026-10-12") and text.count("## 13:00 UTC") == 2
