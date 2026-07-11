from __future__ import annotations

import pandas as pd


def drop_unclosed_candle(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove the last candle if it has not closed yet.
    """
    if df.empty:
        return df

    now = pd.Timestamp.now("UTC")

    last_close = pd.to_datetime(df.iloc[-1]["close_time"])

    if last_close > now:
        return df.iloc[:-1].copy()

    return df.copy()