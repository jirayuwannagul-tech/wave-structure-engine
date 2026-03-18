import core.engine as engine


def test_run_single_timeframe_returns_report(monkeypatch):
    sample_report = """Symbol: BTCUSDT
Timeframe: 1D

ABC structure detected:
A = 63030.0
B = 74050.0
C = 65618.49
"""

    monkeypatch.setattr(engine, "run_single_timeframe", lambda symbol, interval, limit=200: sample_report)

    result = engine.run_single_timeframe("BTCUSDT", "1d", 200)

    assert isinstance(result, str)
    assert "Symbol: BTCUSDT" in result