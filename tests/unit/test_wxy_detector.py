from analysis.swing_builder import SwingPoint
from analysis.wxy_detector import _safe_ratio, detect_wxy


def _sw(i, p, t):
    return SwingPoint(index=i, price=p, type=t, timestamp=f"2026-01-{i:02d}")


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


def test_safe_ratio_zero_denominator():
    assert _safe_ratio(3.0, 0.0) == 0.0


def test_bullish_wxy_wx_zero_skips():
    # w.price == x.price → wx=0 → skip
    swings = [_sw(1, 100.0, "L"), _sw(2, 100.0, "H"), _sw(3, 95.0, "L")]
    assert detect_wxy(swings) is None


def test_bullish_wxy_xy_zero_skips():
    # y.price == x.price → xy=0 → skip
    swings = [_sw(1, 100.0, "L"), _sw(2, 120.0, "H"), _sw(3, 120.0, "L")]
    assert detect_wxy(swings) is None


def test_bearish_wxy_wx_zero_skips():
    # w.price == x.price → wx=0 → skip
    swings = [_sw(1, 100.0, "H"), _sw(2, 100.0, "L"), _sw(3, 105.0, "H")]
    assert detect_wxy(swings) is None


def test_too_few_swings_returns_none():
    assert detect_wxy([_sw(1, 100.0, "L")]) is None