"""Extended tests for analysis/multi_count_engine.py to push coverage to 80%+."""
from __future__ import annotations

import pandas as pd
import pytest

from analysis.multi_count_engine import (
    _clamp,
    _indicator_adjustment,
    _indicator_adjustment_with_context,
    _prepare_indicator_df,
    generate_labeled_wave_counts,
    generate_wave_counts,
)
from analysis.pivot_detector import Pivot
from analysis.rule_validator import RuleValidationResult
from analysis.swing_builder import SwingPoint


# ---------- helpers ----------

def _pivot(i, price, t):
    return Pivot(index=i, price=price, type=t, timestamp=f"2026-01-{i:02d}")


def _swing(i, price, t):
    return SwingPoint(index=i, price=price, type=t, timestamp=f"2026-01-{i:02d}")


def _make_df(n=50, with_volume=True):
    data = {
        "close": list(range(100, 100 + n)),
        "high": list(range(101, 101 + n)),
        "low": list(range(99, 99 + n)),
    }
    if with_volume:
        data["volume"] = [1000.0] * n
    return pd.DataFrame(data)


def _make_df_with_indicators(n=50):
    df = _make_df(n)
    df["ema50"] = df["close"] * 0.98
    df["rsi"] = [55.0] * (n - 2) + [30.0, 38.0]
    df["atr"] = [2.0] * n
    df["macd"] = [0.1] * n
    df["macd_signal"] = [0.05] * n
    df["macd_hist"] = [0.0] * (n - 3) + [-0.1, 0.0, 0.1]
    df["volume_ma20"] = [900.0] * n
    df["ema200"] = df["close"] * 0.90
    return df


# ---------- _clamp ----------

def test_clamp_within():
    assert _clamp(0.5) == 0.5


def test_clamp_low():
    assert _clamp(-1.0) == 0.0


def test_clamp_high():
    assert _clamp(2.0) == 1.0


# ---------- _prepare_indicator_df ----------

def test_prepare_indicator_df_none():
    assert _prepare_indicator_df(None) is None


def test_prepare_indicator_df_empty():
    assert _prepare_indicator_df(pd.DataFrame()) is None


def test_prepare_indicator_df_adds_missing_indicators():
    df = _make_df(60)
    result = _prepare_indicator_df(df)
    assert result is not None
    assert "ema50" in result.columns
    assert "rsi" in result.columns
    assert "atr" in result.columns
    assert "macd" in result.columns
    assert "ema200" in result.columns


def test_prepare_indicator_df_skips_existing_columns():
    df = _make_df(30)
    df["ema50"] = 99.0
    result = _prepare_indicator_df(df)
    # Should keep existing value, not recalculate
    assert result["ema50"].iloc[0] == 99.0


def test_prepare_indicator_df_no_volume_skips_volume_ma():
    df = _make_df(30, with_volume=False)
    result = _prepare_indicator_df(df)
    assert result is not None
    assert "volume_ma20" not in result.columns


def test_prepare_indicator_df_adds_volume_ma_when_volume_present():
    df = _make_df(30, with_volume=True)
    result = _prepare_indicator_df(df)
    assert "volume_ma20" in result.columns


# ---------- _indicator_adjustment ----------

def test_indicator_adjustment_none_df():
    assert _indicator_adjustment("bullish", None) == 0.0


def test_indicator_adjustment_bearish_no_df():
    assert _indicator_adjustment("bearish", None) == 0.0


def test_indicator_adjustment_bullish_returns_float():
    df = _make_df_with_indicators(50)
    adj = _indicator_adjustment("bullish", df)
    assert isinstance(adj, float)


def test_indicator_adjustment_bearish_returns_float():
    df = _make_df_with_indicators(50)
    adj = _indicator_adjustment("bearish", df)
    assert isinstance(adj, float)


def test_indicator_adjustment_empty_direction():
    df = _make_df_with_indicators(50)
    adj, ctx = _indicator_adjustment_with_context("", df, [])
    assert adj == 0.0
    assert ctx is not None


