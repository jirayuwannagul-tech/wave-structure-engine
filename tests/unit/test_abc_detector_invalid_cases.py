from analysis.pivot_detector import Pivot
from analysis.wave_detector import detect_latest_abc


def test_no_bullish_abc_when_c_breaks_below_a():
    pivots = [
        Pivot(index=1, price=100, type="L", timestamp="2026-01-01"),
        Pivot(index=2, price=120, type="H", timestamp="2026-01-02"),
        Pivot(index=3, price=95, type="L", timestamp="2026-01-03"),  # ต่ำกว่า A
    ]

    pattern = detect_latest_abc(pivots)

    assert pattern is None


def test_no_bearish_abc_when_c_breaks_above_a():
    pivots = [
        Pivot(index=1, price=120, type="H", timestamp="2026-01-01"),
        Pivot(index=2, price=100, type="L", timestamp="2026-01-02"),
        Pivot(index=3, price=125, type="H", timestamp="2026-01-03"),  # สูงกว่า A
    ]

    pattern = detect_latest_abc(pivots)

    assert pattern is None


def test_no_abc_when_pivot_types_do_not_match():
    pivots = [
        Pivot(index=1, price=100, type="L", timestamp="2026-01-01"),
        Pivot(index=2, price=105, type="L", timestamp="2026-01-02"),
        Pivot(index=3, price=110, type="H", timestamp="2026-01-03"),
    ]

    pattern = detect_latest_abc(pivots)

    assert pattern is None


def test_detect_valid_bullish_abc():
    pivots = [
        Pivot(index=1, price=100, type="L", timestamp="2026-01-01"),
        Pivot(index=2, price=120, type="H", timestamp="2026-01-02"),
        Pivot(index=3, price=110, type="L", timestamp="2026-01-03"),
    ]

    pattern = detect_latest_abc(pivots)

    assert pattern is not None
    assert pattern.direction == "bullish"
    assert pattern.a.price == 100
    assert pattern.b.price == 120
    assert pattern.c.price == 110