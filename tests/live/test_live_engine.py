import pandas as pd

from live.live_engine import LiveWaveEngine


def test_live_engine_process_dataframe():
    df = pd.read_csv("data/BTCUSDT_1d.csv")

    engine = LiveWaveEngine()
    result = engine.process_dataframe(df)

    assert result is None or "bias" in result