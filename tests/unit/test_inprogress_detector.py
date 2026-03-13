"""Tests for analysis/inprogress_detector.py"""

import pytest

from analysis.inprogress_detector import (
    InProgressWave,
    detect_inprogress_wave,
    _try_partial_bullish_impulse,
    _try_partial_bearish_impulse,
)
from analysis.pivot_detector import Pivot


def make_pivot(index: int, price: float, ptype: str) -> Pivot:
    return Pivot(index=index, price=price, type=ptype, timestamp=f"2026-01-{index:02d}")


# ---------------------------------------------------------------------------
# Bullish impulse: building wave 2 (2 pivots)
# ---------------------------------------------------------------------------


def test_building_wave_2_bullish():
    pivots = [
        make_pivot(1, 100.0, "L"),  # Wave 1 start
        make_pivot(2, 120.0, "H"),  # Wave 1 end
    ]
    result = detect_inprogress_wave(pivots)
    assert result is not None
    assert result.wave_number == "2"
    assert result.direction == "bullish"
    assert result.structure == "IMPULSE"
    assert result.completed_waves == 1
    # Fib targets should be retracements of wave 1
    assert "0.618" in result.fib_targets
    assert result.fib_targets["0.618"] < 120.0  # below wave 1 end


# ---------------------------------------------------------------------------
# Bullish impulse: building wave 3 (3 pivots)
# ---------------------------------------------------------------------------


def test_building_wave_3_bullish():
    pivots = [
        make_pivot(1, 100.0, "L"),  # Wave 1 start
        make_pivot(2, 120.0, "H"),  # Wave 1 end
        make_pivot(3, 110.0, "L"),  # Wave 2 end (above wave 1 start ✓)
    ]
    result = detect_inprogress_wave(pivots)
    assert result is not None
    assert result.wave_number == "3"
    assert result.direction == "bullish"
    assert result.completed_waves == 2
    # Fib targets: extensions from wave 2 end
    assert "1.618" in result.fib_targets
    assert result.fib_targets["1.618"] > 120.0  # above wave 1 high


# ---------------------------------------------------------------------------
# Bullish impulse: building wave 4 (4 pivots)
# ---------------------------------------------------------------------------


def test_building_wave_4_bullish():
    pivots = [
        make_pivot(1, 100.0, "L"),  # Wave 1 start
        make_pivot(2, 120.0, "H"),  # Wave 1 end
        make_pivot(3, 108.0, "L"),  # Wave 2 end (above 100 ✓)
        make_pivot(4, 150.0, "H"),  # Wave 3 end (w3=42 > w1=20 ✓)
    ]
    result = detect_inprogress_wave(pivots)
    assert result is not None
    assert result.wave_number == "4"
    assert result.direction == "bullish"
    assert result.completed_waves == 3
    # Fib targets: retracements of wave 3
    assert "0.382" in result.fib_targets
    target_382 = 150.0 - (150.0 - 108.0) * 0.382
    assert abs(result.fib_targets["0.382"] - target_382) < 0.01


# ---------------------------------------------------------------------------
# Bullish impulse: building wave 5 (5 pivots)
# ---------------------------------------------------------------------------


def test_building_wave_5_bullish():
    pivots = [
        make_pivot(1, 100.0, "L"),  # Wave 1 start
        make_pivot(2, 120.0, "H"),  # Wave 1 end
        make_pivot(3, 108.0, "L"),  # Wave 2 end
        make_pivot(4, 150.0, "H"),  # Wave 3 end
        make_pivot(5, 135.0, "L"),  # Wave 4 end (above 120 ✓ rule 3)
    ]
    result = detect_inprogress_wave(pivots)
    assert result is not None
    assert result.wave_number == "5"
    assert result.direction == "bullish"
    assert result.completed_waves == 4
    assert "w1_equal" in result.fib_targets
    # Wave 5 = wave 1 size from wave 4 end: 135 + 20 = 155
    assert abs(result.fib_targets["w1_equal"] - 155.0) < 0.01


# ---------------------------------------------------------------------------
# Bearish impulse: building wave 4 (4 pivots)
# ---------------------------------------------------------------------------


def test_building_wave_4_bearish():
    pivots = [
        make_pivot(1, 100.0, "H"),  # Wave 1 start
        make_pivot(2, 80.0,  "L"),  # Wave 1 end
        make_pivot(3, 92.0,  "H"),  # Wave 2 end (below 100 ✓)
        make_pivot(4, 50.0,  "L"),  # Wave 3 end (w3=42 > w1=20 ✓)
    ]
    result = detect_inprogress_wave(pivots)
    assert result is not None
    assert result.wave_number == "4"
    assert result.direction == "bearish"
    assert result.completed_waves == 3
    # Fib targets: retracements (up) of wave 3
    assert "0.382" in result.fib_targets
    # Wave 3 size = 92-50 = 42
    target_382 = 50.0 + 42.0 * 0.382
    assert abs(result.fib_targets["0.382"] - target_382) < 0.01


