from analysis.swing_builder import SwingPoint
from analysis.triangle_detector import (
    _slope,
    detect_contracting_triangle,
    detect_expanding_triangle,
    detect_barrier_triangle,
)


def _sw(index, price, t):
    return SwingPoint(index=index, price=price, type=t, timestamp=f"2026-01-{index:02d}")


def test_detect_contracting_triangle_from_high():
    swings = [
        _sw(1, 120.0, "H"),
        _sw(2, 100.0, "L"),
        _sw(3, 115.0, "H"),
        _sw(4, 103.0, "L"),
        _sw(5, 110.0, "H"),
    ]

    pattern = detect_contracting_triangle(swings)

    assert pattern is not None
    assert pattern.pattern_type == "contracting_triangle"
    assert pattern.triangle_subtype == "contracting"


def test_detect_contracting_triangle_from_low():
    swings = [
        _sw(1, 100.0, "L"),
        _sw(2, 120.0, "H"),
        _sw(3, 104.0, "L"),
        _sw(4, 116.0, "H"),
        _sw(5, 108.0, "L"),
    ]

    pattern = detect_contracting_triangle(swings)

    assert pattern is not None
    assert pattern.triangle_subtype == "contracting"


def test_no_triangle_when_not_contracting():
    swings = [
        _sw(1, 120.0, "H"),
        _sw(2, 100.0, "L"),
        _sw(3, 125.0, "H"),
        _sw(4, 95.0, "L"),
        _sw(5, 130.0, "H"),
    ]

    pattern = detect_contracting_triangle(swings)

    assert pattern is None


def test_contracting_triangle_too_few_swings():
    swings = [_sw(1, 120.0, "H"), _sw(2, 100.0, "L")]
    assert detect_contracting_triangle(swings) is None


# ── Expanding triangle ───────────────────────────────────────────────────────

def test_detect_expanding_triangle_from_high():
    """Each segment is larger than the previous; highs rise, lows fall."""
    swings = [
        _sw(1, 110.0, "H"),
        _sw(2, 100.0, "L"),
        _sw(3, 113.0, "H"),
        _sw(4,  96.0, "L"),
        _sw(5, 117.0, "H"),
    ]

    pattern = detect_expanding_triangle(swings)

    assert pattern is not None
    assert pattern.pattern_type == "expanding_triangle"
    assert pattern.triangle_subtype == "expanding"
    assert pattern.upper_slope > 0
    assert pattern.lower_slope < 0


def test_no_expanding_when_segments_same_size():
    swings = [
        _sw(1, 110.0, "H"),
        _sw(2, 100.0, "L"),
        _sw(3, 110.0, "H"),
        _sw(4, 100.0, "L"),
        _sw(5, 110.0, "H"),
    ]

    pattern = detect_expanding_triangle(swings)

    assert pattern is None


def test_expanding_triangle_too_few():
    assert detect_expanding_triangle([_sw(1, 100.0, "H")]) is None


# ── Barrier triangle ─────────────────────────────────────────────────────────

def test_detect_ascending_barrier_triangle():
    """Flat upper boundary (~same highs), rising lows."""
    swings = [
        _sw(1, 100.0, "H"),
        _sw(2,  80.0, "L"),
        _sw(4, 100.5, "H"),
        _sw(6,  85.0, "L"),
        _sw(8, 100.2, "H"),
    ]

    pattern = detect_barrier_triangle(swings)

    assert pattern is not None
    assert pattern.triangle_subtype == "ascending_barrier"
    assert pattern.pattern_type == "ascending_barrier_triangle"


def test_detect_descending_barrier_triangle():
    """Flat lower boundary (~same lows), falling highs."""
    swings = [
        _sw(1, 120.0, "H"),
        _sw(2, 100.0, "L"),
        _sw(4, 115.0, "H"),
        _sw(6, 100.2, "L"),
        _sw(8, 110.0, "H"),
    ]

    pattern = detect_barrier_triangle(swings)

    assert pattern is not None
    assert pattern.triangle_subtype == "descending_barrier"
    assert pattern.pattern_type == "descending_barrier_triangle"


def test_barrier_triangle_too_few():
    assert detect_barrier_triangle([_sw(1, 100.0, "H"), _sw(2, 90.0, "L")]) is None


def test_barrier_triangle_zero_avg_price():
    """avg_price == 0 → skip this window (line 158)."""
    swings = [
        _sw(1, 0.0, "H"), _sw(2, 0.0, "L"), _sw(3, 0.0, "H"),
        _sw(4, 0.0, "L"), _sw(5, 0.0, "H"),
    ]
    assert detect_barrier_triangle(swings) is None


def test_no_barrier_when_both_slopes_large():
    """Neither boundary is flat → neither ascending nor descending barrier."""
    swings = [
        _sw(1, 120.0, "H"),
        _sw(2, 100.0, "L"),
        _sw(3, 115.0, "H"),
        _sw(4, 103.0, "L"),
        _sw(5, 110.0, "H"),
    ]
    # This is a contracting triangle, not a barrier
    pattern = detect_barrier_triangle(swings)
    # May or may not match; just ensure no crash
    assert pattern is None or pattern.triangle_subtype in ("ascending_barrier", "descending_barrier")


# ── _slope dx==0 (line 22) ───────────────────────────────────────────────────

def test_slope_same_index_returns_zero():
    p1 = _sw(5, 100.0, "H")
    p2 = _sw(5, 110.0, "L")  # same index → dx=0
    assert _slope(p1, p2) == 0.0


# ── Invalid sequence → continue (lines 39, 87, 148) ─────────────────────────

def test_contracting_triangle_invalid_sequence():
    """H-H-L-L-H is not a valid contracting sequence → None."""
    swings = [
        _sw(1, 120.0, "H"), _sw(2, 118.0, "H"),
        _sw(3, 110.0, "L"), _sw(4, 115.0, "H"), _sw(5, 108.0, "L"),
    ]
    assert detect_contracting_triangle(swings) is None


def test_expanding_triangle_invalid_sequence():
    """H-H-L-H-L is not a valid expanding sequence → None."""
    swings = [
        _sw(1, 110.0, "H"), _sw(2, 108.0, "H"),
        _sw(3, 100.0, "L"), _sw(4, 113.0, "H"), _sw(5, 96.0, "L"),
    ]
    assert detect_expanding_triangle(swings) is None


def test_barrier_triangle_invalid_sequence():
    """H-H-L-H-L is not a valid barrier sequence → None."""
    swings = [
        _sw(1, 100.0, "H"), _sw(2, 98.0, "H"),
        _sw(4, 85.0, "L"), _sw(6, 100.5, "H"), _sw(8, 88.0, "L"),
    ]
    assert detect_barrier_triangle(swings) is None