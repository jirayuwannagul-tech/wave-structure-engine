"""Targeted tests to push analysis modules from 85-90% to 95% coverage."""
from __future__ import annotations

import runpy
from unittest.mock import patch

import pandas as pd
import pytest

from analysis.indicator_filter import (
    check_atr_expansion,
    check_bearish_momentum,
    check_bearish_trend_context,
    check_bullish_momentum,
    check_bullish_trend_context,
    check_long_term_bearish_trend,
    check_long_term_bullish_trend,
)
from analysis.trend_classifier import (
    TrendClassification,
    _fallback_from_closes,
    classify_market_trend,
    dow_theory_alignment_adjustment,
)
from analysis.wave_position import WavePosition, _build_pattern_position, detect_wave_position


# ============================================================
# indicator_filter.py — cover empty df and missing column paths
# ============================================================

def _empty_df():
    return pd.DataFrame()


def _df_no_ema50():
    return pd.DataFrame({"close": [100.0]})


def _df_no_close():
    return pd.DataFrame({"ema50": [99.0]})


def test_check_bullish_trend_context_no_close():
    assert check_bullish_trend_context(_df_no_close()) is False


def test_check_bullish_trend_context_empty_df():
    df = pd.DataFrame({"close": [], "ema50": []})
    assert check_bullish_trend_context(df) is False


def test_check_bearish_trend_context_no_close():
    assert check_bearish_trend_context(_df_no_close()) is False


def test_check_bearish_trend_context_empty_df():
    df = pd.DataFrame({"close": [], "ema50": []})
    assert check_bearish_trend_context(df) is False


def test_check_long_term_bearish_empty_df():
    df = pd.DataFrame({"close": [], "ema200": []})
    assert check_long_term_bearish_trend(df) is False


def test_check_bullish_momentum_empty_df():
    df = pd.DataFrame({"rsi": []})
    assert check_bullish_momentum(df) is False


def test_check_bearish_momentum_empty_df():
    df = pd.DataFrame({"rsi": []})
    assert check_bearish_momentum(df) is False


def test_check_atr_expansion_too_few_rows():
    df = pd.DataFrame({"atr": [1.0, 2.0, 3.0]})  # only 3 rows, lookback=20
    assert check_atr_expansion(df) is False


def test_check_atr_expansion_zero_avg():
    df = pd.DataFrame({"atr": [0.0] * 21})
    assert check_atr_expansion(df) is False


# ============================================================
# trend_classifier.py — cover missing branches
# ============================================================

def test_fallback_from_closes_none_df():
    result = _fallback_from_closes(None)
    assert result.state == "SIDEWAY"
    assert result.source == "fallback"


def test_fallback_from_closes_short_df():
    df = pd.DataFrame({"close": [100.0] * 10})
    result = _fallback_from_closes(df)
    assert result.state == "SIDEWAY"


def test_fallback_from_closes_no_close_column():
    df = pd.DataFrame({"high": [100.0] * 25})
    result = _fallback_from_closes(df)
    assert result.state == "SIDEWAY"


def test_fallback_from_closes_downtrend():
    closes = list(range(100, 80, -1))  # falling prices
    df = pd.DataFrame({"close": closes})
    result = _fallback_from_closes(df)
    assert result.state == "DOWNTREND"


def test_fallback_from_closes_flat():
    df = pd.DataFrame({"close": [100.0] * 20})
    result = _fallback_from_closes(df)
    assert result.state == "SIDEWAY"


def test_dow_theory_alignment_adjustment_uptrend_bullish():
    trend = TrendClassification(
        state="UPTREND", last_high=None, previous_high=None,
        last_low=None, previous_low=None,
        swing_structure="HH_HL", source="pivot", confidence=0.8,
        message="uptrend",
    )
    adj = dow_theory_alignment_adjustment("bullish", trend)
    assert adj == 0.003


def test_dow_theory_alignment_adjustment_uptrend_bearish():
    trend = TrendClassification(
        state="UPTREND", last_high=None, previous_high=None,
        last_low=None, previous_low=None,
        swing_structure="HH_HL", source="pivot", confidence=0.8,
        message="uptrend",
    )
    adj = dow_theory_alignment_adjustment("bearish", trend)
    assert adj == 0.0


def test_dow_theory_alignment_adjustment_downtrend_bearish():
    trend = TrendClassification(
        state="DOWNTREND", last_high=None, previous_high=None,
        last_low=None, previous_low=None,
        swing_structure="LH_LL", source="pivot", confidence=0.8,
        message="downtrend",
    )
    adj = dow_theory_alignment_adjustment("bearish", trend)
    assert adj == 0.003


def test_dow_theory_alignment_adjustment_unknown_direction():
    trend = TrendClassification(
        state="UPTREND", last_high=None, previous_high=None,
        last_low=None, previous_low=None,
        swing_structure="HH_HL", source="pivot", confidence=0.8,
        message="uptrend",
    )
    adj = dow_theory_alignment_adjustment("neutral", trend)
    assert adj == 0.0


