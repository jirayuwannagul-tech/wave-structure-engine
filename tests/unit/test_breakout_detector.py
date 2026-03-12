from monitor.breakout_detector import detect_breakout


def test_bullish_no_breakout():
    result = detect_breakout(
        price=70000,
        confirmation_level=74050,
        bias="BULLISH",
    )

    assert result.state == "no_breakout"
    assert result.level == 74050


def test_bullish_breakout():
    result = detect_breakout(
        price=75000,
        confirmation_level=74050,
        bias="BULLISH",
    )

    assert result.state == "bullish_breakout"
    assert result.level == 74050


def test_bearish_breakdown():
    result = detect_breakout(
        price=65000,
        confirmation_level=65618,
        bias="BEARISH",
    )

    assert result.state == "bearish_breakdown"
    assert result.level == 65618