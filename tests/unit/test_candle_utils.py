import pandas as pd

from data.candle_utils import drop_unclosed_candle


def test_drop_unclosed_candle_removes_last_open_candle():
    now = pd.Timestamp.utcnow()

    df = pd.DataFrame(
        {
            "close_time": [
                now - pd.Timedelta(minutes=10),
                now + pd.Timedelta(minutes=10),
            ],
            "close": [100.0, 101.0],
        }
    )

    result = drop_unclosed_candle(df)

    assert len(result) == 1
    assert float(result.iloc[0]["close"]) == 100.0


def test_drop_unclosed_candle_keeps_all_when_closed():
    now = pd.Timestamp.utcnow()

    df = pd.DataFrame(
        {
            "close_time": [
                now - pd.Timedelta(minutes=20),
                now - pd.Timedelta(minutes=10),
            ],
            "close": [100.0, 101.0],
        }
    )

    result = drop_unclosed_candle(df)

    assert len(result) == 2
    assert float(result.iloc[-1]["close"]) == 101.0