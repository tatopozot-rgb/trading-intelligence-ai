"""Tests for research_copiar (synthetic data, no network)."""
import numpy as np
import pandas as pd
import pytest

from trading_intelligence.backtesting import research_copiar as rc

DAY = rc.DAY_MS


def _ms(s):
    return int(pd.Timestamp(s, tz="UTC").value // 1_000_000)


def _vault(name, daily, start="2023-01-01", value=50_000.0, closed=False):
    t0 = _ms(start)
    n = len(daily) + 1
    times = [t0 + i * DAY for i in range(n)]
    av, pnl, cum, v = [], [], 0.0, value
    for i, t in enumerate(times):
        av.append([t, str(v)])
        pnl.append([t, str(cum)])
        if i < len(daily):
            g = v * daily[i]
            cum += g
            v += g
    t, idx, val = rc.build_index(av, pnl)
    return rc.Vault(name, name, t0, closed, t, idx, val)


def test_index_ignores_deposits_and_follows_pnl():
    t, idx, _ = rc.build_index([[0, "100"], [1, "1100"], [2, "1210"]], [[0, "0"], [1, "0"], [2, "110"]])
    assert idx.tolist() == pytest.approx([1.0, 1.0, 1.1])


def test_formation_needs_age_size_and_history():
    days = (_ms("2026-10-13") - _ms("2023-01-01")) // DAY
    v = _vault("ok", [0.001] * days)
    f = rc.formation(v, _ms("2025-10-13"))
    assert f and f["ret"] == pytest.approx((1.001 ** 365 - 1) * 100, rel=1e-3)
    young = _vault("young", [0.001] * 500, start="2025-01-01")
    assert rc.formation(young, _ms("2025-10-13")) is None
    small = _vault("small", [0.001] * days, value=1_000.0)
    assert rc.formation(small, _ms("2024-10-12")) is None


def test_leader_cut_and_persistence():
    days = (_ms("2026-10-14") - _ms("2023-01-01")) // DAY
    split = (_ms("2025-10-13") - _ms("2023-01-01")) // DAY
    winners = [_vault(f"w{i}", [0.003] * (split - 30) + [-0.1] + [0.003] * 29 + [-0.002] * (days - split))
               for i in range(10)]
    steady = [_vault(f"s{i}", [0.0005] * days) for i in range(10)]
    y = rc.year(winners + steady, "2025-10-13", "2026-10-13", 259)
    a = y["rows"]["A, los que más ganaron"]
    assert all(v["name"].startswith("w") for v in a["vaults"]) and a["neto_pct"] < 0
    assert y["persistencia"]["top10_sigue_top10"] == 0 and y["persistencia"]["top10_pierde"] == 10
    b = y["rows"]["B, los más parejos"]
    assert all(v["name"].startswith("s") for v in b["vaults"])
    gain = 1.0005 ** 365 - 1
    assert b["neto_pct"] == pytest.approx(gain * 0.9 * 100, abs=0.2)
    assert len(a["capital_diario"]) == 366
