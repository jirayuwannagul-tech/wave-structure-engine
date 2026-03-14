import pandas as pd

from analysis.pivot_detector import Pivot
from analysis.indicator_filter import (
    check_atr_expansion,
    detect_aligned_rsi_divergence,
    check_bearish_momentum,
    check_bearish_trend_context,
    check_bullish_momentum,
    check_bullish_trend_context,
    check_long_term_bullish_trend,
    check_long_term_bearish_trend,
    check_bullish_volume_confirmation,
    check_bearish_volume_confirmation,
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


def test_detect_aligned_rsi_divergence_bearish():
    df = pd.DataFrame({"rsi": [50.0, 55.0, 60.0, 57.0, 52.0]})
    pivots = [
        Pivot(index=2, price=100.0, type="H", timestamp=pd.Timestamp("2026-01-01")),
        Pivot(index=4, price=105.0, type="H", timestamp=pd.Timestamp("2026-01-02")),
    ]
    signal = detect_aligned_rsi_divergence("bearish", df, pivots)
    assert signal is not None
    assert signal.state == "BEARISH_RSI_DIVERGENCE"


def test_detect_aligned_rsi_divergence_empty_df_returns_none():
    df = pd.DataFrame({"rsi": []})
    signal = detect_aligned_rsi_divergence("bullish", df, [])
    assert signal is None


def test_detect_aligned_rsi_divergence_unknown_direction():
    df = pd.DataFrame({"rsi": [50.0, 55.0]})
    pivots = [Pivot(index=0, price=100.0, type="L", timestamp="2026-01-01")]
    signal = detect_aligned_rsi_divergence("sideways", df, pivots)
    assert signal is None


# ── Long-term trend (EMA 200) ─────────────────────────────────────────────────

def test_check_long_term_bullish_trend_true():
    df = pd.DataFrame({"close": [105.0], "ema200": [100.0]})
    assert check_long_term_bullish_trend(df) is True


def test_check_long_term_bullish_trend_false():
    df = pd.DataFrame({"close": [95.0], "ema200": [100.0]})
    assert check_long_term_bullish_trend(df) is False


def test_check_long_term_bullish_trend_missing_column():
    df = pd.DataFrame({"close": [105.0]})
    assert check_long_term_bullish_trend(df) is False


def test_check_long_term_bearish_trend_true():
    df = pd.DataFrame({"close": [95.0], "ema200": [100.0]})
    assert check_long_term_bearish_trend(df) is True


def test_check_long_term_bearish_trend_false():
    df = pd.DataFrame({"close": [105.0], "ema200": [100.0]})
    assert check_long_term_bearish_trend(df) is False


# ── Volume confirmation ───────────────────────────────────────────────────────

def test_check_bullish_volume_confirmation_spike():
    volume = [100.0] * 20 + [200.0]
    df = pd.DataFrame({"volume": volume})
    assert check_bullish_volume_confirmation(df) is True


def test_check_bearish_volume_confirmation_spike():
    volume = [100.0] * 20 + [200.0]
    df = pd.DataFrame({"volume": volume})
    assert check_bearish_volume_confirmation(df) is True


def test_volume_confirmation_no_spike():
    volume = [100.0] * 20 + [105.0]
    df = pd.DataFrame({"volume": volume})
    assert check_bullish_volume_confirmation(df) is False


# ── validate_bullish_wave_with_indicators (volume branch) ────────────────────

def test_validate_bullish_with_volume_instead_of_atr():
    """Volume spike (not ATR expansion) should satisfy indicator requirement."""
    n = 21
    volume = [100.0] * 20 + [200.0]
    df = pd.DataFrame(
        {
            "close": [100] * 20 + [110],
            "ema50": [99] * 20 + [100],
            "rsi": [50] * 20 + [60],
            "atr": [10] * n,   # flat ATR — no expansion
            "volume": volume,
        }
    )
    assert validate_bullish_wave_with_indicators(df) is True


def test_validate_bearish_with_volume():
    n = 21
    volume = [100.0] * 20 + [200.0]
    df = pd.DataFrame(
        {
            "close": [100] * 20 + [88],
            "ema50": [101] * 20 + [100],
            "rsi": [50] * 20 + [40],
            "atr": [10] * n,
            "volume": volume,
        }
    )
    assert validate_bearish_wave_with_indicators(df) is True
