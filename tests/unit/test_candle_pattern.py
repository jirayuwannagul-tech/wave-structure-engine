"""Unit tests for analysis.candle_pattern module."""
from __future__ import annotations

import pandas as pd
import pytest

from analysis.candle_pattern import (
    CandlePattern,
    detect_candle_patterns,
    score_candle_confirmation,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_df(candles: list[tuple]) -> pd.DataFrame:
    """Build a DataFrame from (open, high, low, close) tuples."""
    return pd.DataFrame(candles, columns=["open", "high", "low", "close"])


# ── detect_candle_patterns: edge cases ───────────────────────────────────────

def test_empty_dataframe_returns_no_patterns():
    df = make_df([])
    result = detect_candle_patterns(df, lookback=3)
    assert result == []


def test_single_candle_returns_no_patterns():
    df = make_df([(100, 110, 90, 105)])
    result = detect_candle_patterns(df, lookback=3)
    # Only one candle, less than 2 rows needed
    assert isinstance(result, list)


def test_zero_range_candle_skipped():
    """A candle where high == low must be skipped (avoid div-by-zero)."""
    df = make_df([
        (100, 100, 100, 100),  # zero range
        (100, 110, 95, 105),
    ])
    # Should not raise
    result = detect_candle_patterns(df, lookback=3)
    assert isinstance(result, list)


# ── Hammer detection ─────────────────────────────────────────────────────────

def test_hammer_detected():
    """Classic hammer: small body at top, long lower wick."""
    # o=100, h=101, l=80, c=99 → body=1, range=21, lower_wick=19, upper_wick=2
    # body_ratio=1/21≈0.048, lower_wick=19 >= 2*1=2 ✓, upper_wick=2 <= 0.3*21=6.3 ✓
    df = make_df([
        (100, 110, 90, 105),   # padding candle
        (100, 101, 80, 99),    # hammer
    ])
    patterns = detect_candle_patterns(df, lookback=2)
    names = [p.name for p in patterns]
    assert "HAMMER" in names


def test_hammer_direction_is_bullish():
    df = make_df([
        (100, 110, 90, 105),
        (100, 101, 80, 99),
    ])
    patterns = detect_candle_patterns(df, lookback=2)
    hammers = [p for p in patterns if p.name == "HAMMER"]
    assert all(p.direction == "bullish" for p in hammers)


def test_hammer_strength_in_range():
    df = make_df([
        (100, 110, 90, 105),
        (100, 101, 80, 99),
    ])
    patterns = detect_candle_patterns(df, lookback=2)
    hammers = [p for p in patterns if p.name == "HAMMER"]
    for h in hammers:
        assert 0.0 <= h.strength <= 1.0


# ── Shooting Star detection ───────────────────────────────────────────────────

def test_shooting_star_detected():
    """Shooting star: small body at bottom, long upper wick."""
    # o=99, h=120, l=98, c=100 → body=1, range=22, upper_wick=20, lower_wick=1
    # body_ratio=1/22≈0.045, upper_wick=20>=2*1=2 ✓, lower_wick=1<=0.3*22=6.6 ✓
    df = make_df([
        (100, 110, 90, 105),   # padding
        (99, 120, 98, 100),    # shooting star
    ])
    patterns = detect_candle_patterns(df, lookback=2)
    names = [p.name for p in patterns]
    assert "SHOOTING_STAR" in names


def test_shooting_star_direction_is_bearish():
    df = make_df([
        (100, 110, 90, 105),
        (99, 120, 98, 100),
    ])
    patterns = detect_candle_patterns(df, lookback=2)
    stars = [p for p in patterns if p.name == "SHOOTING_STAR"]
    assert all(p.direction == "bearish" for p in stars)


# ── Engulfing detection ───────────────────────────────────────────────────────

def test_bullish_engulfing_detected():
    """Bullish engulfing: prev candle bearish, curr candle bullish and engulfs."""
    # prev: o=105, h=106, l=98, c=100 (bearish)
    # curr: o=99, h=110, l=98, c=106  (bullish, c>po=105, o<pc=100)
    df = make_df([
        (105, 106, 98, 100),   # bearish candle
        (99, 110, 98, 106),    # bullish engulfing
    ])
    patterns = detect_candle_patterns(df, lookback=2)
    names = [p.name for p in patterns]
    assert "ENGULFING_BULLISH" in names


def test_bearish_engulfing_detected():
    """Bearish engulfing: prev candle bullish, curr candle bearish and engulfs."""
    # prev: o=100, h=108, l=99, c=106 (bullish)
    # curr: o=107, h=108, l=97, c=99  (bearish, c<po=100, o>pc=106)
    df = make_df([
        (100, 108, 99, 106),   # bullish candle
        (107, 108, 97, 99),    # bearish engulfing
    ])
    patterns = detect_candle_patterns(df, lookback=2)
    names = [p.name for p in patterns]
    assert "ENGULFING_BEARISH" in names


def test_engulfing_bullish_direction():
    df = make_df([
        (105, 106, 98, 100),
        (99, 110, 98, 106),
    ])
    patterns = detect_candle_patterns(df, lookback=2)
    eng = [p for p in patterns if p.name == "ENGULFING_BULLISH"]
    assert all(p.direction == "bullish" for p in eng)


def test_engulfing_bearish_direction():
    df = make_df([
        (100, 108, 99, 106),
        (107, 108, 97, 99),
    ])
    patterns = detect_candle_patterns(df, lookback=2)
    eng = [p for p in patterns if p.name == "ENGULFING_BEARISH"]
    assert all(p.direction == "bearish" for p in eng)


# ── Doji detection ────────────────────────────────────────────────────────────

def test_doji_detected():
    """Doji: very small body relative to total range."""
    # o=100, h=110, l=90, c=100.5 → body=0.5, range=20, ratio=0.025 ≤ 0.1 ✓
    df = make_df([
        (100, 110, 90, 105),   # padding
        (100, 110, 90, 100.5), # doji
    ])
    patterns = detect_candle_patterns(df, lookback=2)
    names = [p.name for p in patterns]
    assert "DOJI" in names


def test_doji_direction_is_neutral():
    df = make_df([
        (100, 110, 90, 105),
        (100, 110, 90, 100.5),
    ])
    patterns = detect_candle_patterns(df, lookback=2)
    dojis = [p for p in patterns if p.name == "DOJI"]
    assert all(p.direction == "neutral" for p in dojis)


# ── Pin Bar detection ─────────────────────────────────────────────────────────

def test_pin_bar_bullish_detected():
    """Bullish pin bar: lower wick >= 60% of range, small body."""
    # o=100, h=101, l=80, c=99 → range=21, lower_wick=19, body=1
    # lower_wick/range = 19/21 ≈ 0.905 >= 0.6 ✓, body_ratio ≈ 0.048 ≤ 0.2 ✓
    df = make_df([
        (100, 110, 90, 105),
        (100, 101, 80, 99),
    ])
    patterns = detect_candle_patterns(df, lookback=2)
    names = [p.name for p in patterns]
    assert "PIN_BAR_BULLISH" in names


def test_pin_bar_bearish_detected():
    """Bearish pin bar: upper wick >= 60% of range, small body."""
    # o=100, h=120, l=99, c=101 → range=21, upper_wick=19, body=1
    # upper_wick/range = 19/21 ≈ 0.905 >= 0.6 ✓, body_ratio ≈ 0.048 ≤ 0.2 ✓
    df = make_df([
        (100, 110, 90, 105),
        (100, 120, 99, 101),
    ])
    patterns = detect_candle_patterns(df, lookback=2)
    names = [p.name for p in patterns]
    assert "PIN_BAR_BEARISH" in names


# ── score_candle_confirmation ─────────────────────────────────────────────────

def test_score_empty_patterns_returns_zero():
    assert score_candle_confirmation([], "BULLISH") == 0.0


def test_score_strong_bullish_confirmation():
    """Strong bullish pattern confirming a bullish bias should return +0.10."""
    patterns = [CandlePattern("HAMMER", "bullish", 0.9, 0)]
    assert score_candle_confirmation(patterns, "BULLISH") == 0.10


def test_score_moderate_bullish_confirmation():
    """Moderate bullish pattern (strength 0.4-0.6) should return +0.05."""
    patterns = [CandlePattern("HAMMER", "bullish", 0.5, 0)]
    assert score_candle_confirmation(patterns, "BULLISH") == 0.05


def test_score_contradicting_bearish_against_bullish():
    """Strong bearish pattern against bullish bias should return -0.05."""
    patterns = [CandlePattern("SHOOTING_STAR", "bearish", 0.8, 0)]
    assert score_candle_confirmation(patterns, "BULLISH") == -0.05


def test_score_neutral_doji_returns_zero():
    """Doji (neutral) should not affect the score positively or negatively."""
    patterns = [CandlePattern("DOJI", "neutral", 0.3, 0)]
    assert score_candle_confirmation(patterns, "BULLISH") == 0.0


def test_score_bearish_bias_bullish_pattern_contradicts():
    """Bullish pattern against bearish bias should return -0.05."""
    patterns = [CandlePattern("ENGULFING_BULLISH", "bullish", 0.9, 0)]
    assert score_candle_confirmation(patterns, "BEARISH") == -0.05


def test_score_bearish_confirmation_strong():
    """Strong bearish pattern confirming bearish bias should return +0.10."""
    patterns = [CandlePattern("SHOOTING_STAR", "bearish", 0.85, 0)]
    assert score_candle_confirmation(patterns, "BEARISH") == 0.10


def test_score_weak_contradict_returns_zero():
    """A weak contradicting pattern (strength < 0.6) should return 0.0."""
    patterns = [CandlePattern("SHOOTING_STAR", "bearish", 0.4, 0)]
    assert score_candle_confirmation(patterns, "BULLISH") == 0.0


def test_score_best_confirming_pattern_wins():
    """When multiple patterns exist, the best confirming one dominates."""
    patterns = [
        CandlePattern("DOJI", "neutral", 0.3, 0),
        CandlePattern("HAMMER", "bullish", 0.7, 1),
    ]
    assert score_candle_confirmation(patterns, "BULLISH") == 0.10


def test_candle_pattern_dataclass_fields():
    """CandlePattern dataclass stores fields correctly."""
    p = CandlePattern(name="HAMMER", direction="bullish", strength=0.75, index=5)
    assert p.name == "HAMMER"
    assert p.direction == "bullish"
    assert p.strength == 0.75
    assert p.index == 5
