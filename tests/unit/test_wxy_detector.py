from analysis.swing_builder import SwingPoint
from analysis.wxy_detector import detect_wxy


def test_detect_bullish_wxy():
    swings = [
        SwingPoint(index=1, price=100.0, type="L", timestamp="2026-01-01"),
        SwingPoint(index=2, price=120.0, type="H", timestamp="2026-01-02"),
        SwingPoint(index=3, price=108.0, type="L", timestamp="2026-01-03"),
    ]

    pattern = detect_wxy(swings)

    assert pattern is not None
    assert pattern.pattern_type == "WXY"
    assert pattern.direction == "bullish"


def test_detect_bearish_wxy():
    swings = [
        SwingPoint(index=1, price=120.0, type="H", timestamp="2026-01-01"),
        SwingPoint(index=2, price=100.0, type="L", timestamp="2026-01-02"),
        SwingPoint(index=3, price=112.0, type="H", timestamp="2026-01-03"),
    ]

    pattern = detect_wxy(swings)

    assert pattern is not None
    assert pattern.pattern_type == "WXY"
    assert pattern.direction == "bearish"


def test_no_wxy_when_retrace_too_small():
    swings = [
        SwingPoint(index=1, price=100.0, type="L", timestamp="2026-01-01"),
        SwingPoint(index=2, price=120.0, type="H", timestamp="2026-01-02"),
        SwingPoint(index=3, price=119.5, type="L", timestamp="2026-01-03"),
    ]

    pattern = detect_wxy(swings)

    assert pattern is None