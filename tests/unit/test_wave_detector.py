from analysis.pivot_detector import Pivot
from analysis.wave_detector import detect_latest_impulse


def test_detect_valid_bearish_impulse():
    pivots = [
        Pivot(index=1, price=100, type="H", timestamp="2026-01-01"),
        Pivot(index=2, price=90, type="L", timestamp="2026-01-02"),
        Pivot(index=3, price=95, type="H", timestamp="2026-01-03"),
        Pivot(index=4, price=70, type="L", timestamp="2026-01-04"),
        Pivot(index=5, price=80, type="H", timestamp="2026-01-05"),
        Pivot(index=6, price=60, type="L", timestamp="2026-01-06"),
    ]

    pattern = detect_latest_impulse(pivots)

    assert pattern is not None
    assert pattern.direction == "bearish"
    assert pattern.is_valid is True
    assert pattern.p1.price == 100
    assert pattern.p6.price == 60


def test_no_impulse_if_rules_broken():
    pivots = [
        Pivot(index=1, price=100, type="H", timestamp="2026-01-01"),
        Pivot(index=2, price=90, type="L", timestamp="2026-01-02"),
        Pivot(index=3, price=110, type="H", timestamp="2026-01-03"),  # invalid wave2
        Pivot(index=4, price=70, type="L", timestamp="2026-01-04"),
        Pivot(index=5, price=80, type="H", timestamp="2026-01-05"),
        Pivot(index=6, price=60, type="L", timestamp="2026-01-06"),
    ]

    pattern = detect_latest_impulse(pivots)

    assert pattern is None


def test_detect_bearish_impulse_with_truncated_wave5_when_wave5_is_still_large():
    pivots = [
        Pivot(index=1, price=100, type="H", timestamp="2026-01-01"),
        Pivot(index=2, price=90, type="L", timestamp="2026-01-02"),
        Pivot(index=3, price=98, type="H", timestamp="2026-01-03"),
        Pivot(index=4, price=60, type="L", timestamp="2026-01-04"),
        Pivot(index=5, price=80, type="H", timestamp="2026-01-05"),
        Pivot(index=6, price=68, type="L", timestamp="2026-01-06"),
    ]

    pattern = detect_latest_impulse(pivots)

    assert pattern is not None
    assert pattern.direction == "bearish"
    assert pattern.is_valid is True
