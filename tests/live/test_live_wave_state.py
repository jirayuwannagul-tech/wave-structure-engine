from live.live_wave_state import LiveWaveState


def test_live_wave_state_update_and_snapshot():
    state = LiveWaveState()

    state.update("ABC_CORRECTION", "BULLISH", 70000.0)
    snap = state.snapshot()

    assert snap["structure"] == "ABC_CORRECTION"
    assert snap["bias"] == "BULLISH"
    assert snap["price"] == 70000.0