# ---------- _indicator_adjustment_with_context ----------

def test_indicator_adjustment_with_context_none_df():
    adj, ctx = _indicator_adjustment_with_context("bullish", None, [])
    assert adj == 0.0
    assert ctx is None


def test_indicator_adjustment_with_context_bullish_structure():
    df = _make_df_with_indicators(50)
    adj, ctx = _indicator_adjustment_with_context("bullish", df, [])
    assert ctx is not None
    assert "trend_ok" in ctx
    assert "momentum_ok" in ctx
    assert "atr_ok" in ctx
    assert "indicator_validation" in ctx
    assert "rsi_divergence" in ctx
    assert "macd_divergence" in ctx


def test_indicator_adjustment_with_context_bearish_structure():
    df = _make_df_with_indicators(50)
    df["close"] = list(range(150, 150 - 50, -1))
    adj, ctx = _indicator_adjustment_with_context("bearish", df, [])
    assert ctx is not None
    assert "trend_ok" in ctx
    assert "momentum_ok" in ctx
    assert "long_term_trend_ok" in ctx


def test_indicator_adjustment_with_volume_column():
    df = _make_df_with_indicators(50)
    # Make volume spike: last volume >> average
    df["volume"] = [1000.0] * 49 + [9000.0]
    df["volume_ma20"] = [1000.0] * 50
    adj, ctx = _indicator_adjustment_with_context("bullish", df, [])
    assert ctx["volume_spike"] is True


def test_indicator_adjustment_no_volume_column():
    df = _make_df_with_indicators(50)
    df = df.drop(columns=["volume"], errors="ignore")
    adj, ctx = _indicator_adjustment_with_context("bullish", df, [])
    assert ctx["volume_spike"] is False


def test_indicator_adjustment_macd_hist_turning_bullish():
    df = _make_df_with_indicators(50)
    # Make macd_hist turn from negative to positive
    df["macd_hist"] = [-0.5] * 48 + [-0.1, 0.1]
    adj, ctx = _indicator_adjustment_with_context("bullish", df, [])
    assert ctx is not None


# ---------- generate_wave_counts with mocked patterns ----------

def _valid_rule_result(pattern_type):
    return RuleValidationResult(
        pattern_type=pattern_type.lower(),
        is_valid=True,
        message="valid",
    )


class _FakeFlat:
    pattern_type = "flat"
    direction = "bullish"
    ab_length = 10.0
    bc_length = 9.0
    b_vs_a_ratio = 0.95
    c_vs_a_ratio = 0.85

    class _P:
        price = 100.0
    a = _P()
    b = _P()
    c = _P()


class _FakeExpandedFlat:
    pattern_type = "expanded_flat"
    direction = "bearish"
    ab_length = 10.0
    bc_length = 12.0
    b_vs_a_ratio = 1.1
    c_vs_a_ratio = 1.05

    class _P:
        price = 90.0
    a = _P()
    b = _P()
    c = _P()


class _FakeRunningFlat:
    pattern_type = "running_flat"
    direction = "bullish"
    ab_length = 10.0
    bc_length = 8.0
    b_vs_a_ratio = 0.5
    c_vs_a_ratio = 0.7

    class _P:
        price = 105.0
    a = _P()
    b = _P()
    c = _P()


class _FakeTriangle:
    pattern_type = "contracting_triangle"
    direction = "neutral"
    upper_slope = -1.0
    lower_slope = 1.0

    class _P:
        def __init__(self, p):
            self.price = p
    points = [_P(120), _P(100), _P(115), _P(105), _P(110)]


class _FakeExpandingTriangle:
    pattern_type = "expanding_triangle"
    direction = "neutral"
    upper_slope = 1.0
    lower_slope = -1.0

    class _P:
        def __init__(self, p):
            self.price = p
    points = [_P(110), _P(100), _P(115), _P(95), _P(120)]