# ---------------------------------------------------------------------------
# Rule violations → None
# ---------------------------------------------------------------------------


def test_wave2_breaches_wave1_origin_returns_smaller_window():
    """Wave 2 going below Wave 1 start should fail 3-pivot validation."""
    pivots = [
        make_pivot(1, 100.0, "L"),  # Wave 1 start
        make_pivot(2, 120.0, "H"),  # Wave 1 end
        make_pivot(3,  95.0, "L"),  # Wave 2 below wave 1 start → INVALID
    ]
    result = detect_inprogress_wave(pivots)
    # 3-pivot [L,H,L] with rule violation → should fall back to 2-pivot [H,L]
    # or return None (since [L,H] is valid, detect_inprogress_wave returns wave 2)
    if result is not None:
        # If it returns something, it must be the 2-pivot window (building wave 2)
        assert result.wave_number == "2"


def test_wave4_overlap_fails_rule3():
    """Wave 4 end below Wave 1 end violates rule 3."""
    pivots = [
        make_pivot(1, 100.0, "L"),  # Wave 1 start
        make_pivot(2, 120.0, "H"),  # Wave 1 end
        make_pivot(3, 108.0, "L"),  # Wave 2 end
        make_pivot(4, 150.0, "H"),  # Wave 3 end
        make_pivot(5, 115.0, "L"),  # Wave 4 end — BELOW wave 1 end (120) ❌
    ]
    result = detect_inprogress_wave(pivots)
    # 5-pivot fails rule 3 → should fall back to 4-pivot (building wave 4)
    if result is not None:
        assert result.wave_number in ("4", "3", "2")


def test_wave3_shorter_than_wave1_fails():
    """Wave 3 shorter than Wave 1 violates rule 2."""
    pivots = [
        make_pivot(1, 100.0, "L"),
        make_pivot(2, 120.0, "H"),  # w1 = 20
        make_pivot(3, 110.0, "L"),
        make_pivot(4, 125.0, "H"),  # w3 = 15 < 20 → INVALID
    ]
    result = detect_inprogress_wave(pivots)
    # 4-pivot fails rule 2 → should fall back to smaller window
    if result is not None:
        assert result.wave_number in ("3", "2")


# ---------------------------------------------------------------------------
# Insufficient pivots
# ---------------------------------------------------------------------------


def test_single_pivot_returns_none():
    pivots = [make_pivot(1, 100.0, "L")]
    assert detect_inprogress_wave(pivots) is None


def test_empty_pivots_returns_none():
    assert detect_inprogress_wave([]) is None


# ---------------------------------------------------------------------------
# Confidence increases with more validated waves
# ---------------------------------------------------------------------------


def test_confidence_increases_with_more_waves():
    two_pivot = [
        make_pivot(1, 100.0, "L"),
        make_pivot(2, 120.0, "H"),
    ]
    four_pivot = [
        make_pivot(1, 100.0, "L"),
        make_pivot(2, 120.0, "H"),
        make_pivot(3, 108.0, "L"),
        make_pivot(4, 150.0, "H"),
    ]
    r2 = detect_inprogress_wave(two_pivot)
    r4 = detect_inprogress_wave(four_pivot)
    assert r2 is not None
    assert r4 is not None
    assert r4.confidence > r2.confidence


# ---------------------------------------------------------------------------
# Invalidation levels
# ---------------------------------------------------------------------------


def test_bullish_invalidation_2pivots_is_wave1_start():
    pivots = [
        make_pivot(1, 100.0, "L"),
        make_pivot(2, 120.0, "H"),
    ]
    result = detect_inprogress_wave(pivots)
    assert result is not None
    assert result.invalidation == 100.0  # wave 1 start


def test_bullish_invalidation_5pivots_is_wave1_end():
    pivots = [
        make_pivot(1, 100.0, "L"),
        make_pivot(2, 120.0, "H"),  # wave 1 end = invalidation
        make_pivot(3, 108.0, "L"),
        make_pivot(4, 150.0, "H"),
        make_pivot(5, 135.0, "L"),
    ]
    result = detect_inprogress_wave(pivots)
    assert result is not None
    assert result.invalidation == 120.0  # wave 1 end (rule 3 level)


# ---------------------------------------------------------------------------
# InProgressWave properties
# ---------------------------------------------------------------------------


def test_inprogress_label_bullish():
    pivots = [
        make_pivot(1, 100.0, "L"),
        make_pivot(2, 120.0, "H"),
        make_pivot(3, 108.0, "L"),
    ]
    result = detect_inprogress_wave(pivots)
    assert result is not None
    assert "3" in result.label
    assert "↑" in result.label


def test_inprogress_summary_contains_structure():
    pivots = [
        make_pivot(1, 100.0, "L"),
        make_pivot(2, 120.0, "H"),
    ]
    result = detect_inprogress_wave(pivots)
    assert result is not None
    assert "IMPULSE" in result.summary
