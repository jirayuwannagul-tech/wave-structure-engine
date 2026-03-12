from __future__ import annotations

from dataclasses import dataclass

from analysis.wave_position import WavePosition
from monitor.mtf_alignment import MTFAlignmentResult
from monitor.price_confirmation import PriceConfirmation
from state.scenario_state_machine import ScenarioState


@dataclass
class MarketContext:
    trend_context: str
    wave_structure: str
    wave_bias: str
    scenario_state: str
    price_state: str
    mtf_state: str
    summary: str


def build_market_context(
    wave_position: WavePosition,
    scenario_state: ScenarioState,
    price_confirmation: PriceConfirmation,
    mtf_alignment: MTFAlignmentResult,
) -> MarketContext:
    trend_context = "neutral"

    if mtf_alignment.state == "full_bullish_alignment":
        trend_context = "bullish_trend"
    elif mtf_alignment.state == "full_bearish_alignment":
        trend_context = "bearish_trend"
    elif wave_position.bias == "BULLISH":
        trend_context = "bullish_rebound_inside_mixed_context"
    elif wave_position.bias == "BEARISH":
        trend_context = "bearish_pullback_inside_mixed_context"

    summary = (
        f"{wave_position.structure} | "
        f"bias={wave_position.bias} | "
        f"scenario={scenario_state.state} | "
        f"price={price_confirmation.state} | "
        f"mtf={mtf_alignment.state}"
    )

    return MarketContext(
        trend_context=trend_context,
        wave_structure=wave_position.structure,
        wave_bias=wave_position.bias,
        scenario_state=scenario_state.state,
        price_state=price_confirmation.state,
        mtf_state=mtf_alignment.state,
        summary=summary,
    )


if __name__ == "__main__":
    from analysis.wave_position import WavePosition
    from monitor.mtf_alignment import MTFAlignmentResult
    from monitor.price_confirmation import PriceConfirmation
    from state.scenario_state_machine import ScenarioState

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

    print(build_market_context(
        wave_position=wave_position,
        scenario_state=scenario_state,
        price_confirmation=price_confirmation,
        mtf_alignment=mtf_alignment,
    ))