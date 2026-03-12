from analysis.wave_position import WavePosition
from monitor.market_context import build_market_context
from monitor.mtf_alignment import MTFAlignmentResult
from monitor.price_confirmation import PriceConfirmation
from state.scenario_state_machine import ScenarioState


def test_build_market_context_mixed_bullish_rebound():
    wave_position = WavePosition(
        structure="ABC_CORRECTION",
        position="WAVE_C_END",
        bias="BULLISH",
        confidence="medium",
    )

    scenario_state = ScenarioState(
        state="waiting_confirmation",
        active_scenario="Main Bullish",
        message="waiting for bullish confirmation",
    )

    price_confirmation = PriceConfirmation(
        state="inside_range",
        price=69597.46,
        confirmation=74050.0,
        invalidation=65618.49,
        message="price is between invalidation and confirmation",
    )

    mtf_alignment = MTFAlignmentResult(
        state="mixed_alignment",
        biases={"1W": "BEARISH", "1D": "BULLISH", "4H": "BULLISH"},
        message="timeframes are mixed",
    )

    result = build_market_context(
        wave_position=wave_position,
        scenario_state=scenario_state,
        price_confirmation=price_confirmation,
        mtf_alignment=mtf_alignment,
    )

    assert result.trend_context == "bullish_rebound_inside_mixed_context"
    assert result.wave_structure == "ABC_CORRECTION"
    assert result.wave_bias == "BULLISH"
    assert result.scenario_state == "waiting_confirmation"
    assert result.price_state == "inside_range"
    assert result.mtf_state == "mixed_alignment"