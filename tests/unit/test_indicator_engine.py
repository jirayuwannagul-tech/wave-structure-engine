"""Tests for analysis/indicator_engine.py"""
import pandas as pd
import pytest

from analysis.indicator_engine import (
    calculate_ema,
    calculate_rsi,
    calculate_atr,
    calculate_macd,
    calculate_volume_ma,
    check_volume_spike,
    check_volume_divergence_bullish,
    check_volume_divergence_bearish,
    check_macd_momentum_turning_bullish,
    check_macd_momentum_turning_bearish,
)


def _df(closes, highs=None, lows=None, volume=None):
    n = len(closes)
    return pd.DataFrame({
        "close": closes,
        "high": highs if highs is not None else [c + 1 for c in closes],
        "low": lows if lows is not None else [c - 1 for c in closes],
        "volume": volume if volume is not None else [1000.0] * n,
    })


# ── calculate_ema ─────────────────────────────────────────────────────────────

def test_calculate_ema_length():
    df = _df(list(range(1, 21)))
    ema = calculate_ema(df, 5)
    assert len(ema) == 20
    assert not ema.isna().all()


def test_calculate_ema_rising_series():
    df = _df(list(range(1, 21)))
    ema = calculate_ema(df, 5)
    assert ema.iloc[-1] > ema.iloc[0]


# ── calculate_rsi ────────────────────────────────────────────────────────────

def test_calculate_rsi_length():
    closes = [100 + i * 0.5 for i in range(30)]
    df = _df(closes)
    rsi = calculate_rsi(df)
    assert len(rsi) == 30


def test_calculate_rsi_range():
    closes = [100 + i * 0.5 for i in range(30)]
    df = _df(closes)
    rsi = calculate_rsi(df)
    valid = rsi.dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


def test_calculate_rsi_above_50_for_rising_prices():
    closes = [100 + i for i in range(30)]
    df = _df(closes)
    rsi = calculate_rsi(df)
    assert rsi.iloc[-1] > 50


# ── calculate_atr ────────────────────────────────────────────────────────────

def test_calculate_atr_length():
    n = 30
    closes = [100.0] * n
    highs = [102.0] * n
    lows = [98.0] * n
    df = _df(closes, highs=highs, lows=lows)
    atr = calculate_atr(df)
    assert len(atr) == n


def test_calculate_atr_positive():
    n = 20
    closes = [100.0] * n
    highs = [103.0] * n
    lows = [97.0] * n
    df = _df(closes, highs=highs, lows=lows)
    atr = calculate_atr(df)
    valid = atr.dropna()
    assert (valid > 0).all()


# ── calculate_macd ───────────────────────────────────────────────────────────

def test_calculate_macd_returns_dataframe():
    closes = [100 + i * 0.3 for i in range(50)]
    df = _df(closes)
    result = calculate_macd(df)
    assert "macd" in result.columns
    assert "macd_signal" in result.columns
    assert "macd_hist" in result.columns
    assert len(result) == 50


def test_calculate_macd_hist_is_macd_minus_signal():
    closes = [100 + i * 0.3 for i in range(50)]
    df = _df(closes)
    result = calculate_macd(df)
    diff = (result["macd"] - result["macd_signal"] - result["macd_hist"]).abs()
    assert diff.max() < 1e-10


# ── calculate_volume_ma ──────────────────────────────────────────────────────

def test_calculate_volume_ma():
    volume = [100.0] * 25
    df = pd.DataFrame({"volume": volume})
    ma = calculate_volume_ma(df, period=20)
    assert len(ma) == 25
    assert ma.iloc[-1] == pytest.approx(100.0)


# ── check_volume_spike ────────────────────────────────────────────────────────

def test_volume_spike_detected():
    volume = [100.0] * 20 + [200.0]
    df = pd.DataFrame({"volume": volume})
    assert check_volume_spike(df, lookback=20, multiplier=1.5) is True


def test_no_volume_spike():
    volume = [100.0] * 21
    df = pd.DataFrame({"volume": volume})
    assert check_volume_spike(df, lookback=20, multiplier=1.5) is False


def test_volume_spike_too_few_rows():
    df = pd.DataFrame({"volume": [100.0] * 5})
    assert check_volume_spike(df, lookback=20) is False


def test_volume_spike_no_volume_column():
    df = pd.DataFrame({"close": [100.0] * 25})
    assert check_volume_spike(df) is False


# ── check_volume_divergence_bullish ────────────────────────────────────────────

