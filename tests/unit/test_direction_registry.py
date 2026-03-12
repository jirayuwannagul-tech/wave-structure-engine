from analysis.patterns.direction_registry import (
    get_direction,
    is_bullish,
    is_bearish,
)


def test_get_direction_bullish():
    assert get_direction("bullish") == "BULLISH"
    assert get_direction("up") == "BULLISH"


def test_get_direction_bearish():
    assert get_direction("bearish") == "BEARISH"
    assert get_direction("down") == "BEARISH"


def test_get_direction_neutral():
    assert get_direction(None) == "NEUTRAL"
    assert get_direction("sideways") == "NEUTRAL"


def test_direction_helpers():
    assert is_bullish("BULLISH") is True
    assert is_bearish("BEARISH") is True