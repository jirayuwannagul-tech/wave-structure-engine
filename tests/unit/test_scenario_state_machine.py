from scenarios.scenario_engine import Scenario
from scenarios.scenario_state_machine import update_scenario_state


def test_bullish_scenario_waiting_confirmation():
    scenario = Scenario(
        name="Main Bullish",
        condition="price holds above 65618.49",
        interpretation="correction likely finished",
        target="move toward 74050.0 then 74050.0",
        bias="BULLISH",
        invalidation=65618.49,
        confirmation=74050.0,
        stop_loss=65618.49,
        targets=[74050.0, 74050.0, 76271.5],
    )

    state = update_scenario_state(scenario, 70000.0)
    assert state == "WAITING_CONFIRMATION"


def test_bullish_scenario_confirmed():
    scenario = Scenario(
        name="Main Bullish",
        condition="price holds above 65618.49",
        interpretation="correction likely finished",
        target="move toward 74050.0 then 74050.0",
        bias="BULLISH",
        invalidation=65618.49,
        confirmation=74050.0,
        stop_loss=65618.49,
        targets=[74050.0, 74050.0, 76271.5],
    )

    state = update_scenario_state(scenario, 74500.0)
    assert state == "CONFIRMED"


def test_bullish_scenario_invalidated():
    scenario = Scenario(
        name="Main Bullish",
        condition="price holds above 65618.49",
        interpretation="correction likely finished",
        target="move toward 74050.0 then 74050.0",
        bias="BULLISH",
        invalidation=65618.49,
        confirmation=74050.0,
        stop_loss=65618.49,
        targets=[74050.0, 74050.0, 76271.5],
    )

    state = update_scenario_state(scenario, 65000.0)
    assert state == "INVALIDATED"