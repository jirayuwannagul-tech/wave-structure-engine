from analysis.price_level_watcher import Level
from monitor.live_price_monitor import monitor
from services.alert_state_store import AlertStateStore
from services.live_price_monitor import _process_price_update, run_monitor


def test_process_price_update_sends_only_one_notification_per_state(tmp_path, monkeypatch):
    store = AlertStateStore(state_path=str(tmp_path / "alert_state.json"))
    sent = []

    monkeypatch.setattr(
        "services.live_price_monitor.send_notification",
        lambda message: sent.append(message),
    )

    levels = [Level("4H Support", 69266.0, "support")]

    _process_price_update("BTCUSDT", 69180.0, levels, store)
    _process_price_update("BTCUSDT", 69180.0, levels, store)

    assert len(sent) == 1
    assert "4H Support" in sent[0]


def test_run_monitor_refreshes_runtime_levels_between_cycles(tmp_path, monkeypatch):
    monkeypatch.setenv("ALERT_STATE_PATH", str(tmp_path / "alert_state.json"))

    level_sets = [
        [Level("1D Resistance", 74050.0, "resistance")],
        [Level("4H Resistance", 71777.0, "resistance")],
    ]
    load_calls = []
    observed_cycles = []
    timestamps = iter([0.0, 30.0, 61.0])
    prices = iter([70000.0, 70100.0, 70200.0])
    sleeps = []

    def fake_load_runtime_levels(symbol):
        load_calls.append(symbol)
        if len(load_calls) == 1:
            return level_sets[0]
        return level_sets[1]

    def fake_process_price_update(symbol, current_price, levels, store, tolerance=0.002):
        observed_cycles.append(
            {
                "symbol": symbol,
                "price": current_price,
                "levels": [(level.name, level.price) for level in levels],
            }
        )

    monkeypatch.setattr("services.live_price_monitor.load_runtime_levels", fake_load_runtime_levels)
    monkeypatch.setattr("services.live_price_monitor.get_last_price", lambda symbol: next(prices))
    monkeypatch.setattr("services.live_price_monitor._process_price_update", fake_process_price_update)
    monkeypatch.setattr("services.live_price_monitor.time.time", lambda: next(timestamps))
    monkeypatch.setattr("services.live_price_monitor.time.sleep", lambda seconds: sleeps.append(seconds))

    run_monitor(
        symbol="BTCUSDT",
        poll_interval=1.5,
        levels_refresh_interval=60.0,
        max_cycles=3,
    )

    assert load_calls == ["BTCUSDT", "BTCUSDT"]
    assert observed_cycles == [
        {
            "symbol": "BTCUSDT",
            "price": 70000.0,
            "levels": [("1D Resistance", 74050.0)],
        },
        {
            "symbol": "BTCUSDT",
            "price": 70100.0,
            "levels": [("1D Resistance", 74050.0)],
        },
        {
            "symbol": "BTCUSDT",
            "price": 70200.0,
            "levels": [("4H Resistance", 71777.0)],
        },
    ]
    assert sleeps == [1.5, 1.5]


def test_monitor_wrapper_routes_to_service_live_monitor(monkeypatch):
    observed = {}

    monkeypatch.setattr(
        "monitor.live_price_monitor.run_monitor",
        lambda **kwargs: observed.update(kwargs),
    )

    monitor(symbol="ETHUSDT", interval="4h", limit=123, sleep_seconds=7)

    assert observed == {
        "symbol": "ETHUSDT",
        "poll_interval": 7,
    }
