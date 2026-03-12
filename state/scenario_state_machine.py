from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from scenarios.scenario_engine import Scenario


@dataclass
class ScenarioState:
    state: str
    active_scenario: Optional[str]
    message: str


def evaluate_scenario_state(
    price: float,
    main_scenario: Scenario,
) -> ScenarioState:
    if main_scenario.bias == "BULLISH":
        if main_scenario.invalidation and price < main_scenario.invalidation:
            return ScenarioState(
                state="invalidated",
                active_scenario=None,
                message="bullish scenario invalidated",
            )

        if main_scenario.confirmation and price > main_scenario.confirmation:
            return ScenarioState(
                state="bullish_confirmed",
                active_scenario=main_scenario.name,
                message="bullish continuation confirmed",
            )

        return ScenarioState(
            state="waiting_confirmation",
            active_scenario=main_scenario.name,
            message="waiting for bullish confirmation",
        )

    if main_scenario.bias == "BEARISH":
        if main_scenario.invalidation and price > main_scenario.invalidation:
            return ScenarioState(
                state="invalidated",
                active_scenario=None,
                message="bearish scenario invalidated",
            )

        if main_scenario.confirmation and price < main_scenario.confirmation:
            return ScenarioState(
                state="bearish_confirmed",
                active_scenario=main_scenario.name,
                message="bearish continuation confirmed",
            )

        return ScenarioState(
            state="waiting_confirmation",
            active_scenario=main_scenario.name,
            message="waiting for bearish confirmation",
        )

    return ScenarioState(
        state="unknown",
        active_scenario=None,
        message="scenario unclear",
    )


if __name__ == "__main__":
    from scenarios.scenario_engine import Scenario

    scenario = Scenario(
        name="Main Bullish",
        condition="price holds above 65618",
        interpretation="correction finished",
        target="74050",
        bias="BULLISH",
        invalidation=65618,
        confirmation=74050,
    )

    price = 70000

    print(evaluate_scenario_state(price, scenario))