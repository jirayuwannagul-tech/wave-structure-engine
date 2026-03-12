from core.engine import run_multi_timeframe


def test_run_multi_timeframe_returns_combined_report(monkeypatch):
    sample_report = "Symbol: BTCUSDT\nTimeframe: TEST"

    def fake_run(symbol, interval, limit):
        return sample_report + f"\n{interval}"

    monkeypatch.setattr("core.engine.run_single_timeframe", fake_run)

    result = run_multi_timeframe("BTCUSDT")

    assert isinstance(result, str)
    assert result.count("Symbol: BTCUSDT") == 2
    assert "1d" in result
    assert "4h" in result