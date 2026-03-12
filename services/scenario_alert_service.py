from __future__ import annotations

from scenarios.scenario_engine import Scenario
from scenarios.scenario_state_machine import update_scenario_state
from services.alert_state_store import AlertStateStore
from services.notifier import send_notification


def _build_scenario_alert_key(symbol: str, scenario: Scenario) -> str:
    return (
        f"{symbol}:SCENARIO:{scenario.name}:"
        f"{scenario.bias}:{scenario.confirmation}:{scenario.invalidation}"
    )


def check_scenario_and_alert(
    scenario: Scenario,
    current_price: float,
    store: AlertStateStore,
    symbol: str = "BTCUSDT",
):
    state = update_scenario_state(scenario, current_price)
    key = _build_scenario_alert_key(symbol, scenario)

    if not store.should_alert(key, state):
        return state

    if state == "CONFIRMED":
        send_notification(
            f"✅ {symbol} Scenario Confirmed\n"
            f"Scenario: {scenario.name}\n"
            f"ราคา: {current_price}\n"
            f"Confirm: {scenario.confirmation}\n"
            f"SL: {scenario.stop_loss}\n"
            f"Targets: {scenario.targets}"
        )

    elif state == "INVALIDATED":
        send_notification(
            f"❌ {symbol} Scenario Invalidated\n"
            f"Scenario: {scenario.name}\n"
            f"ราคา: {current_price}\n"
            f"Invalidation: {scenario.invalidation}"
        )

    return state
