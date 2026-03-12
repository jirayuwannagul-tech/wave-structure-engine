from analysis.swing_builder import SwingPoint
from analysis.triangle_detector import detect_contracting_triangle


def test_detect_contracting_triangle_from_high():
    swings = [
        SwingPoint(index=1, price=120.0, type="H", timestamp="2026-01-01"),
        SwingPoint(index=2, price=100.0, type="L", timestamp="2026-01-02"),
        SwingPoint(index=3, price=115.0, type="H", timestamp="2026-01-03"),
        SwingPoint(index=4, price=103.0, type="L", timestamp="2026-01-04"),
        SwingPoint(index=5, price=110.0, type="H", timestamp="2026-01-05"),
    ]

    pattern = detect_contracting_triangle(swings)

    assert pattern is not None
    assert pattern.pattern_type == "contracting_triangle"


def test_no_triangle_when_not_contracting():
    swings = [
        SwingPoint(index=1, price=120.0, type="H", timestamp="2026-01-01"),
        SwingPoint(index=2, price=100.0, type="L", timestamp="2026-01-02"),
        SwingPoint(index=3, price=125.0, type="H", timestamp="2026-01-03"),
        SwingPoint(index=4, price=95.0, type="L", timestamp="2026-01-04"),
        SwingPoint(index=5, price=130.0, type="H", timestamp="2026-01-05"),
    ]

    pattern = detect_contracting_triangle(swings)

    assert pattern is None