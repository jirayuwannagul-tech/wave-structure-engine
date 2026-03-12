import pandas as pd

from analysis.pivot_detector import Pivot
from analysis.indicator_filter import (
    check_atr_expansion,
    detect_aligned_rsi_divergence,
    check_bearish_momentum,
    check_bearish_trend_context,
    check_bullish_momentum,
    check_bullish_trend_context,
    validate_bearish_wave_with_indicators,
    validate_bullish_wave_with_indicators,
)


def test_check_bullish_trend_context():
    df = pd.DataFrame(
        {
            "close": [100, 105],
            "ema50": [99, 101],
        }
    )
    assert check_bullish_trend_context(df) is True


def test_check_bearish_trend_context():
    df = pd.DataFrame(
        {
            "close": [100, 95],
            "ema50": [101, 100],
        }
    )
    assert check_bearish_trend_context(df) is True


def test_check_bullish_momentum():
    df = pd.DataFrame({"rsi": [45, 55]})
    assert check_bullish_momentum(df) is True


def test_check_bearish_momentum():
    df = pd.DataFrame({"rsi": [55, 45]})
    assert check_bearish_momentum(df) is True


def test_check_atr_expansion():
    df = pd.DataFrame({"atr": [10] * 19 + [12]})
    assert check_atr_expansion(df, lookback=20) is True


def test_validate_bullish_wave_with_indicators():
    df = pd.DataFrame(
        {
            "close": [100] * 19 + [110],
            "ema50": [99] * 19 + [100],
            "rsi": [50] * 19 + [60],
            "atr": [10] * 19 + [12],
        }
    )
    assert validate_bullish_wave_with_indicators(df) is True


def test_validate_bearish_wave_with_indicators():
    df = pd.DataFrame(
        {
            "close": [100] * 19 + [90],
            "ema50": [101] * 19 + [100],
            "rsi": [50] * 19 + [40],
            "atr": [10] * 19 + [12],
        }
    )
    assert validate_bearish_wave_with_indicators(df) is True


def test_detect_aligned_rsi_divergence_for_bullish_direction():
    df = pd.DataFrame({"rsi": [40.0, 35.0, 30.0, 33.0, 38.0]})
    pivots = [
        Pivot(index=2, price=100.0, type="L", timestamp=pd.Timestamp("2026-01-01")),
        Pivot(index=4, price=95.0, type="L", timestamp=pd.Timestamp("2026-01-02")),
    ]

    signal = detect_aligned_rsi_divergence("bullish", df, pivots)

    assert signal is not None
    assert signal.state == "BULLISH_RSI_DIVERGENCE"
