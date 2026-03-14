from analysis.corrective_detector import detect_latest_correction, detect_zigzag
from analysis.pivot_detector import Pivot
from analysis.swing_builder import SwingPoint


def _sw(index, price, t):
    return SwingPoint(index=index, price=price, type=t, timestamp=f"2026-01-{index:02d}")


def test_detect_valid_bullish_zigzag():
    pivots = [
        Pivot(index=1, price=63000, type="L", timestamp="2026-01-01"),
        Pivot(index=2, price=74000, type="H", timestamp="2026-01-02"),
        Pivot(index=3, price=66000, type="L", timestamp="2026-01-03"),
    ]

    pattern = detect_zigzag(pivots)

    assert pattern is not None
    assert pattern.direction == "bullish"
    assert pattern.a.price == 63000
    assert pattern.b.price == 74000
    assert pattern.c.price == 66000


def test_detect_valid_bearish_zigzag():
    pivots = [
        Pivot(index=1, price=74000, type="H", timestamp="2026-01-01"),
        Pivot(index=2, price=63000, type="L", timestamp="2026-01-02"),
        Pivot(index=3, price=69000, type="H", timestamp="2026-01-03"),
    ]

    pattern = detect_zigzag(pivots)

    assert pattern is not None
    assert pattern.direction == "bearish"
    assert pattern.a.price == 74000
    assert pattern.b.price == 63000
    assert pattern.c.price == 69000


# ── detect_latest_correction ─────────────────────────────────────────────────

def test_detect_latest_correction_too_few():
    assert detect_latest_correction([_sw(1, 100.0, "L"), _sw(2, 110.0, "H")]) is None


def test_detect_latest_correction_bullish_flat():
    """bc/ab < 0.5 → flat pattern."""
    swings = [
        _sw(1, 100.0, "L"),
        _sw(2, 120.0, "H"),
        _sw(3, 112.0, "L"),  # bc = 8, ab = 20, ratio = 0.40 → flat
    ]
    pattern = detect_latest_correction(swings)
    assert pattern is not None
    assert pattern.direction == "bullish"
    assert pattern.pattern_type == "flat"


def test_detect_latest_correction_bullish_zigzag():
    """bc/ab ≥ 0.5 → zigzag pattern."""
    swings = [
        _sw(1, 100.0, "L"),
        _sw(2, 120.0, "H"),
        _sw(3, 108.0, "L"),  # bc = 12, ab = 20, ratio = 0.60 → zigzag
    ]
    pattern = detect_latest_correction(swings)
    assert pattern is not None
    assert pattern.pattern_type == "zigzag"


def test_detect_latest_correction_bearish_flat():
    """Bearish correction, bc/ab < 0.5 → flat."""
    swings = [
        _sw(1, 120.0, "H"),
        _sw(2, 100.0, "L"),
        _sw(3, 108.0, "H"),  # bc = 8, ab = 20, ratio = 0.40 → flat
    ]
    pattern = detect_latest_correction(swings)
    assert pattern is not None
    assert pattern.direction == "bearish"
    assert pattern.pattern_type == "flat"


def test_detect_latest_correction_bearish_zigzag():
    """Bearish zigzag: bc/ab ≥ 0.5."""
    swings = [
        _sw(1, 120.0, "H"),
        _sw(2, 100.0, "L"),
        _sw(3, 112.0, "H"),  # bc = 12, ab = 20, ratio = 0.60 → zigzag
    ]
    pattern = detect_latest_correction(swings)
    assert pattern is not None
    assert pattern.direction == "bearish"
    assert pattern.pattern_type == "zigzag"


def test_detect_latest_correction_c_not_above_a_bullish():
    """c.price <= a.price → not a bullish correction."""
    swings = [
        _sw(1, 100.0, "L"),
        _sw(2, 120.0, "H"),
        _sw(3, 98.0, "L"),  # c below a → skip
    ]
    # This won't match the bullish branch (c > a fails)
    pattern = detect_latest_correction(swings)
    assert pattern is None


def test_detect_latest_correction_c_above_a_bearish():
    """c.price >= a.price → not a bearish correction."""
    swings = [
        _sw(1, 120.0, "H"),
        _sw(2, 100.0, "L"),
        _sw(3, 122.0, "H"),  # c above a → skip
    ]
    pattern = detect_latest_correction(swings)
    assert pattern is None


def test_detect_zigzag_returns_none_when_flat():
    """detect_zigzag filters out flat patterns."""
    swings = [
        _sw(1, 100.0, "L"),
        _sw(2, 120.0, "H"),
        _sw(3, 112.0, "L"),  # ratio=0.40 → flat, not zigzag
    ]
    assert detect_zigzag(swings) is None


def test_detect_zigzag_returns_none_when_no_correction():
    assert detect_zigzag([_sw(1, 100.0, "L")]) is None