def test_dow_theory_alignment_adjustment_broken_up():
    trend = TrendClassification(
        state="BROKEN_UP", last_high=None, previous_high=None,
        last_low=None, previous_low=None,
        swing_structure="HH_HL", source="pivot", confidence=0.7,
        message="",
    )
    adj = dow_theory_alignment_adjustment("bullish", trend)
    assert adj == 0.003


def test_dow_theory_alignment_adjustment_broken_down():
    trend = TrendClassification(
        state="BROKEN_DOWN", last_high=None, previous_high=None,
        last_low=None, previous_low=None,
        swing_structure="LH_LL", source="pivot", confidence=0.7,
        message="",
    )
    adj = dow_theory_alignment_adjustment("bearish", trend)
    assert adj == 0.003


# ============================================================
# wave_position.py — _build_pattern_position coverage
# ============================================================

class _FakePattern:
    direction = "bullish"


def test_build_pattern_position_abc():
    """ABC_CORRECTION pattern uses _build_abc_position path."""
    from analysis.pivot_detector import Pivot
    from analysis.wave_detector import ABCPattern

    class FakeABC:
        direction = "bullish"

        class P:
            price = 100.0
        a = P()
        b = P()
        c = P()
        ab_length = 10.0
        bc_length = 8.0
        bc_vs_ab_ratio = 0.8

    pos = _build_pattern_position("ABC_CORRECTION", FakeABC())
    assert pos.structure == "ABC_CORRECTION"
    assert pos.bias == "BULLISH"


def test_build_pattern_position_impulse():
    """IMPULSE pattern uses _build_impulse_position path."""
    from analysis.pivot_detector import Pivot
    from analysis.wave_detector import ImpulsePattern

    p = lambda i, price, t: Pivot(index=i, price=price, type=t, timestamp=f"2026-01-{i:02d}")
    impulse = ImpulsePattern(
        p1=p(1, 100, "L"), p2=p(2, 90, "H"), p3=p(3, 130, "L"),
        p4=p(4, 115, "H"), p5=p(5, 125, "L"), p6=p(6, 155, "H"),
        direction="bullish",
        wave1_length=30, wave2_length=10, wave3_length=40,
        wave4_length=15, wave5_length=30,
        wave2_retrace_ratio=0.33, wave4_retrace_ratio=0.38,
        wave3_vs_wave1_ratio=1.3, wave5_vs_wave1_ratio=1.0,
        rule_wave2_not_beyond_wave1_origin=True,
        rule_wave3_not_shortest=True,
        rule_wave4_no_overlap_wave1=True,
        is_valid=True,
    )
    pos = _build_pattern_position("IMPULSE", impulse)
    assert pos.structure == "IMPULSE"
    assert pos.bias == "BULLISH"


def test_build_pattern_position_flat():
    pos = _build_pattern_position("FLAT", _FakePattern())
    assert pos.structure == "FLAT"
    assert pos.position == "CORRECTION_COMPLETE"


def test_build_pattern_position_wxy():
    pos = _build_pattern_position("WXY", _FakePattern())
    assert pos.structure == "WXY"


def test_build_pattern_position_contracting_triangle():
    pos = _build_pattern_position("CONTRACTING_TRIANGLE", _FakePattern())
    assert pos.position == "CONSOLIDATION_END"


def test_build_pattern_position_ascending_barrier_triangle():
    pos = _build_pattern_position("ASCENDING_BARRIER_TRIANGLE", _FakePattern())
    assert pos.position == "CONSOLIDATION_END"


# ============================================================
# rule_validator.py — __main__ block + misc
# ============================================================

def _make_dummy_df_for_validator(n=20):
    return pd.DataFrame(
        {
            "open_time": pd.date_range("2026-01-01", periods=n, freq="D", tz="UTC"),
            "high": [100 + i % 5 for i in range(n)],
            "low": [95 + i % 5 for i in range(n)],
            "close": [98 + i % 5 for i in range(n)],
        }
    )


def test_rule_validator_main_block():
    dummy_df = _make_dummy_df_for_validator()
    with (
        patch("pandas.read_csv", return_value=dummy_df),
        patch("analysis.wave_detector.detect_latest_abc", return_value=None),
        patch("analysis.wave_detector.detect_latest_impulse", return_value=None),
    ):
        runpy.run_module("analysis.rule_validator", run_name="__main__")


def test_wave_position_main_block():
    dummy_df = _make_dummy_df_for_validator()
    with (
        patch("pandas.read_csv", return_value=dummy_df),
        patch("analysis.wave_detector.detect_latest_abc", return_value=None),
        patch("analysis.wave_detector.detect_latest_impulse", return_value=None),
    ):
        runpy.run_module("analysis.wave_position", run_name="__main__")


def test_trend_classifier_classify_with_empty_pivots():
    """classify_market_trend with no pivots falls back to close-based."""
    df = pd.DataFrame({"close": list(range(100, 120))})
    result = classify_market_trend([], df)
    assert result is not None
    assert result.state in {"UPTREND", "SIDEWAY", "DOWNTREND"}
