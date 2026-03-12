from scenarios.scenario_engine import Scenario
from services.alert_state_store import AlertStateStore
from services.scenario_alert_service import check_scenario_and_alert


def test_check_scenario_and_alert_uses_unique_key_per_level(monkeypatch):
    store = AlertStateStore()
    sent = []

    scenario_1d = Scenario(
        name="Main Bullish",
        condition="price breaks above 74050.0",
        interpretation="daily breakout",
        target="move higher",
        bias="BULLISH",
        invalidation=63030.0,
        confirmation=74050.0,
        stop_loss=63030.0,
        targets=[76000.0],
    )
    scenario_4h = Scenario(
        name="Main Bullish",
        condition="price breaks above 71777.0",
        interpretation="4h breakout",
        target="move higher",
        bias="BULLISH",
        invalidation=69266.06,
        confirmation=71777.0,
        stop_loss=69266.06,
        targets=[75424.57],
    )

    monkeypatch.setattr(
        "services.scenario_alert_service.send_notification",
        lambda message, **kwargs: sent.append((message, kwargs)),
    )

    state_1d = check_scenario_and_alert(
        scenario=scenario_1d,
        current_price=74100.0,
        store=store,
        symbol="BTCUSDT",
    )
    state_4h = check_scenario_and_alert(
        scenario=scenario_4h,
        current_price=71800.0,
        store=store,
        symbol="BTCUSDT",
    )

    assert state_1d == "CONFIRMED"
    assert state_4h == "CONFIRMED"
    assert len(sent) == 2
    assert sent[0][1]["timeframe"] is None
    assert sent[1][1]["timeframe"] is None
