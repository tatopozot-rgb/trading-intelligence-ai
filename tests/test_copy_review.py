"""Capture (CSV -> snapshot), owner review with keep/stop advice, and learning across
captures. Synthetic figures only."""
import csv
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from trading_intelligence.copy_trading import capture, review
from trading_intelligence.copy_trading.learning import forward_return, learn
from trading_intelligence.copy_trading.models import Market, ReportedStats, TraderRecord
from trading_intelligence.copy_trading.sources import Snapshot, parse_snapshot

TEMPLATE = Path(__file__).resolve().parents[1] / "docs/templates/copy_trading_capture.template.csv"
GOOD = {"trader_id": "good", "name": "good", "market": "SPOT", "active": "yes", "profit_share_pct": "10",
        "aum_usd": "100000", "copiers": "50", "max_leverage": "1", "roi_7d": "1", "roi_30d": "4", "roi_90d": "10",
        "roi_180d": "20", "mdd_pct": "12", "lead_days": "300", "trades": "120", "win_rate_pct": "60",
        "symbols": "BTCUSDT:50;ETHUSDT:50", "last_pnls": ";".join(["5", "3", "-1", "4", "2", "6"] * 4)}


def _rows(*overrides: dict) -> list[dict]:
    return [{**GOOD, **o} for o in overrides]


def _snap(rows, when="2026-10-08T15:00:00-05:00") -> Snapshot:
    return parse_snapshot(capture.rows_to_snapshot(rows, when))


class TestCapture:
    def test_the_template_converts(self):
        with TEMPLATE.open(encoding="utf-8-sig", newline="") as fh:
            data = capture.rows_to_snapshot(list(csv.DictReader(fh)), "2026-10-08T15:00:00-05:00")
        assert data["source"] == "binance_app_manual" and len(data["traders"]) == 2
        assert data["traders"][1]["active"] is False

    def test_values_are_read_as_shown_in_the_app(self):
        t = _snap(_rows({"roi_30d": "4.5%", "aum_usd": "1,200,000", "active": "sí"})).traders[0]
        assert t.reported.roi_pct_by_days[30] == Decimal("4.5") and t.aum_usd == Decimal("1200000") and t.active
        assert t.symbol_share == {"BTCUSDT": Decimal("0.5"), "ETHUSDT": Decimal("0.5")}

    @pytest.mark.parametrize("override,message", [
        ({"mdd_pct": ""}, "mdd_pct"),
        ({"active": "maybe"}, "active"),
        ({"roi_30d": "abc"}, "roi_30d"),
        ({"symbols": "BTCUSDT"}, "BTCUSDT:45"),
        ({"symbols": "BTCUSDT:30;ETHUSDT:30"}, "100%"),
        ({"market": "MARGIN"}, "MARGIN"),
    ])
    def test_bad_rows_are_rejected_with_the_line(self, override, message):
        with pytest.raises(ValueError, match=message):
            capture.rows_to_snapshot(_rows(override), "2026-10-08T15:00:00-05:00")

    def test_a_capture_time_needs_a_timezone(self):
        with pytest.raises(ValueError, match="timezone"):
            capture.rows_to_snapshot(_rows({}), "2026-10-08T15:00:00")

    def test_cli(self, tmp_path):
        out = tmp_path / "s.json"
        assert capture.main([str(TEMPLATE), "--captured-at", "2026-10-08T15:00:00-05:00", "--out", str(out)]) == 0
        assert json.loads(out.read_text(encoding="utf-8"))["traders"]
        bad = tmp_path / "bad.csv"
        bad.write_text("trader_id,market\nx,SPOT\n", encoding="utf-8")
        assert capture.main([str(bad), "--captured-at", "2026-10-08T15:00:00-05:00", "--out", str(tmp_path / "b.json")]) == 1


