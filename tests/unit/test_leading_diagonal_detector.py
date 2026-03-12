from analysis.leading_diagonal_detector import detect_leading_diagonal
from analysis.pivot_detector import Pivot


def test_detect_bullish_leading_diagonal():
    pivots = [
        Pivot(index=1, price=100.0, type="L", timestamp="2026-01-01"),
        Pivot(index=2, price=120.0, type="H", timestamp="2026-01-02"),
        Pivot(index=3, price=108.0, type="L", timestamp="2026-01-03"),
        Pivot(index=4, price=122.0, type="H", timestamp="2026-01-04"),
        Pivot(index=5, price=112.0, type="L", timestamp="2026-01-05"),
    ]

    pattern = detect_leading_diagonal(pivots)

    assert pattern is not None
    assert pattern.pattern_type == "leading_diagonal"
    assert pattern.direction == "bullish"


def test_detect_bearish_leading_diagonal():
    pivots = [
        Pivot(index=1, price=120.0, type="H", timestamp="2026-01-01"),
        Pivot(index=2, price=100.0, type="L", timestamp="2026-01-02"),
        Pivot(index=3, price=112.0, type="H", timestamp="2026-01-03"),
        Pivot(index=4, price=98.0, type="L", timestamp="2026-01-04"),
        Pivot(index=5, price=108.0, type="H", timestamp="2026-01-05"),
    ]

    pattern = detect_leading_diagonal(pivots)

    assert pattern is not None
    assert pattern.pattern_type == "leading_diagonal"
    assert pattern.direction == "bearish"


def test_no_leading_diagonal_when_not_enough_points():
    pivots = [
        Pivot(index=1, price=120.0, type="H", timestamp="2026-01-01"),
        Pivot(index=2, price=100.0, type="L", timestamp="2026-01-02"),
        Pivot(index=3, price=112.0, type="H", timestamp="2026-01-03"),
    ]

    pattern = detect_leading_diagonal(pivots)

    assert pattern is None