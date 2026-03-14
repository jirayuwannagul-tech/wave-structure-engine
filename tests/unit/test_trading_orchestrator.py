from analysis.price_level_watcher import Level
from analysis.wave_position import WavePosition
from scenarios.scenario_engine import Scenario
from services.alert_state_store import AlertStateStore
from services.trading_orchestrator import (
    OrchestratorRuntime,
    _build_levels_from_analysis,
    _format_analysis_summary,
    _load_runtime,
    _refresh_runtime,
    process_market_update,
    run_orchestrator,
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
        "position": WavePosition(
            structure="ABC_CORRECTION",
            position="WAVE_C_END",
            bias="BULLISH",
            confidence="medium",
        ),
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

    assert summary.startswith("4H")
    assert "• Structure: ABC_CORRECTION" in summary
    assert "• Current Leg: C" in summary
    assert "• Scenario: Main Bullish" in summary
    assert "• Bias: BULLISH" in summary
    assert "• Setup: Waiting Breakout" in summary
    assert "• Trigger: Above 71777" in summary
    assert "• Entry: 71777" in summary
    assert "• SL: 69266.06" in summary
    assert "• TP1: 75424.57" in summary
    assert "• TP2: 77099.68" in summary
    assert "• TP3: 79230.53" in summary
    assert "RR1:" not in summary
    assert "RR2:" not in summary
    assert "RR3:" not in summary


def test_format_analysis_summary_marks_bearish_setup_as_waiting_breakdown():
    analysis = {
        "timeframe": "1D",
        "current_price": 70165.1,
        "primary_pattern_type": "EXPANDED_FLAT",
        "position": WavePosition(
            structure="EXPANDED_FLAT",
            position="CORRECTION_COMPLETE",
            bias="BEARISH",
            confidence="medium",
        ),
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

    assert "• Setup: Waiting Breakdown" in summary
    assert "• Current Leg: C" in summary
    assert "• Trigger: Below 63030" in summary
    assert "• TP1: 52010" in summary
    assert "RR1:" not in summary


def test_format_analysis_summary_prefers_confirmed_alternate_scenario():
    analysis = {
        "timeframe": "4H",
        "current_price": 71914.27,
        "primary_pattern_type": "ABC_CORRECTION",
        "position": WavePosition(
            structure="ABC_CORRECTION",
            position="WAVE_C_END",
            bias="BULLISH",
            confidence="medium",
        ),
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

    assert summary.startswith("4H")
    assert "• Structure: ABC_CORRECTION" in summary
    assert "• Current Leg: C" in summary
    assert "• Scenario: Alternate Bullish" in summary
    assert "• Bias: BULLISH" in summary
    assert "• Setup: Active" in summary
    assert "• Trigger: Above 70800" in summary
    assert "• TP1: 72394.09" in summary
    assert "• TP2: 72827.6825" in summary
    assert "• TP3: 73379.2376" in summary


def test_process_market_update_refreshes_after_level_break(monkeypatch):
    runtime = OrchestratorRuntime(
        symbol="BTCUSDT",
        analyses=[],
        levels=[Level("4H Resistance", 71777.0, "resistance")],
        scenarios=[],
    )
    store = AlertStateStore()
    notifications = []

    monkeypatch.setattr(
        "services.trading_orchestrator.send_notification",
        lambda message, **kwargs: notifications.append((message, kwargs)),
    )

    result = process_market_update(
        runtime=runtime,
        current_price=72000.0,
        store=store,
    )

    assert result is runtime
    assert notifications == []


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
    result = process_market_update(
        runtime=runtime,
        current_price=71800.0,
        store=store,
    )

    assert result is runtime


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
    assert "🔄 BTCUSDT | Re-analysis Update" in notifications[0][0]
    assert "Reason:" in notifications[0][0]
    assert "• level break: 4H Resistance" in notifications[0][0]
    assert "\n1D\n" in notifications[0][0]
    assert "• Setup: Waiting Breakdown" in notifications[0][0]
    assert "• Entry: 63030" in notifications[0][0]
    assert "• SL: 74050" in notifications[0][0]
    assert "• TP3: 45199.64" in notifications[0][0]
    assert notifications[0][1]["timeframe"] == "1D"
    assert "\n4H\n" in f"\n{notifications[1][0]}\n"
    assert "• Structure: ABC_CORRECTION" in notifications[1][0]
    assert "• Setup: Waiting Breakout" in notifications[1][0]
    assert "• Entry: 71777" in notifications[1][0]
    assert notifications[1][1]["timeframe"] == "4H"


def test_refresh_runtime_keeps_existing_alert_state(monkeypatch):
    runtime = OrchestratorRuntime(
        symbol="BTCUSDT",
        analyses=[],
        levels=[],
        scenarios=[],
    )
    store = AlertStateStore()
    store.set("BTCUSDT:SCENARIO:Main Bearish:BEARISH:63030.0:74050.0", "CONFIRMED")

    refreshed_runtime = OrchestratorRuntime(
        symbol="BTCUSDT",
        analyses=[],
        levels=[],
        scenarios=[],
    )

    monkeypatch.setattr(
        "services.trading_orchestrator._load_runtime",
        lambda symbol: refreshed_runtime,
    )
    monkeypatch.setattr(
        "services.trading_orchestrator.send_notification",
        lambda message, **kwargs: None,
    )

    _refresh_runtime(runtime=runtime, store=store, reason="scenario confirmed: Main Bearish")

    assert store.get("BTCUSDT:SCENARIO:Main Bearish:BEARISH:63030.0:74050.0") == "CONFIRMED"


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
    assert len(notifications) == 1
    assert notifications[0][0].startswith("🎯 BTCUSDT | 4H Entry Triggered")
    assert "• Status: Active" in notifications[0][0]
    assert "• Entry: 100" in notifications[0][0]
    assert notifications[0][1]["timeframe"] == "4H"
    assert notifications[0][1]["include_layout"] is False

    process_market_update(runtime, current_price=111.0, store=AlertStateStore(), repository=repository)

    assert len(notifications) == 2
    assert notifications[1][0].startswith("✅ BTCUSDT | 4H TP1 Hit")
    assert "• Status: Partial TP1" in notifications[1][0]
    assert "• Scenario: Main Bullish" in notifications[1][0]
    assert "• TP1: 110 ✅" in notifications[1][0]
    assert "• TP2: 120" in notifications[1][0]
    assert "1D" not in notifications[1][0]
    assert notifications[1][1]["timeframe"] == "4H"
    assert notifications[1][1]["include_layout"] is False


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

    assert len(notifications) == 3
    assert notifications[0][0].startswith("🎯 BTCUSDT | 4H Entry Triggered")
    assert "• TP1: 110 ✅" in notifications[1][0]
    assert notifications[2][0].startswith("❌ BTCUSDT | 4H Stop Loss Hit")
    assert "• Status: Stopped" in notifications[2][0]
    assert "• SL: 95 ❌" in notifications[2][0]
    assert "• TP1: 110 ✅" in notifications[2][0]
    assert notifications[2][1]["timeframe"] == "4H"


def test_run_orchestrator_once_supports_multiple_symbols(monkeypatch):
    runtimes = {
        "BTCUSDT": OrchestratorRuntime(symbol="BTCUSDT", analyses=[], levels=[], scenarios=[]),
        "ETHUSDT": OrchestratorRuntime(symbol="ETHUSDT", analyses=[], levels=[], scenarios=[]),
    }
    prices = {"BTCUSDT": 70000.0, "ETHUSDT": 3500.0}
    sync_calls = []
    market_sync_calls = []

    class DummyRepository:
        def sync_runtime(self, runtime, current_price=None):
            sync_calls.append((runtime.symbol, current_price))
            return []

    monkeypatch.setattr("services.trading_orchestrator._load_runtime", lambda symbol: runtimes[symbol])
    monkeypatch.setattr("services.trading_orchestrator.get_last_price", lambda symbol: prices[symbol])
    monkeypatch.setattr("services.trading_orchestrator.maybe_run_daily_job", lambda **kwargs: False)
    monkeypatch.setattr(
        "services.trading_orchestrator.sync_recent_market_data",
        lambda **kwargs: market_sync_calls.append(kwargs) or {"items": {}},
    )
    monkeypatch.setattr(
        "services.trading_orchestrator.process_market_update",
        lambda runtime, current_price, store, repository=None, sheets_logger=None: runtime,
    )

    result = run_orchestrator(
        symbol="BTCUSDT",
        symbols=["BTCUSDT", "ETHUSDT"],
        once=True,
        repository=DummyRepository(),
    )

    assert result.symbol == "BTCUSDT"
    assert sync_calls == [("BTCUSDT", None), ("ETHUSDT", None)]
    assert len(market_sync_calls) == 1
    assert market_sync_calls[0]["symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert market_sync_calls[0]["timeframes"] == ["1W", "1D", "4H"]


def test_load_runtime_uses_weekly_manual_context_for_1d_then_1d_context_for_4h(monkeypatch):
    calls = []

    class Position:
        def __init__(self, bias, wave_number):
            self.bias = bias
            self.wave_number = wave_number

    def fake_build_timeframe_analysis(symbol, interval, limit, higher_timeframe_bias=None, higher_timeframe_wave_number=None):
        calls.append((interval, higher_timeframe_bias, higher_timeframe_wave_number))
        interval = interval.lower()
        if interval == "1w":
            return {"timeframe": "1W", "position": Position("BULLISH", "2"), "scenarios": [], "wave_summary": {}}
        if interval == "1d":
            return {"timeframe": "1D", "position": Position("BEARISH", "3"), "scenarios": [], "wave_summary": {}}
        if interval == "4h":
            return {"timeframe": "4H", "position": Position("BEARISH", "C"), "scenarios": [], "wave_summary": {}}
        raise AssertionError(interval)

    class ManualContext:
        bias = "BEARISH"
        wave_number = "5"
        structure = "IMPULSE"
        position = "WAVE_5_COMPLETE"
        symbol = "BTCUSDT"
        timeframe = "1W"
        note = "seed"
        source = "manual"

    monkeypatch.setattr("services.trading_orchestrator.build_timeframe_analysis", fake_build_timeframe_analysis)
    monkeypatch.setattr("services.trading_orchestrator.get_manual_wave_context", lambda symbol, timeframe: ManualContext())

    runtime = _load_runtime("BTCUSDT", retries=1)

    assert runtime.symbol == "BTCUSDT"
    assert calls == [
        ("1w", None, None),
        ("1d", "BEARISH", "5"),
        ("4h", "BEARISH", "3"),
    ]
    assert runtime.analyses[0]["higher_timeframe_context"]["timeframe"] == "1W"
    assert runtime.analyses[0]["higher_timeframe_context"]["bias"] == "BEARISH"
    assert runtime.analyses[0]["higher_timeframe_context"]["wave_number"] == "5"
    assert runtime.analyses[1]["higher_timeframe_context"]["timeframe"] == "1D"
    assert runtime.analyses[1]["higher_timeframe_context"]["wave_number"] == "3"
