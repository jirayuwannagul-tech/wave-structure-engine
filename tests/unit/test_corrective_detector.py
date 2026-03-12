from analysis.corrective_detector import detect_zigzag
from analysis.pivot_detector import Pivot


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