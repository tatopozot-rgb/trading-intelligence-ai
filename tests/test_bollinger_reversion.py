"""Tests for BollingerReversion strategy (mean-reversion, built for Regime.RANGE)."""
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from trading_intelligence.strategy.strategies.bollinger_reversion import BollingerReversion


def _make_ohlcv(prices: list, volume: float = 1000.0) -> pd.DataFrame:
    """Create OHLCV DataFrame from close prices. Synthetic OHLC around close."""
    idx = pd.date_range("2020-01-01", periods=len(prices), freq="1D")
    closes = np.array(prices, dtype=float)
    return pd.DataFrame(
        {
            "open": closes * 0.999,
            "high": closes * 1.005,
            "low": closes * 0.995,
            "close": closes,
            "volume": volume,
        },
        index=idx,
    )


# Flat baseline, then a sharp dip (triggers an oversold close below the lower
# band with low RSI), then a bounce that closes back above the lower band
# while RSI is still confirmed-oversold (bar 35), then a recovery toward and
# through the middle band (exit). Values verified bar-by-bar against the real
# bollinger_bands()/rsi() output before being fixed here, per
# STRATEGY_VALIDATION_FRAMEWORK.md's "no ambiguous fixtures" discipline.
_DIP_AND_RECOVERY = (
    [100.0] * 30 + [97.0, 94.0, 91.0, 89.0, 90.5, 92.0, 94.0, 97.0, 100.0, 103.0]
)


class TestBollingerReversionValidation:
    def test_invalid_bb_period(self):
        with pytest.raises(ValueError, match="bb_period"):
            BollingerReversion("BTCUSDT", "1d", params={"bb_period": 1})

    def test_invalid_bb_std(self):
        with pytest.raises(ValueError, match="bb_std"):
            BollingerReversion("BTCUSDT", "1d", params={"bb_std": 0})

    def test_invalid_rsi_thresholds_order(self):
        with pytest.raises(ValueError, match="rsi_oversold"):
            BollingerReversion(
                "BTCUSDT", "1d", params={"rsi_oversold": 60.0, "rsi_exit": 50.0}
            )

    def test_invalid_stop_atr_mult(self):
        with pytest.raises(ValueError, match="stop_atr_mult"):
            BollingerReversion("BTCUSDT", "1d", params={"stop_atr_mult": 0})


class TestBollingerReversionSignals:
    def _strategy(self, **kwargs) -> BollingerReversion:
        params = {"bb_period": 20, "rsi_period": 14, **kwargs}
        return BollingerReversion("BTCUSDT", "1d", params=params)

    def test_no_signal_with_insufficient_data(self):
        strategy = self._strategy()
        data = _make_ohlcv([100.0] * 10)
        assert strategy.on_bar(data) is None

    def test_no_signal_flat_prices(self):
        """Flat prices -> zero std -> bands collapse to the mean -> close is
        never strictly below the lower band -> never oversold -> no signal."""
        strategy = self._strategy()
        data = _make_ohlcv([100.0] * 50)
        assert strategy.on_bar(data) is None

    def test_entry_fires_on_confirmed_reversion_with_valid_stop(self):
        """A dip below the lower band followed by a confirmed bounce (price
        back above the lower band while RSI is still oversold) must produce
        a BUY proposal with a Decimal stop strictly below entry."""
        strategy = self._strategy()
        data = _make_ohlcv(_DIP_AND_RECOVERY)
        proposal = None
        entry_close = None
        for i in range(len(data)):
            sub = data.iloc[: i + 1]
            p = strategy.on_bar(sub)
            if p is not None:
                proposal = p
                entry_close = data["close"].iloc[i]
                break
        assert proposal is not None
        assert isinstance(proposal.stop_price, Decimal)
        assert proposal.stop_price < Decimal(str(entry_close))
        assert proposal.side == "BUY"

    def test_no_entry_when_price_never_closes_below_lower_band(self):
        """Mild sinusoidal noise that never breaches 2 standard deviations
        -> close never falls below the lower band -> the oversold condition
        is never satisfied at any bar -> no signal, regardless of RSI."""
        strategy = self._strategy()
        prices = (100 + np.sin(np.arange(60) / 3.0) * 0.3).tolist()
        data = _make_ohlcv(prices)
        for i in range(len(data)):
            sub = data.iloc[: i + 1]
            assert strategy.on_bar(sub) is None

    def test_exit_signal_on_reversion_to_mean_or_rsi_recovery(self):
        """on_exit_signal returns True once price/RSI have recovered after
        an entry — scanning forward from a known entry bar, same pattern as
        test_ma_crossover.py's exit-signal test."""
        strategy = self._strategy()
        data = _make_ohlcv(_DIP_AND_RECOVERY)
        entry_price = Decimal(str(data["close"].iloc[35]))
        found_exit = False
        for i in range(36, len(data)):
            sub = data.iloc[: i + 1]
            if strategy.on_exit_signal(sub, entry_price):
                found_exit = True
                break
        assert found_exit

    def test_no_exit_signal_with_insufficient_data(self):
        strategy = self._strategy()
        data = _make_ohlcv([100.0] * 10)
        assert strategy.on_exit_signal(data, Decimal("100")) is False
