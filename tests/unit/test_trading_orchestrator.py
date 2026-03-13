from analysis.price_level_watcher import Level
from scenarios.scenario_engine import Scenario
from services.alert_state_store import AlertStateStore
from services.trading_orchestrator import (
    OrchestratorRuntime,
    _build_levels_from_analysis,
    _format_analysis_summary,
    _refresh_runtime,
    process_market_update,
)
from storage.wave_repository import WaveRepository


def test_build_levels_from_analysis():
    analysis = {
        "timeframe": "4H",
        "wave_summary": {
            "confirm": 71777.0,
            "stop_loss": 69266.06,
        },
    }

    levels = _build_levels_from_analysis(analysis)

    assert len(levels) == 2
    assert levels[0] == Level("4H Support", 69266.06, "support")
    assert levels[1] == Level("4H Resistance", 71777.0, "resistance")


def test_format_analysis_summary_includes_entry_sl_and_targets():
    analysis = {
        "timeframe": "4H",
        "current_price": 70000.0,
        "primary_pattern_type": "ABC_CORRECTION",
        "wave_summary": {
            "confirm": 71777.0,
            "stop_loss": 69266.06,
            "targets": [75424.57, 77099.68, 79230.53],
        },
        "scenarios": [
            Scenario(
                name="Main Bullish",
                condition="price holds above 69266.06",
                interpretation="correction likely finished",
                target="move higher",
                bias="BULLISH",
                invalidation=69266.06,
                confirmation=71777.0,
                stop_loss=69266.06,
                targets=[75424.57, 77099.68, 79230.53],
            )
        ],
    }

    summary = _format_analysis_summary(analysis)

    assert "4H | ABC_CORRECTION | Main Bullish" in summary
    assert "Bias: BULLISH" in summary
    assert "Setup: WAITING_BREAKOUT" in summary
    assert "Trigger: Above 71777" in summary
    assert "Entry: 71777" in summary
    assert "SL: 69266.06" in summary
    assert "TP1: 75424.57" in summary
    assert "TP2: 77099.68" in summary
    assert "TP3: 79230.53" in summary
    assert "RR1:" not in summary
    assert "RR2:" not in summary
    assert "RR3:" not in summary


def test_format_analysis_summary_marks_bearish_setup_as_waiting_breakdown():
    analysis = {
        "timeframe": "1D",
        "current_price": 70165.1,
        "primary_pattern_type": "EXPANDED_FLAT",
        "wave_summary": {},
        "scenarios": [
            Scenario(
                name="Main Bearish",
                condition="price breaks below 63030.0",
                interpretation="correction likely finished",
                target="move lower",
                bias="BEARISH",
                invalidation=74050.0,
                confirmation=63030.0,
                stop_loss=74050.0,
                targets=[52010.0, 49012.56, 45199.64],
            )
        ],
    }

    summary = _format_analysis_summary(analysis)

    assert "Setup: WAITING_BREAKDOWN" in summary
    assert "Trigger: Below 63030" in summary
    assert "TP1: 52010" in summary
    assert "RR1:" not in summary


def test_format_analysis_summary_prefers_confirmed_alternate_scenario():
    analysis = {
        "timeframe": "4H",
        "current_price": 71914.27,
        "primary_pattern_type": "ABC_CORRECTION",
        "wave_summary": {},
        "scenarios": [
            Scenario(
                name="Main Bearish",
                condition="price breaks below 69205.91",
                interpretation="correction likely finished",
                target="move lower",
                bias="BEARISH",
                invalidation=70800.0,
                confirmation=69205.91,
                stop_loss=70800.0,
                targets=[67611.82, 67178.23, 66626.67],
            ),
            Scenario(
                name="Alternate Bullish",
                condition="price breaks above 70800.0",
                interpretation="bearish count weakens, upside continuation possible",
                target="look for higher high structure",
                bias="BULLISH",
                invalidation=69205.91,
                confirmation=70800.0,
                stop_loss=69205.91,
                targets=[],
            ),
        ],
    }

    summary = _format_analysis_summary(analysis)

    assert "4H | ABC_CORRECTION | Alternate Bullish" in summary
    assert "Bias: BULLISH" in summary
    assert "Setup: ACTIVE" in summary
    assert "Trigger: Above 70800" in summary


