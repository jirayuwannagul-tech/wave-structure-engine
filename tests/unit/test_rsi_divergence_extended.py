"""Extended tests for analysis/rsi_divergence.py to push coverage to 95%+."""
from __future__ import annotations

import pandas as pd
import pytest

from analysis.pivot_detector import Pivot
from analysis.rsi_divergence import (
    RSIDivergenceSignal,
    _latest_same_type_pair,
    _rsi_at_index,
    detect_bearish_rsi_divergence,
    detect_bullish_rsi_divergence,
)


def _p(idx, price, t):
    return Pivot(index=idx, price=price, type=t, timestamp=f"2026-01-{idx:02d}")


# ---------- RSIDivergenceSignal.message ----------

def test_signal_message_bearish():
    signal = RSIDivergenceSignal(
        direction="bearish",
        first_index=2,
        second_index=4,
        first_price=100.0,
        second_price=105.0,
        first_rsi=60.0,
        second_rsi=55.0,
    )
    assert signal.message == "price made a higher high while RSI made a lower high"
    assert signal.state == "BEARISH_RSI_DIVERGENCE"


def test_signal_message_bullish():
    signal = RSIDivergenceSignal(
        direction="bullish",
        first_index=1,
        second_index=3,
        first_price=100.0,
        second_price=90.0,
        first_rsi=30.0,
        second_rsi=35.0,
    )
    assert signal.message == "price made a lower low while RSI made a higher low"


# ---------- _latest_same_type_pair ----------

def test_latest_same_type_pair_too_few():
    """When fewer than 2 pivots of the same type, return None."""
    pivots = [_p(1, 100.0, "H")]  # only 1 H pivot
    result = _latest_same_type_pair(pivots, "H")
    assert result is None


def test_latest_same_type_pair_returns_last_two():
    pivots = [_p(1, 100.0, "L"), _p(2, 105.0, "H"), _p(3, 90.0, "L")]
    result = _latest_same_type_pair(pivots, "L")
    assert result is not None
    assert result[0].price == 100.0
    assert result[1].price == 90.0


# ---------- _rsi_at_index ----------

def test_rsi_at_index_no_rsi_column():
    df = pd.DataFrame({"close": [100.0, 101.0]})
    assert _rsi_at_index(df, 0) is None


def test_rsi_at_index_out_of_range():
    df = pd.DataFrame({"rsi": [50.0, 60.0]})
    assert _rsi_at_index(df, 5) is None
    assert _rsi_at_index(df, -1) is None


def test_rsi_at_index_nan():
    import numpy as np
    df = pd.DataFrame({"rsi": [float("nan"), 60.0]})
    assert _rsi_at_index(df, 0) is None


def test_rsi_at_index_valid():
    df = pd.DataFrame({"rsi": [50.0, 60.0]})
    assert _rsi_at_index(df, 1) == 60.0


# ---------- detect_bullish_rsi_divergence edge cases ----------

def test_detect_bullish_rsi_divergence_no_lows():
    """No L pivots → None."""
    df = pd.DataFrame({"rsi": [50.0, 60.0]})
    pivots = [_p(1, 100.0, "H")]
    assert detect_bullish_rsi_divergence(df, pivots) is None


def test_detect_bullish_rsi_divergence_rsi_is_none():
    """RSI index out of df range → None."""
    df = pd.DataFrame({"rsi": [30.0, 36.0]})  # only 2 rows
    pivots = [
        _p(10, 100.0, "L"),  # index 10 out of range
        _p(15, 90.0, "L"),   # index 15 out of range
    ]
    assert detect_bullish_rsi_divergence(df, pivots) is None


def test_detect_bullish_rsi_divergence_no_divergence():
    """Both price and RSI go down → no divergence."""
    df = pd.DataFrame({"rsi": [50.0, 42.0, 30.0, 25.0, 20.0]})
    pivots = [_p(2, 100.0, "L"), _p(4, 90.0, "L")]
    # price LL: 90 < 100 ✓, but RSI also LL: 20 < 30 → no divergence
    assert detect_bullish_rsi_divergence(df, pivots) is None


# ---------- detect_bearish_rsi_divergence edge cases ----------

def test_detect_bearish_rsi_divergence_no_highs():
    """No H pivots → None."""
    df = pd.DataFrame({"rsi": [50.0, 60.0]})
    pivots = [_p(1, 100.0, "L")]
    assert detect_bearish_rsi_divergence(df, pivots) is None


def test_detect_bearish_rsi_divergence_rsi_is_none():
    """RSI index out of range → None."""
    df = pd.DataFrame({"rsi": [60.0, 55.0]})
    pivots = [_p(10, 100.0, "H"), _p(15, 105.0, "H")]
    assert detect_bearish_rsi_divergence(df, pivots) is None


def test_detect_bearish_rsi_divergence_no_divergence():
    """Price HH AND RSI HH → no divergence."""
    df = pd.DataFrame({"rsi": [45.0, 58.0, 64.0, 60.0, 70.0]})
    pivots = [_p(2, 100.0, "H"), _p(4, 105.0, "H")]
    # price HH: 105 > 100 ✓, RSI also HH: 70 > 64 → no divergence
    assert detect_bearish_rsi_divergence(df, pivots) is None
