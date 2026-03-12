from monitor.price_confirmation import evaluate_price_confirmation


def test_price_inside_range():
    result = evaluate_price_confirmation(
        price=70000,
        confirmation=74050,
        invalidation=65618,
        bias="BULLISH",
    )

    assert result.state == "inside_range"


def test_price_breaks_confirmation():
    result = evaluate_price_confirmation(
        price=75000,
        confirmation=74050,
        invalidation=65618,
        bias="BULLISH",
    )

    assert result.state == "confirmed_breakout"


def test_price_breaks_invalidation():
    result = evaluate_price_confirmation(
        price=65000,
        confirmation=74050,
        invalidation=65618,
        bias="BULLISH",
    )

    assert result.state == "below_invalidation"