def test_process_market_update_refreshes_after_level_break(monkeypatch):
    runtime = OrchestratorRuntime(
        symbol="BTCUSDT",
        analyses=[],
        levels=[Level("4H Resistance", 71777.0, "resistance")],
        scenarios=[],
    )
    store = AlertStateStore()
    notifications = []
    refreshed_runtime = OrchestratorRuntime(
        symbol="BTCUSDT",
        analyses=[{"timeframe": "4H", "wave_summary": {}}],
        levels=[],
        scenarios=[],
    )

    monkeypatch.setattr(
        "services.trading_orchestrator.send_notification",
        lambda message, **kwargs: notifications.append((message, kwargs)),
    )
    monkeypatch.setattr(
        "services.trading_orchestrator._refresh_runtime",
        lambda runtime, store, reason, repository=None, current_price=None, sheets_logger=None: refreshed_runtime,
    )

    result = process_market_update(
        runtime=runtime,
        current_price=72000.0,
        store=store,
    )

    assert result is refreshed_runtime
    assert notifications == [
        (
            "🚨 BTCUSDT BREAK 4H Resistance (71777)\nราคาปัจจุบัน: 72000",
            {"timeframe": "4H"},
        )
    ]


def test_process_market_update_refreshes_after_scenario_confirmation(monkeypatch):
    runtime = OrchestratorRuntime(
        symbol="BTCUSDT",
        analyses=[],
        levels=[],
        scenarios=[
            Scenario(
                name="Main Bullish",
                condition="price breaks above 71777.0",
                interpretation="breakout",
                target="move higher",
                bias="BULLISH",
                invalidation=69266.06,
                confirmation=71777.0,
                stop_loss=69266.06,
                targets=[75424.57],
            )
        ],
    )
    store = AlertStateStore()
    refreshed_runtime = OrchestratorRuntime(
        symbol="BTCUSDT",
        analyses=[{"timeframe": "1D", "wave_summary": {}}],
        levels=[],
        scenarios=[],
    )

    monkeypatch.setattr(
        "services.trading_orchestrator.check_scenario_and_alert",
        lambda scenario, current_price, store, symbol, timeframe=None: "CONFIRMED",
    )
    monkeypatch.setattr(
        "services.trading_orchestrator._refresh_runtime",
        lambda runtime, store, reason, repository=None, current_price=None, sheets_logger=None: refreshed_runtime,
    )

    result = process_market_update(
        runtime=runtime,
        current_price=71800.0,
        store=store,
    )

    assert result is refreshed_runtime


def test_refresh_runtime_notification_summarizes_trade_levels(monkeypatch):
    runtime = OrchestratorRuntime(
        symbol="BTCUSDT",
        analyses=[],
        levels=[],
        scenarios=[],
    )
    store = AlertStateStore()
    notifications = []
    refreshed_runtime = OrchestratorRuntime(
        symbol="BTCUSDT",
        analyses=[
            {
                "timeframe": "1D",
                "current_price": 70165.1,
                "primary_pattern_type": "EXPANDED_FLAT",
                "wave_summary": {},
                "scenarios": [
                    Scenario(
                        name="Main Bearish",
                        condition="price breaks below 63030.0",
                        interpretation="correction likely finished",
                        target="move lower",
                        bias="BEARISH",
                        invalidation=74050.0,
                        confirmation=63030.0,
                        stop_loss=74050.0,
                        targets=[52010.0, 49012.56, 45199.64],
                    )
                ],
            },
            {
                "timeframe": "4H",
                "current_price": 70000.0,
                "primary_pattern_type": "ABC_CORRECTION",
                "wave_summary": {},
                "scenarios": [
                    Scenario(
                        name="Main Bullish",
                        condition="price holds above 69266.06",
                        interpretation="correction likely finished",
                        target="move higher",
                        bias="BULLISH",
                        invalidation=69266.06,
                        confirmation=71777.0,
                        stop_loss=69266.06,
                        targets=[75424.57, 77099.68, 79230.53],
                    )
                ],
            },
        ],
        levels=[],
        scenarios=[],
    )

    monkeypatch.setattr(
        "services.trading_orchestrator._load_runtime",
        lambda symbol: refreshed_runtime,
    )
    monkeypatch.setattr(
        "services.trading_orchestrator.send_notification",
        lambda message, **kwargs: notifications.append((message, kwargs)),
    )

    result = _refresh_runtime(runtime=runtime, store=store, reason="level break: 4H Resistance")

    assert result is refreshed_runtime
    assert len(notifications) == 2
    assert "Reason: level break: 4H Resistance" in notifications[0][0]
    assert "1D | EXPANDED_FLAT | Main Bearish" in notifications[0][0]
    assert "Setup: WAITING_BREAKDOWN" in notifications[0][0]
    assert "Entry: 63030" in notifications[0][0]
    assert "SL: 74050" in notifications[0][0]
    assert "TP3: 45199.64" in notifications[0][0]
    assert notifications[0][1]["timeframe"] == "1D"
    assert "4H | ABC_CORRECTION | Main Bullish" in notifications[1][0]
    assert "Setup: WAITING_BREAKOUT" in notifications[1][0]
    assert "Entry: 71777" in notifications[1][0]
    assert notifications[1][1]["timeframe"] == "4H"


