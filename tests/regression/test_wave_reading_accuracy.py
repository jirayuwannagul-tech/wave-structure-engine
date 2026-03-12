from analysis.corrective_detector import detect_zigzag
from analysis.wave_detector import detect_latest_impulse

from tests.fixtures.sample_waves import (
    sample_bearish_impulse,
    sample_bullish_abc,
)


def test_detect_bullish_abc():
    pivots = sample_bullish_abc()

    pattern = detect_zigzag(pivots)

    assert pattern is not None
    assert pattern.pattern_type == "zigzag"
    assert pattern.direction == "bullish"
    assert pattern.a.price == 63030.0
    assert pattern.b.price == 74050.0
    assert pattern.c.price == 65618.49


def test_detect_bearish_impulse():
    pivots = sample_bearish_impulse()

    pattern = detect_latest_impulse(pivots)

    assert pattern is not None
    assert pattern.direction == "bearish"
    assert pattern.p1.price == 91224.99
    assert pattern.p6.price == 65118.0
    assert pattern.is_valid is True