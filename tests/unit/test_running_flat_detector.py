from analysis.running_flat_detector import detect_running_flat
from analysis.swing_builder import SwingPoint


def test_detect_bullish_running_flat():
    swings = [
        SwingPoint(index=1, price=100.0, type="L", timestamp="2026-01-01"),
        SwingPoint(index=2, price=120.0, type="H", timestamp="2026-01-02"),
        SwingPoint(index=3, price=105.0, type="L", timestamp="2026-01-03"),
    ]

    pattern = detect_running_flat(swings)

    assert pattern is not None
    assert pattern.pattern_type == "running_flat"
    assert pattern.direction == "bullish"


def test_detect_bearish_running_flat():
    swings = [
        SwingPoint(index=1, price=120.0, type="H", timestamp="2026-01-01"),
        SwingPoint(index=2, price=100.0, type="L", timestamp="2026-01-02"),
        SwingPoint(index=3, price=115.0, type="H", timestamp="2026-01-03"),
    ]

    pattern = detect_running_flat(swings)

    assert pattern is not None
    assert pattern.pattern_type == "running_flat"
    assert pattern.direction == "bearish"


def test_no_running_flat_when_c_expands_too_far():
    swings = [
        SwingPoint(index=1, price=100.0, type="L", timestamp="2026-01-01"),
        SwingPoint(index=2, price=120.0, type="H", timestamp="2026-01-02"),
        SwingPoint(index=3, price=95.0, type="L", timestamp="2026-01-03"),
    ]

    pattern = detect_running_flat(swings)

    assert pattern is None