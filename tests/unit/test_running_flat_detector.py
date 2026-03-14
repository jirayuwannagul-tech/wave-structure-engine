from analysis.running_flat_detector import _safe_ratio, detect_running_flat
from analysis.swing_builder import SwingPoint


def _sw(i, p, t):
    return SwingPoint(index=i, price=p, type=t, timestamp=f"2026-01-{i:02d}")


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


def test_safe_ratio_zero_denominator():
    assert _safe_ratio(5.0, 0.0) == 0.0


def test_bullish_running_flat_ab_zero_skips():
    swings = [_sw(1, 100.0, "L"), _sw(2, 100.0, "H"), _sw(3, 99.0, "L")]
    assert detect_running_flat(swings) is None


def test_bullish_running_flat_bc_zero_skips():
    swings = [_sw(1, 100.0, "L"), _sw(2, 110.0, "H"), _sw(3, 110.0, "L")]
    assert detect_running_flat(swings) is None


def test_bearish_running_flat_ab_zero_skips():
    swings = [_sw(1, 100.0, "H"), _sw(2, 100.0, "L"), _sw(3, 101.0, "H")]
    assert detect_running_flat(swings) is None


def test_too_few_swings_returns_none():
    assert detect_running_flat([_sw(1, 100.0, "L")]) is None