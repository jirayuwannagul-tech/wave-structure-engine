from analysis.flat_detector import _safe_ratio, detect_flat
from analysis.swing_builder import SwingPoint


def _sw(index, price, t):
    return SwingPoint(index=index, price=price, type=t, timestamp=f"2026-01-{index:02d}")


def test_detect_bullish_flat():
    # Regular Flat: bc/ab must be 0.90-1.05; bc=18, ab=20 → ratio=0.90
    swings = [
        SwingPoint(index=1, price=100.0, type="L", timestamp="2026-01-01"),
        SwingPoint(index=2, price=120.0, type="H", timestamp="2026-01-02"),
        SwingPoint(index=3, price=102.0, type="L", timestamp="2026-01-03"),
    ]

    pattern = detect_flat(swings)

    assert pattern is not None
    assert pattern.pattern_type == "flat"
    assert pattern.direction == "bullish"


def test_detect_bearish_flat():
    # Regular Flat bearish: bc/ab must be 0.90-1.05; bc=18, ab=20 → ratio=0.90
    swings = [
        SwingPoint(index=1, price=120.0, type="H", timestamp="2026-01-01"),
        SwingPoint(index=2, price=100.0, type="L", timestamp="2026-01-02"),
        SwingPoint(index=3, price=118.0, type="H", timestamp="2026-01-03"),
    ]

    pattern = detect_flat(swings)

    assert pattern is not None
    assert pattern.pattern_type == "flat"
    assert pattern.direction == "bearish"


# ── _safe_ratio zero denominator (line 24) ───────────────────────────────────

def test_safe_ratio_zero_denominator():
    assert _safe_ratio(5.0, 0.0) == 0.0


# ── Bullish ab<=0 skip (line 41) ─────────────────────────────────────────────

def test_detect_flat_bullish_ab_zero_skips():
    """L-H where H==L → ab=0 → skip, return None."""
    swings = [_sw(1, 100.0, "L"), _sw(2, 100.0, "H"), _sw(3, 99.0, "L")]
    assert detect_flat(swings) is None


def test_detect_flat_bullish_bc_zero_skips():
    """C.price == B.price → bc=0 → skip."""
    swings = [_sw(1, 100.0, "L"), _sw(2, 110.0, "H"), _sw(3, 110.0, "L")]
    assert detect_flat(swings) is None


# ── Bearish ab<=0 skip (line 66) ─────────────────────────────────────────────

def test_detect_flat_bearish_ab_zero_skips():
    """H-L where L==H → ab=0 → skip, return None."""
    swings = [_sw(1, 100.0, "H"), _sw(2, 100.0, "L"), _sw(3, 101.0, "H")]
    assert detect_flat(swings) is None


# ── No pattern → return None (line 85) ───────────────────────────────────────

def test_detect_flat_no_match_returns_none():
    """bc/ab = 3/10 = 0.30 < 0.90 → no flat detected."""
    swings = [_sw(1, 100.0, "L"), _sw(2, 110.0, "H"), _sw(3, 107.0, "L")]
    assert detect_flat(swings) is None


def test_detect_flat_too_few_returns_none():
    assert detect_flat([_sw(1, 100.0, "L"), _sw(2, 110.0, "H")]) is None