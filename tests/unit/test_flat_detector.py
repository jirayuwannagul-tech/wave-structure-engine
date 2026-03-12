from analysis.flat_detector import detect_flat
from analysis.swing_builder import SwingPoint


def test_detect_bullish_flat():
    swings = [
        SwingPoint(index=1, price=100.0, type="L", timestamp="2026-01-01"),
        SwingPoint(index=2, price=120.0, type="H", timestamp="2026-01-02"),
        SwingPoint(index=3, price=112.0, type="L", timestamp="2026-01-03"),
    ]

    pattern = detect_flat(swings)

    assert pattern is not None
    assert pattern.pattern_type == "flat"
    assert pattern.direction == "bullish"


def test_detect_bearish_flat():
    swings = [
        SwingPoint(index=1, price=120.0, type="H", timestamp="2026-01-01"),
        SwingPoint(index=2, price=100.0, type="L", timestamp="2026-01-02"),
        SwingPoint(index=3, price=108.0, type="H", timestamp="2026-01-03"),
    ]

    pattern = detect_flat(swings)

    assert pattern is not None
    assert pattern.pattern_type == "flat"
    assert pattern.direction == "bearish"