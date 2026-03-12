from __future__ import annotations

from scenarios.scenario_engine import Scenario


def update_scenario_state(scenario: Scenario, current_price: float) -> str:
    if scenario.bias == "BULLISH":
        if scenario.invalidation is not None and current_price < scenario.invalidation:
            return "INVALIDATED"
        if scenario.confirmation is not None and current_price >= scenario.confirmation:
            return "CONFIRMED"
        return "WAITING_CONFIRMATION"

    if scenario.bias == "BEARISH":
        if scenario.invalidation is not None and current_price > scenario.invalidation:
            return "INVALIDATED"
        if scenario.confirmation is not None and current_price <= scenario.confirmation:
            return "CONFIRMED"
        return "WAITING_CONFIRMATION"

    return "UNKNOWN"