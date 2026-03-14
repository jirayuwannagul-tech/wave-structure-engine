"""Tests for analysis/level_state_engine.py"""
from analysis.level_state_engine import detect_level_state


def test_support_break_below():
    assert detect_level_state(99.0, 100.0, "support") == "BREAK"


def test_support_near():
    # above support but within tolerance: 100.1, level=100.0 → diff=0.001 < 0.002, not below → NEAR
    assert detect_level_state(100.1, 100.0, "support", tolerance=0.002) == "NEAR"


def test_support_far_above():
    assert detect_level_state(110.0, 100.0, "support") is None


def test_resistance_break_above():
    assert detect_level_state(101.0, 100.0, "resistance") == "BREAK"


def test_resistance_near():
    # below resistance but within tolerance: 99.9, level=100.0 → not above → NEAR
    assert detect_level_state(99.9, 100.0, "resistance", tolerance=0.002) == "NEAR"


def test_resistance_far_below():
    assert detect_level_state(90.0, 100.0, "resistance") is None


def test_zero_level_price_returns_none():
    assert detect_level_state(100.0, 0.0, "support") is None


def test_unknown_level_type_returns_none():
    assert detect_level_state(100.0, 100.0, "pivot") is None


def test_negative_level_price_returns_none():
    assert detect_level_state(100.0, -1.0, "support") is None