class _FakeBarrierTriangle:
    pattern_type = "ascending_barrier"
    direction = "neutral"
    upper_slope = 0.0
    lower_slope = 1.0

    class _P:
        def __init__(self, p):
            self.price = p
    points = [_P(120), _P(100), _P(120), _P(105), _P(120)]


class _FakeWXY:
    direction = "bearish"
    wx_length = 20.0
    xy_length = 15.0
    y_vs_w_ratio = 0.75

    class _P:
        price = 95.0
    w = _P()
    x = _P()
    y = _P()


class _FakeEndingDiagonal:
    pattern_type = "ending_diagonal"
    direction = "bullish"
    overlap_exists = True
    is_contracting = True
    w3_vs_w1_ratio = 0.8
    w4_vs_w2_ratio = 0.8

    class _P:
        price = 100.0
    p1 = _P()
    p2 = _P()
    p3 = _P()
    p4 = _P()
    p5 = _P()


class _FakeLeadingDiagonal:
    pattern_type = "leading_diagonal"
    direction = "bearish"
    overlap_exists = True
    is_contracting = True
    w3_vs_w1_ratio = 0.8
    w4_vs_w2_ratio = 0.8

    class _P:
        price = 80.0
    p1 = _P()
    p2 = _P()
    p3 = _P()
    p4 = _P()
    p5 = _P()


def test_generate_wave_counts_flat_pattern(monkeypatch):
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_abc", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_impulse", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_flat", lambda s: _FakeFlat())
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanded_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_running_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_contracting_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanding_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_barrier_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_wxy", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_ending_diagonal", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_leading_diagonal", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.validate_pattern_rules", lambda t, p: _valid_rule_result(t))

    counts = generate_wave_counts([])
    assert any(c["type"] == "FLAT" for c in counts)


