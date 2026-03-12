from live.scenario_monitor import ScenarioMonitor


def test_scenario_monitor_update():

    monitor = ScenarioMonitor()

    monitor.update("BULLISH")
    assert monitor.get_bias() == "BULLISH"

    monitor.update("BEARISH")
    assert monitor.get_bias() == "BEARISH"