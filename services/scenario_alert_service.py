from __future__ import annotations

from scenarios.scenario_engine import Scenario
from scenarios.scenario_state_machine import update_scenario_state
from services.alert_state_store import AlertStateStore
from services.notifier import send_notification


def _fmt_value(value) -> str:
    if value is None:
        return "None"
    if isinstance(value, (int, float)):
        rounded = round(float(value), 4)
        text = f"{rounded:.4f}".rstrip("0").rstrip(".")
        return text or "0"
    return str(value)


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
    timeframe: str | None = None,
):
    state = update_scenario_state(scenario, current_price)
    key = _build_scenario_alert_key(symbol, scenario)

    if not store.should_alert(key, state):
        return state

    if state == "CONFIRMED":
        send_notification(
            f"✅ {symbol} Scenario Confirmed\n"
            f"Scenario: {scenario.name}\n"
            f"ราคา: {_fmt_value(current_price)}\n"
            f"Confirm: {_fmt_value(scenario.confirmation)}\n"
            f"SL: {_fmt_value(scenario.stop_loss)}\n"
            f"Targets: {[ _fmt_value(target) for target in scenario.targets ]}",
            timeframe=timeframe,
            symbol=symbol,
        )

    elif state == "INVALIDATED":
        send_notification(
            f"❌ {symbol} Scenario Invalidated\n"
            f"Scenario: {scenario.name}\n"
            f"ราคา: {_fmt_value(current_price)}\n"
            f"Invalidation: {_fmt_value(scenario.invalidation)}",
            timeframe=timeframe,
            symbol=symbol,
        )

    return state