def test_process_market_update_notifies_tp_event_for_single_timeframe(tmp_path, monkeypatch):
    repository = WaveRepository(db_path=str(tmp_path / "wave.db"))
    analysis = {
        "symbol": "BTCUSDT",
        "timeframe": "4H",
        "primary_pattern_type": "ABC_CORRECTION",
        "current_price": 99.0,
        "position": None,
        "scenarios": [
            Scenario(
                name="Main Bullish",
                condition="test",
                interpretation="test",
                target="test",
                bias="BULLISH",
                invalidation=95.0,
                confirmation=100.0,
                stop_loss=95.0,
                targets=[110.0, 120.0, 130.0],
            )
        ],
        "wave_summary": {},
    }
    runtime = OrchestratorRuntime(
        symbol="BTCUSDT",
        analyses=[analysis],
        levels=[],
        scenarios=[],
    )
    repository.sync_runtime(runtime, current_price=99.0)
    notifications = []
    monkeypatch.setattr(
        "services.trading_orchestrator.send_notification",
        lambda message, **kwargs: notifications.append((message, kwargs)),
    )

    process_market_update(runtime, current_price=100.5, store=AlertStateStore(), repository=repository)
    assert notifications == []

    process_market_update(runtime, current_price=111.0, store=AlertStateStore(), repository=repository)

    assert len(notifications) == 1
    assert notifications[0][0].startswith("4H")
    assert "status: PARTIAL_TP1" in notifications[0][0]
    assert "scenario: Main Bullish" in notifications[0][0]
    assert "TP1: 110 ✅" in notifications[0][0]
    assert "TP2: 120" in notifications[0][0]
    assert "1D" not in notifications[0][0]
    assert notifications[0][1]["timeframe"] == "4H"
    assert notifications[0][1]["include_layout"] is False


def test_process_market_update_notifies_stop_after_tp1(tmp_path, monkeypatch):
    repository = WaveRepository(db_path=str(tmp_path / "wave.db"))
    analysis = {
        "symbol": "BTCUSDT",
        "timeframe": "4H",
        "primary_pattern_type": "ABC_CORRECTION",
        "current_price": 99.0,
        "position": None,
        "scenarios": [
            Scenario(
                name="Main Bullish",
                condition="test",
                interpretation="test",
                target="test",
                bias="BULLISH",
                invalidation=95.0,
                confirmation=100.0,
                stop_loss=95.0,
                targets=[110.0, 120.0, 130.0],
            )
        ],
        "wave_summary": {},
    }
    runtime = OrchestratorRuntime(
        symbol="BTCUSDT",
        analyses=[analysis],
        levels=[],
        scenarios=[],
    )
    repository.sync_runtime(runtime, current_price=99.0)
    notifications = []
    monkeypatch.setattr(
        "services.trading_orchestrator.send_notification",
        lambda message, **kwargs: notifications.append((message, kwargs)),
    )

    process_market_update(runtime, current_price=100.5, store=AlertStateStore(), repository=repository)
    process_market_update(runtime, current_price=111.0, store=AlertStateStore(), repository=repository)
    process_market_update(runtime, current_price=94.0, store=AlertStateStore(), repository=repository)

    assert len(notifications) == 2
    assert "TP1: 110 ✅" in notifications[0][0]
    assert notifications[1][0].startswith("4H")
    assert "status: STOPPED" in notifications[1][0]
    assert "SL: 95 ❌" in notifications[1][0]
    assert "TP1: 110 ✅" in notifications[1][0]
    assert notifications[1][1]["timeframe"] == "4H"
