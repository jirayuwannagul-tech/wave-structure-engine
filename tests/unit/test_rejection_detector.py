from monitor.rejection_detector import detect_rejection


def test_no_rejection():
    result = detect_rejection(
        price=70000,
        invalidation_level=65618,
        bias="BULLISH",
    )

    assert result.state == "no_rejection"


def test_bullish_rejection():
    result = detect_rejection(
        price=65620,
        invalidation_level=65618,
        bias="BULLISH",
    )

    assert result.state == "bullish_rejection"


def test_bearish_rejection():
    result = detect_rejection(
        price=74048,
        invalidation_level=74050,
        bias="BEARISH",
    )

    assert result.state == "bearish_rejection"