def test_bullish_volume_divergence_detected():
    """Price lower lows + volume declining."""
    lows = [100.0, 99.0, 98.0, 97.0, 96.0]
    volumes = [500.0, 400.0, 300.0, 200.0, 100.0]
    df = pd.DataFrame({"low": lows, "volume": volumes})
    assert check_volume_divergence_bullish(df, lookback=5) is True


def test_bullish_volume_divergence_not_detected_when_price_rising():
    lows = [96.0, 97.0, 98.0, 99.0, 100.0]  # rising lows
    volumes = [500.0, 400.0, 300.0, 200.0, 100.0]
    df = pd.DataFrame({"low": lows, "volume": volumes})
    assert check_volume_divergence_bullish(df, lookback=5) is False


def test_bullish_volume_divergence_no_volume_column():
    df = pd.DataFrame({"low": [100.0] * 5, "close": [100.0] * 5})
    assert check_volume_divergence_bullish(df) is False


def test_bullish_volume_divergence_too_few_rows():
    df = pd.DataFrame({"low": [100.0], "volume": [500.0]})
    assert check_volume_divergence_bullish(df, lookback=5) is False


# ── check_volume_divergence_bearish ────────────────────────────────────────────

def test_bearish_volume_divergence_detected():
    """Price higher highs + volume declining."""
    highs = [100.0, 101.0, 102.0, 103.0, 104.0]
    volumes = [500.0, 400.0, 300.0, 200.0, 100.0]
    df = pd.DataFrame({"high": highs, "volume": volumes})
    assert check_volume_divergence_bearish(df, lookback=5) is True


def test_bearish_volume_divergence_not_when_price_falling():
    highs = [104.0, 103.0, 102.0, 101.0, 100.0]  # falling highs
    volumes = [500.0, 400.0, 300.0, 200.0, 100.0]
    df = pd.DataFrame({"high": highs, "volume": volumes})
    assert check_volume_divergence_bearish(df, lookback=5) is False


def test_bearish_volume_divergence_no_high_column():
    df = pd.DataFrame({"close": [100.0] * 5, "volume": [500.0] * 5})
    assert check_volume_divergence_bearish(df) is False


# ── check_macd_momentum_turning_bullish ──────────────────────────────────────

def test_macd_hist_turning_bullish():
    df = pd.DataFrame({"macd_hist": [-0.5, -0.3, -0.1]})
    assert check_macd_momentum_turning_bullish(df, lookback=3) is True


def test_macd_hist_not_turning_bullish():
    df = pd.DataFrame({"macd_hist": [-0.1, -0.3, -0.5]})
    assert check_macd_momentum_turning_bullish(df, lookback=3) is False


def test_macd_hist_bullish_no_column():
    df = pd.DataFrame({"close": [100.0] * 5})
    assert check_macd_momentum_turning_bullish(df) is False


def test_macd_hist_bullish_too_few_rows():
    df = pd.DataFrame({"macd_hist": [-0.3, -0.1]})
    assert check_macd_momentum_turning_bullish(df, lookback=3) is False


# ── check_macd_momentum_turning_bearish ──────────────────────────────────────

def test_macd_hist_turning_bearish():
    df = pd.DataFrame({"macd_hist": [0.5, 0.3, 0.1]})
    assert check_macd_momentum_turning_bearish(df, lookback=3) is True


def test_macd_hist_not_turning_bearish():
    df = pd.DataFrame({"macd_hist": [0.1, 0.3, 0.5]})
    assert check_macd_momentum_turning_bearish(df, lookback=3) is False


def test_macd_hist_bearish_no_column():
    df = pd.DataFrame({"close": [100.0] * 5})
    assert check_macd_momentum_turning_bearish(df) is False


def test_volume_spike_nan_volume():
    """NaN current volume → return False (line 48)."""
    import numpy as np
    df = pd.DataFrame({"volume": [1000.0] * 4 + [np.nan]})
    assert check_volume_spike(df, lookback=3) is False


def test_macd_hist_bullish_nan_values():
    """macd_hist with NaN → return False (line 110)."""
    import numpy as np
    df = pd.DataFrame({"macd_hist": [float("nan"), 0.0, 0.1]})
    assert check_macd_momentum_turning_bullish(df, lookback=3) is False


def test_macd_hist_bearish_nan_values():
    """macd_hist with NaN → return False (line 123)."""
    import numpy as np
    df = pd.DataFrame({"macd_hist": [float("nan"), 0.5, 0.3]})
    assert check_macd_momentum_turning_bearish(df, lookback=3) is False
