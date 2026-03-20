from storage.manual_wave_context import get_manual_wave_context


def test_get_manual_wave_context_returns_seeded_btc_weekly_context():
    context = get_manual_wave_context("BTCUSDT", "1W")

    assert context is not None
    assert context.symbol == "BTCUSDT"
    assert context.timeframe == "1W"
    assert context.bias == "BULLISH"
    assert context.wave_number == "B"
    assert context.structure == "ABC_CORRECTION"
    assert context.position == "WAVE_B_IN_PROGRESS"
