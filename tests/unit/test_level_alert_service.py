from analysis.price_level_watcher import Level
from services.level_alert_service import load_runtime_levels
from services.run_level_check_once import run_once
from services.trading_orchestrator import OrchestratorRuntime


def test_load_runtime_levels_uses_orchestrator_runtime(monkeypatch):
    expected_levels = [
        Level("1D Support", 63030.0, "support"),
        Level("1D Resistance", 74050.0, "resistance"),
    ]

    monkeypatch.setattr(
        "services.level_alert_service._load_runtime",
        lambda symbol: OrchestratorRuntime(
            symbol=symbol,
            analyses=[],
            levels=expected_levels,
            scenarios=[],
        ),
    )

    assert load_runtime_levels("BTCUSDT") == expected_levels


def test_run_once_uses_runtime_levels_instead_of_hardcoded_values(monkeypatch):
    observed = {}
    runtime_levels = [Level("4H Resistance", 71777.0, "resistance")]

    def fake_get_last_price(symbol):
        observed["price_symbol"] = symbol
        return 72000.0

    def fake_load_runtime_levels(symbol):
        observed["levels_symbol"] = symbol
        return runtime_levels

    def fake_check_price_and_alert(current_price, levels):
        observed["alert_args"] = (current_price, levels)
        return []

    monkeypatch.setattr("services.run_level_check_once.get_last_price", fake_get_last_price)
    monkeypatch.setattr("services.run_level_check_once.load_runtime_levels", fake_load_runtime_levels)
    monkeypatch.setattr("services.run_level_check_once.check_price_and_alert", fake_check_price_and_alert)

    run_once("BTCUSDT")

    assert observed["price_symbol"] == "BTCUSDT"
    assert observed["levels_symbol"] == "BTCUSDT"
    assert observed["alert_args"] == (72000.0, runtime_levels)