def test_generate_wave_counts_expanded_flat_pattern(monkeypatch):
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_abc", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_impulse", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanded_flat", lambda s: _FakeExpandedFlat())
    monkeypatch.setattr("analysis.multi_count_engine.detect_running_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_contracting_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanding_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_barrier_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_wxy", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_ending_diagonal", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_leading_diagonal", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.validate_pattern_rules", lambda t, p: _valid_rule_result(t))

    counts = generate_wave_counts([])
    assert any(c["type"] == "EXPANDED_FLAT" for c in counts)


def test_generate_wave_counts_running_flat_pattern(monkeypatch):
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_abc", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_impulse", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanded_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_running_flat", lambda s: _FakeRunningFlat())
    monkeypatch.setattr("analysis.multi_count_engine.detect_contracting_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanding_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_barrier_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_wxy", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_ending_diagonal", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_leading_diagonal", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.validate_pattern_rules", lambda t, p: _valid_rule_result(t))

    counts = generate_wave_counts([])
    assert any(c["type"] == "RUNNING_FLAT" for c in counts)


def test_generate_wave_counts_contracting_triangle(monkeypatch):
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_abc", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_impulse", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanded_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_running_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_contracting_triangle", lambda s: _FakeTriangle())
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanding_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_barrier_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_wxy", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_ending_diagonal", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_leading_diagonal", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.validate_pattern_rules", lambda t, p: _valid_rule_result(t))

    counts = generate_wave_counts([])
    assert any(c["type"] == "CONTRACTING_TRIANGLE" for c in counts)


def test_generate_wave_counts_expanding_triangle(monkeypatch):
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_abc", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_impulse", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanded_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_running_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_contracting_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanding_triangle", lambda s: _FakeExpandingTriangle())
    monkeypatch.setattr("analysis.multi_count_engine.detect_barrier_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_wxy", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_ending_diagonal", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_leading_diagonal", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.validate_pattern_rules", lambda t, p: _valid_rule_result(t))

    counts = generate_wave_counts([])
    assert any(c["type"] == "EXPANDING_TRIANGLE" for c in counts)


def test_generate_wave_counts_barrier_triangle(monkeypatch):
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_abc", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_impulse", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanded_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_running_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_contracting_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanding_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_barrier_triangle", lambda s: _FakeBarrierTriangle())
    monkeypatch.setattr("analysis.multi_count_engine.detect_wxy", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_ending_diagonal", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_leading_diagonal", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.validate_pattern_rules", lambda t, p: _valid_rule_result(t))

    counts = generate_wave_counts([])
    assert any(c["type"] == "ASCENDING_BARRIER" for c in counts)


def test_generate_wave_counts_wxy_pattern(monkeypatch):
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_abc", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_impulse", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanded_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_running_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_contracting_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanding_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_barrier_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_wxy", lambda s: _FakeWXY())
    monkeypatch.setattr("analysis.multi_count_engine.detect_ending_diagonal", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_leading_diagonal", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.validate_pattern_rules", lambda t, p: _valid_rule_result(t))

    counts = generate_wave_counts([])
    assert any(c["type"] == "WXY" for c in counts)


def test_generate_wave_counts_ending_diagonal(monkeypatch):
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_abc", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_impulse", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanded_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_running_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_contracting_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanding_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_barrier_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_wxy", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_ending_diagonal", lambda p: _FakeEndingDiagonal())
    monkeypatch.setattr("analysis.multi_count_engine.detect_leading_diagonal", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.validate_pattern_rules", lambda t, p: _valid_rule_result(t))

    counts = generate_wave_counts([])
    assert any(c["type"] == "ENDING_DIAGONAL" for c in counts)


def test_generate_wave_counts_leading_diagonal(monkeypatch):
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_abc", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_impulse", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanded_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_running_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_contracting_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanding_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_barrier_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_wxy", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_ending_diagonal", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_leading_diagonal", lambda p: _FakeLeadingDiagonal())
    monkeypatch.setattr("analysis.multi_count_engine.validate_pattern_rules", lambda t, p: _valid_rule_result(t))

    counts = generate_wave_counts([])
    assert any(c["type"] == "LEADING_DIAGONAL" for c in counts)


def test_generate_wave_counts_invalid_rule_skips_pattern(monkeypatch):
    """Patterns with invalid rule results should not be added to counts."""
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_abc", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_impulse", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_flat", lambda s: _FakeFlat())
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanded_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_running_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_contracting_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanding_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_barrier_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_wxy", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_ending_diagonal", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_leading_diagonal", lambda p: None)
    # Return invalid rule result for all
    monkeypatch.setattr(
        "analysis.multi_count_engine.validate_pattern_rules",
        lambda t, p: RuleValidationResult(pattern_type=t.lower(), is_valid=False, message="invalid"),
    )

    counts = generate_wave_counts([])
    assert not any(c["type"] == "FLAT" for c in counts)


def test_generate_wave_counts_with_df_indicator_context(monkeypatch):
    """When df is provided, indicator_context should be attached to patterns."""
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_abc", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_impulse", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_flat", lambda s: _FakeFlat())
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanded_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_running_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_contracting_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanding_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_barrier_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_wxy", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_ending_diagonal", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_leading_diagonal", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.validate_pattern_rules", lambda t, p: _valid_rule_result(t))

    df = _make_df_with_indicators(50)
    counts = generate_wave_counts([], df=df)
    flat_counts = [c for c in counts if c["type"] == "FLAT"]
    assert flat_counts
    assert "indicator_context" in flat_counts[0]


def test_generate_labeled_wave_counts_returns_list(monkeypatch):
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_abc", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_impulse", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanded_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_running_flat", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_contracting_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_expanding_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_barrier_triangle", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_wxy", lambda s: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_ending_diagonal", lambda p: None)
    monkeypatch.setattr("analysis.multi_count_engine.detect_leading_diagonal", lambda p: None)

    result = generate_labeled_wave_counts([], timeframe="1D")
    assert isinstance(result, list)
