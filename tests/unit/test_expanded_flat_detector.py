from analysis.expanded_flat_detector import _safe_ratio, detect_expanded_flat
from analysis.swing_builder import SwingPoint


def _sw(i, p, t):
    return SwingPoint(index=i, price=p, type=t, timestamp=f"2026-01-{i:02d}")


def test_detect_bullish_expanded_flat():
    swings = [
        SwingPoint(index=1, price=100.0, type="L", timestamp="2026-01-01"),
        SwingPoint(index=2, price=120.0, type="H", timestamp="2026-01-02"),
        SwingPoint(index=3, price=95.0, type="L", timestamp="2026-01-03"),
    ]

    pattern = detect_expanded_flat(swings)

    assert pattern is not None
    assert pattern.pattern_type == "expanded_flat"
    assert pattern.direction == "bullish"
    assert pattern.a.price == 100.0
    assert pattern.b.price == 120.0
    assert pattern.c.price == 95.0


def test_detect_bearish_expanded_flat():
    swings = [
        SwingPoint(index=1, price=120.0, type="H", timestamp="2026-01-01"),
        SwingPoint(index=2, price=100.0, type="L", timestamp="2026-01-02"),
        SwingPoint(index=3, price=125.0, type="H", timestamp="2026-01-03"),
    ]

    pattern = detect_expanded_flat(swings)

    assert pattern is not None
    assert pattern.pattern_type == "expanded_flat"
    assert pattern.direction == "bearish"
    assert pattern.a.price == 120.0
    assert pattern.b.price == 100.0
    assert pattern.c.price == 125.0


def test_no_expanded_flat_when_c_not_expand():
    swings = [
        SwingPoint(index=1, price=100.0, type="L", timestamp="2026-01-01"),
        SwingPoint(index=2, price=120.0, type="H", timestamp="2026-01-02"),
        SwingPoint(index=3, price=105.0, type="L", timestamp="2026-01-03"),
    ]

    pattern = detect_expanded_flat(swings)

    assert pattern is None


def test_safe_ratio_zero_denominator():
    assert _safe_ratio(5.0, 0.0) == 0.0


def test_bullish_expanded_flat_ab_zero_skips():
    swings = [_sw(1, 100.0, "L"), _sw(2, 100.0, "H"), _sw(3, 95.0, "L")]
    assert detect_expanded_flat(swings) is None


def test_bullish_expanded_flat_bc_zero_skips():
    swings = [_sw(1, 100.0, "L"), _sw(2, 110.0, "H"), _sw(3, 110.0, "L")]
    assert detect_expanded_flat(swings) is None


def test_bearish_expanded_flat_ab_zero_skips():
    swings = [_sw(1, 100.0, "H"), _sw(2, 100.0, "L"), _sw(3, 105.0, "H")]
    assert detect_expanded_flat(swings) is None


def test_too_few_swings_returns_none():
    assert detect_expanded_flat([_sw(1, 100.0, "L")]) is None