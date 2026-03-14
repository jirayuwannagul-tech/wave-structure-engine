"""Tests for analysis/macd_divergence.py"""
import pandas as pd
import pytest

from analysis.macd_divergence import (
    MACDDivergenceSignal,
    detect_bullish_macd_divergence,
    detect_bearish_macd_divergence,
)
from analysis.pivot_detector import Pivot


def _pivot(index: int, price: float, ptype: str) -> Pivot:
    return Pivot(index=index, price=price, type=ptype, timestamp=f"2026-01-{index:02d}T00:00:00")


def _make_df(length: int, macd_values: list[float]) -> pd.DataFrame:
    """Build a minimal DataFrame with a 'macd' column aligned to pivot indices."""
    close = [100.0 + i for i in range(length)]
    macd_col = macd_values + [0.0] * (length - len(macd_values))
    return pd.DataFrame({"close": close, "macd": macd_col})


# ── Bullish MACD divergence ───────────────────────────────────────────────────

def test_bullish_macd_divergence_detected():
    """Price lower low + MACD higher low → bullish divergence."""
    pivots = [
        _pivot(2, 100.0, "L"),   # first low
        _pivot(5, 90.0, "L"),    # second low (lower)
    ]
    # MACD at index 2 = -0.5, index 5 = -0.3 (higher → bullish divergence)
    df = _make_df(10, [0, 0, -0.5, 0, 0, -0.3, 0, 0, 0, 0])
    signal = detect_bullish_macd_divergence(df, pivots)
    assert signal is not None
    assert signal.direction == "bullish"
    assert signal.state == "BULLISH_MACD_DIVERGENCE"
    assert "lower low" in signal.message


def test_bullish_macd_divergence_not_detected_when_macd_also_lower():
    """Price lower low + MACD also lower low → NOT bullish divergence."""
    pivots = [
        _pivot(2, 100.0, "L"),
        _pivot(5, 90.0, "L"),
    ]
    df = _make_df(10, [0, 0, -0.3, 0, 0, -0.5, 0, 0, 0, 0])
    signal = detect_bullish_macd_divergence(df, pivots)
    assert signal is None


def test_bullish_macd_divergence_not_detected_when_price_higher():
    """Price higher low (no LL) → NOT bullish divergence."""
    pivots = [
        _pivot(2, 90.0, "L"),
        _pivot(5, 100.0, "L"),  # higher low
    ]
    df = _make_df(10, [0, 0, -0.5, 0, 0, -0.3, 0, 0, 0, 0])
    signal = detect_bullish_macd_divergence(df, pivots)
    assert signal is None


def test_bullish_no_lows_returns_none():
    """Only highs → pair is None → returns None."""
    pivots = [_pivot(2, 100.0, "H"), _pivot(5, 110.0, "H")]
    df = _make_df(10, list(range(10)))
    signal = detect_bullish_macd_divergence(df, pivots)
    assert signal is None


def test_bullish_single_low_returns_none():
    """Only one low pivot → pair needs 2 → returns None."""
    pivots = [_pivot(2, 100.0, "L")]
    df = _make_df(10, list(range(10)))
    signal = detect_bullish_macd_divergence(df, pivots)
    assert signal is None


def test_bullish_missing_macd_column():
    """DataFrame without 'macd' column → returns None."""
    pivots = [_pivot(2, 100.0, "L"), _pivot(5, 90.0, "L")]
    df = pd.DataFrame({"close": list(range(10))})
    signal = detect_bullish_macd_divergence(df, pivots)
    assert signal is None


# ── Bearish MACD divergence ───────────────────────────────────────────────────

def test_bearish_macd_divergence_detected():
    """Price higher high + MACD lower high → bearish divergence."""
    pivots = [
        _pivot(2, 100.0, "H"),   # first high
        _pivot(5, 110.0, "H"),   # second high (higher)
    ]
    # MACD at index 2 = 0.5, index 5 = 0.3 (lower → bearish divergence)
    df = _make_df(10, [0, 0, 0.5, 0, 0, 0.3, 0, 0, 0, 0])
    signal = detect_bearish_macd_divergence(df, pivots)
    assert signal is not None
    assert signal.direction == "bearish"
    assert signal.state == "BEARISH_MACD_DIVERGENCE"
    assert "higher high" in signal.message


def test_bearish_macd_divergence_not_detected_when_macd_also_higher():
    """Price higher high + MACD also higher → NOT bearish divergence."""
    pivots = [_pivot(2, 100.0, "H"), _pivot(5, 110.0, "H")]
    df = _make_df(10, [0, 0, 0.3, 0, 0, 0.5, 0, 0, 0, 0])
    signal = detect_bearish_macd_divergence(df, pivots)
    assert signal is None


def test_bearish_no_highs_returns_none():
    pivots = [_pivot(2, 100.0, "L"), _pivot(5, 90.0, "L")]
    df = _make_df(10, list(range(10)))
    signal = detect_bearish_macd_divergence(df, pivots)
    assert signal is None


def test_bearish_index_out_of_range():
    """Pivot index beyond DataFrame length → macd None → returns None."""
    pivots = [_pivot(2, 100.0, "H"), _pivot(50, 110.0, "H")]
    df = _make_df(10, list(range(10)))
    signal = detect_bearish_macd_divergence(df, pivots)
    assert signal is None


# ── MACDDivergenceSignal properties ──────────────────────────────────────────

def test_signal_properties():
    sig = MACDDivergenceSignal(
        direction="bullish",
        first_index=2, second_index=5,
        first_price=100.0, second_price=90.0,
        first_macd=-0.5, second_macd=-0.3,
    )
    assert sig.state == "BULLISH_MACD_DIVERGENCE"
    assert "lower low" in sig.message

    sig2 = MACDDivergenceSignal(
        direction="bearish",
        first_index=2, second_index=5,
        first_price=100.0, second_price=110.0,
        first_macd=0.5, second_macd=0.3,
    )
    assert sig2.state == "BEARISH_MACD_DIVERGENCE"
    assert "higher high" in sig2.message
