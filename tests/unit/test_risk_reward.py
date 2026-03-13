from analysis.risk_reward import calculate_rr, calculate_rr_levels


def test_calculate_rr_supports_bullish_bearish_aliases():
    assert calculate_rr("BULLISH", 100.0, 95.0, 110.0) == 2.0
    assert calculate_rr("BEARISH", 100.0, 105.0, 90.0) == 2.0


def test_calculate_rr_levels_returns_expected_values():
    levels = calculate_rr_levels(
        side="SHORT",
        entry_price=63030.0,
        stop_loss=74050.0,
        tp1=52010.0,
        tp2=49012.56,
        tp3=45199.64,
    )

    assert levels == {
        "rr_tp1": 1.0,
        "rr_tp2": 1.272,
        "rr_tp3": 1.618,
    }
