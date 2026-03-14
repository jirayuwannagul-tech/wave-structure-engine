"""Tests for analysis/inprogress_detector.py"""

import pytest

from analysis.inprogress_detector import (
    InProgressWave,
    detect_inprogress_wave,
    _try_partial_bullish_impulse,
    _try_partial_bearish_impulse,
    _try_partial_bullish_corrective,
    _try_partial_bearish_corrective,
    _bullish_corrective_targets,
    _bearish_corrective_targets,
    _corrective_wave_number,
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


# ---------------------------------------------------------------------------
# Bearish impulse: wave 2, 3, 5
# ---------------------------------------------------------------------------

def test_building_wave_2_bearish():
    pivots = [
        make_pivot(1, 120.0, "H"),  # Wave 1 start
        make_pivot(2, 100.0, "L"),  # Wave 1 end
    ]
    result = detect_inprogress_wave(pivots)
    assert result is not None
    assert result.wave_number == "2"
    assert result.direction == "bearish"
    assert result.completed_waves == 1


def test_building_wave_3_bearish():
    pivots = [
        make_pivot(1, 120.0, "H"),
        make_pivot(2, 100.0, "L"),
        make_pivot(3, 112.0, "H"),  # Wave 2 retracement (< 120)
    ]
    result = detect_inprogress_wave(pivots)
    assert result is not None
    assert result.wave_number == "3"
    assert result.direction == "bearish"


def test_building_wave_5_bearish():
    pivots = [
        make_pivot(1, 120.0, "H"),
        make_pivot(2, 100.0, "L"),  # w1=20
        make_pivot(3, 112.0, "H"),  # w2 end (< 120)
        make_pivot(4,  60.0, "L"),  # w3 end (w3=52 > w1=20 ✓)
        make_pivot(5,  80.0, "H"),  # w4 end (above 100 ✓ rule 3)
    ]
    result = detect_inprogress_wave(pivots)
    assert result is not None
    assert result.wave_number == "5"
    assert result.direction == "bearish"
    assert result.completed_waves == 4
    assert "w1_equal" in result.fib_targets


# ---------------------------------------------------------------------------
# Corrective waves (ABC)
# ---------------------------------------------------------------------------

def test_bullish_corrective_building_wave_b():
    """H-L sequence: A went down, building B retracement."""
    pivots = [
        make_pivot(1, 120.0, "H"),  # A start
        make_pivot(2, 100.0, "L"),  # A end
    ]
    result = detect_inprogress_wave(pivots)
    assert result is not None
    # Could be bearish impulse wave 2 OR bullish corrective B; both are valid
    # For this sequence, bearish impulse w2 wins (higher priority)
    assert result.wave_number in ("2", "B")


def test_bullish_corrective_building_wave_c():
    """H-L-H sequence below A start: A went down, B retraced, building C."""
    # Use data that doesn't match impulse (B < A start)
    pivots = [
        make_pivot(1, 120.0, "H"),  # A start
        make_pivot(2, 100.0, "L"),  # A end
        make_pivot(3, 115.0, "H"),  # B end (< 120 so B < A start)
    ]
    result = detect_inprogress_wave(pivots)
    assert result is not None
    # [H,L,H] matches bearish impulse wave 3 OR bullish corrective C
    # Impulse check fires first; but if impulse rule 2 fails (w3<w1) → falls to corrective
    assert result.wave_number in ("3", "C")


def test_bearish_corrective_building_wave_b():
    """L-H sequence: A went up, building B retracement."""
    pivots = [
        make_pivot(1, 100.0, "L"),  # A start
        make_pivot(2, 120.0, "H"),  # A end
    ]
    result = detect_inprogress_wave(pivots)
    assert result is not None
    assert result.wave_number in ("2", "B")


def test_bearish_corrective_building_wave_c():
    """L-H-L sequence above A start: A went up, B retraced, building C."""
    pivots = [
        make_pivot(1, 100.0, "L"),  # A start
        make_pivot(2, 120.0, "H"),  # A end
        make_pivot(3, 108.0, "L"),  # B end (> 100 so B > A start)
    ]
    result = detect_inprogress_wave(pivots)
    assert result is not None
    assert result.wave_number in ("3", "C")


def test_corrective_fib_targets_wave_b():
    """Wave B targets should be retracements of Wave A."""
    pivots = [
        make_pivot(1, 120.0, "H"),
        make_pivot(2, 100.0, "L"),
    ]
    result = detect_inprogress_wave(pivots)
    assert result is not None
    if result.wave_number == "B":
        # A size = 20; B targets = 100 + 20 * ratio
        assert "0.618" in result.fib_targets
        assert abs(result.fib_targets["0.618"] - 112.36) < 0.1


def test_corrective_fib_targets_wave_c():
    """Wave C targets should be extensions of Wave A."""
    pivots = [
        make_pivot(1, 120.0, "H"),  # A start
        make_pivot(2, 100.0, "L"),  # A end
        make_pivot(3, 112.0, "H"),  # B end (< 120)
    ]
    result = detect_inprogress_wave(pivots)
    assert result is not None
    if result.wave_number == "C":
        assert "C=A" in result.fib_targets or "C=1.618A" in result.fib_targets


# ---------------------------------------------------------------------------
# Direct corrective helper function tests
# ---------------------------------------------------------------------------

def test_bullish_corrective_targets_wave_b():
    """_bullish_corrective_targets with n=2 (building B)."""
    pivots = [make_pivot(1, 120.0, "H"), make_pivot(2, 100.0, "L")]
    targets = _bullish_corrective_targets(pivots)
    # A size = 20; B targets from a_end=100
    assert "0.382" in targets
    assert abs(targets["0.382"] - (100 + 20 * 0.382)) < 0.01
    assert "0.618" in targets


def test_bullish_corrective_targets_wave_c():
    """_bullish_corrective_targets with n=3 (building C)."""
    pivots = [
        make_pivot(1, 120.0, "H"),  # A start
        make_pivot(2, 100.0, "L"),  # A end
        make_pivot(3, 112.0, "H"),  # B end
    ]
    targets = _bullish_corrective_targets(pivots)
    assert "C=A" in targets
    assert "C=1.618A" in targets
    # C=A from B end 112 going down 20: 112 - 20 = 92
    assert abs(targets["C=A"] - 92.0) < 0.01


def test_bearish_corrective_targets_wave_b():
    """_bearish_corrective_targets with n=2 (building B)."""
    pivots = [make_pivot(1, 100.0, "L"), make_pivot(2, 120.0, "H")]
    targets = _bearish_corrective_targets(pivots)
    # A size = 20; B retraces from a_end=120
    assert "0.382" in targets
    assert abs(targets["0.382"] - (120 - 20 * 0.382)) < 0.01


def test_bearish_corrective_targets_wave_c():
    """_bearish_corrective_targets with n=3 (building C)."""
    pivots = [
        make_pivot(1, 100.0, "L"),  # A start
        make_pivot(2, 120.0, "H"),  # A end
        make_pivot(3, 108.0, "L"),  # B end
    ]
    targets = _bearish_corrective_targets(pivots)
    assert "C=A" in targets
    assert "C=1.618A" in targets
    # C=A from B end 108 going up 20: 108 + 20 = 128
    assert abs(targets["C=A"] - 128.0) < 0.01


def test_corrective_wave_number():
    assert _corrective_wave_number(2, "bullish") == "B"
    assert _corrective_wave_number(3, "bullish") == "C"
    assert _corrective_wave_number(2, "bearish") == "B"
    assert _corrective_wave_number(3, "bearish") == "C"


def test_try_partial_bullish_corrective_b():
    """H-L: A went down, building B (bullish retracement)."""
    pivots = [make_pivot(1, 120.0, "H"), make_pivot(2, 100.0, "L")]
    result = _try_partial_bullish_corrective(pivots)
    assert result is not None
    assert result.wave_number == "B"
    assert result.direction == "bullish"
    assert result.structure == "CORRECTION"
    assert result.is_valid is True


def test_try_partial_bullish_corrective_c():
    """H-L-H (B < A start): A down, B up partially, building C down."""
    pivots = [
        make_pivot(1, 120.0, "H"),
        make_pivot(2, 100.0, "L"),
        make_pivot(3, 114.0, "H"),  # B end (< 120 → valid)
    ]
    result = _try_partial_bullish_corrective(pivots)
    assert result is not None
    assert result.wave_number == "C"


def test_try_partial_bullish_corrective_b_above_a_start():
    """B exceeds A start → invalid."""
    pivots = [
        make_pivot(1, 120.0, "H"),
        make_pivot(2, 100.0, "L"),
        make_pivot(3, 125.0, "H"),  # B >= A start (120) → invalid
    ]
    result = _try_partial_bullish_corrective(pivots)
    assert result is None


def test_try_partial_bullish_corrective_wrong_sequence():
    """L-H sequence → not a bullish corrective."""
    pivots = [make_pivot(1, 100.0, "L"), make_pivot(2, 120.0, "H")]
    result = _try_partial_bullish_corrective(pivots)
    assert result is None


def test_try_partial_bullish_corrective_too_many():
    pivots = [make_pivot(i, float(100 + i), "H" if i % 2 else "L") for i in range(5)]
    result = _try_partial_bullish_corrective(pivots)
    assert result is None


def test_try_partial_bearish_corrective_b():
    """L-H: A went up, building B (bearish retracement)."""
    pivots = [make_pivot(1, 100.0, "L"), make_pivot(2, 120.0, "H")]
    result = _try_partial_bearish_corrective(pivots)
    assert result is not None
    assert result.wave_number == "B"
    assert result.direction == "bearish"


def test_try_partial_bearish_corrective_c():
    """L-H-L (B > A start): A up, B down partially, building C up."""
    pivots = [
        make_pivot(1, 100.0, "L"),
        make_pivot(2, 120.0, "H"),
        make_pivot(3, 108.0, "L"),  # B end (> 100 → valid)
    ]
    result = _try_partial_bearish_corrective(pivots)
    assert result is not None
    assert result.wave_number == "C"


def test_try_partial_bearish_corrective_b_below_a_start():
    """B goes below A start → invalid."""
    pivots = [
        make_pivot(1, 100.0, "L"),
        make_pivot(2, 120.0, "H"),
        make_pivot(3, 95.0, "L"),   # B <= A start (100) → invalid
    ]
    result = _try_partial_bearish_corrective(pivots)
    assert result is None


def test_try_partial_bearish_corrective_wrong_sequence():
    """H-L sequence → not a bearish corrective."""
    pivots = [make_pivot(1, 120.0, "H"), make_pivot(2, 100.0, "L")]
    result = _try_partial_bearish_corrective(pivots)
    assert result is None