class TestReview:
    def _write(self, folder: Path, name: str, rows, when) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(json.dumps(capture.rows_to_snapshot(rows, when)), encoding="utf-8")

    def test_followed_traders_get_keep_or_stop(self, tmp_path):
        rows = _rows({"trader_id": "good"}, {"trader_id": "quitter", "active": "no"},
                     {"trader_id": "short", "lead_days": "60"})
        r = review.run_review([_snap(rows)], ["good", "quitter", "short"])
        by = {d.trader_id: d.decision for d in r.decisions}
        assert by == {"good": "KEEP", "quitter": "REMOVE_INVALIDATED", "short": "REMOVE_WIND_DOWN"}
        assert r.stop_now == ["quitter"]
        text = review.render(r)
        assert "DEJAR DE COPIAR YA" in text and "dejó de liderar" in text and "MANTENER" in text

    def test_cli_turns_red_only_when_a_copied_trader_must_stop(self, tmp_path):
        folder = tmp_path / "snaps"
        self._write(folder, "a.json", _rows({"trader_id": "good"}, {"trader_id": "q", "active": "no"}),
                    "2026-10-08T15:00:00-05:00")
        out = tmp_path / "out"
        assert review.main(["--snapshots", str(folder), "--followed", str(folder / "followed.json"),
                            "--out", str(out)]) == 0
        (folder / "followed.json").write_text(json.dumps({"followed": ["q"]}), encoding="utf-8")
        assert review.main(["--snapshots", str(folder), "--followed", str(folder / "followed.json"),
                            "--out", str(out)]) == 1
        assert json.loads((out / "review.json").read_text(encoding="utf-8"))["stop_now"] == ["q"]

    def test_unofficial_and_template_files_are_skipped_not_trusted(self, tmp_path):
        folder = tmp_path / "snaps"
        self._write(folder, "a.json", _rows({}), "2026-10-08T15:00:00-05:00")
        (folder / "scraped.json").write_text(json.dumps({"source": "leaderboard_scraper",
                                                         "captured_at": "2026-10-08T00:00:00+00:00"}))
        snaps, skipped = review.load_snapshots(folder)
        assert len(snaps) == 1 and any("scraped.json" in s and "not an official" in s for s in skipped)

    def test_no_snapshots_yet(self, tmp_path, capsys):
        assert review.main(["--snapshots", str(tmp_path / "none"), "--out", str(tmp_path / "o")]) == 0
        assert "Todavía no hay capturas" in capsys.readouterr().out


NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)


def _rec(tid, *, daily=(), roi=None, active=True, when=NOW, mdd="10", lead=300):
    reported = ReportedStats({k: Decimal(str(v)) for k, v in (roi or {}).items()}, Decimal(mdd), lead, 100) \
        if roi is not None else None
    return TraderRecord(tid, tid, Market.SPOT, "binance_app_manual", when, active,
                        tuple(Decimal(str(x)) for x in daily), symbol_share={"BTCUSDT": Decimal("0.5"),
                                                                             "ETHUSDT": Decimal("0.5")},
                        closed_trade_pnls=tuple(Decimal(5) for _ in range(30)), reported=reported)


class TestLearning:
    def test_forward_return_from_a_daily_series_is_exact(self):
        r = _rec("x", daily=[0.003] * 100 + [0.01, 0.02])  # only the last 2 days may count
        value, basis = forward_return(r, 2)
        assert basis == "daily_series" and value == pytest.approx(1.01 * 1.02 - 1)

    def test_forward_return_from_app_windows_uses_the_shortest_covering_window(self):
        r = _rec("x", roi={7: 1.5, 30: 4, 90: 9})
        assert forward_return(r, 7) == (pytest.approx(0.015), "reported_7d_window")
        assert forward_return(r, 10) == (pytest.approx(0.04), "reported_30d_window")
        assert forward_return(r, 200)[0] is None

    def test_selected_vs_rest_disappearances_and_stability(self):
        good_roi = {7: 1, 30: 4, 90: 10, 180: 20}
        bad_roi = {7: -1, 30: -6, 90: -15, 180: -30}
        t0 = Snapshot("binance_app_manual", NOW, [
            _rec("a", roi=good_roi), _rec("b", roi=good_roi), _rec("bad", roi=bad_roi, mdd="50")], [])
        t1 = Snapshot("binance_app_manual", NOW + timedelta(days=7), [
            _rec("a", roi={7: 2, 30: 5, 90: 10, 180: 20}, when=NOW + timedelta(days=7)),
            _rec("bad", roi={7: -3, 30: -6, 90: -15, 180: -30}, mdd="50", when=NOW + timedelta(days=7))], [])
        s = learn([t1, t0])  # order does not matter
        assert len(s.periods) == 1 and s.periods[0].gap_days == 7
        assert s.selected_mean == pytest.approx(0.02) and s.others_mean == pytest.approx(-0.03)
        assert s.edge == pytest.approx(0.05)
        assert s.selected_disappeared == 1 and s.selected_total == 2  # b vanished: counted, not dropped
        assert s.rank_stability == pytest.approx(0.5)
        assert s.criterion_effect["DRAWDOWN_TOO_DEEP"]["failed_mean"] == pytest.approx(-0.03)
        assert s.criterion_effect["DRAWDOWN_TOO_DEEP"]["passed_mean"] == pytest.approx(0.02)

    def test_one_capture_teaches_nothing(self):
        assert learn([Snapshot("binance_app_manual", NOW, [_rec("a", roi={7: 1})], [])]).periods == []
