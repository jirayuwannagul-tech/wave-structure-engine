from analysis.expanded_flat_detector import detect_expanded_flat
from analysis.swing_builder import SwingPoint


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