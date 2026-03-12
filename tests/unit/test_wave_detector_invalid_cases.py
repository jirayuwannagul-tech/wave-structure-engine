from analysis.pivot_detector import Pivot
from analysis.wave_detector import detect_latest_impulse


def test_no_bearish_impulse_when_wave4_overlaps_wave1():
    pivots = [
        Pivot(index=1, price=100, type="H", timestamp="2026-01-01"),
        Pivot(index=2, price=90, type="L", timestamp="2026-01-02"),
        Pivot(index=3, price=95, type="H", timestamp="2026-01-03"),
        Pivot(index=4, price=70, type="L", timestamp="2026-01-04"),
        Pivot(index=5, price=92, type="H", timestamp="2026-01-05"),  # overlap wave1
        Pivot(index=6, price=60, type="L", timestamp="2026-01-06"),
    ]

    pattern = detect_latest_impulse(pivots)

    assert pattern is None


def test_no_bearish_impulse_when_wave5_not_extending_past_wave3():
    pivots = [
        Pivot(index=1, price=100, type="H", timestamp="2026-01-01"),
        Pivot(index=2, price=90, type="L", timestamp="2026-01-02"),
        Pivot(index=3, price=95, type="H", timestamp="2026-01-03"),
        Pivot(index=4, price=70, type="L", timestamp="2026-01-04"),
        Pivot(index=5, price=80, type="H", timestamp="2026-01-05"),
        Pivot(index=6, price=72, type="L", timestamp="2026-01-06"),  # wave5 fail
    ]

    pattern = detect_latest_impulse(pivots)

    assert pattern is None


def test_no_bullish_impulse_when_wave2_retraces_too_deep():
    pivots = [
        Pivot(index=1, price=100, type="L", timestamp="2026-01-01"),
        Pivot(index=2, price=110, type="H", timestamp="2026-01-02"),
        Pivot(index=3, price=99, type="L", timestamp="2026-01-03"),  # below origin
        Pivot(index=4, price=125, type="H", timestamp="2026-01-04"),
        Pivot(index=5, price=118, type="L", timestamp="2026-01-05"),
        Pivot(index=6, price=135, type="H", timestamp="2026-01-06"),
    ]

    pattern = detect_latest_impulse(pivots)

    assert pattern is None