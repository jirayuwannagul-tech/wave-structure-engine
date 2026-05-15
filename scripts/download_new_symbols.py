#!/usr/bin/env python3
"""Download historical OHLCV data for newly added symbols."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from data.market_data_fetcher import MarketDataFetcher

SYMBOLS = {
    "NEARUSDT": "2020-10-01",
    "TRXUSDT":  "2018-01-01",
    "TONUSDT":  "2023-01-01",
    "ARBUSDT":  "2022-09-01",
    "ATOMUSDT": "2019-04-01",
}
TIMEFRAMES = ["1d", "4h", "1w"]


def main() -> None:
    total = len(SYMBOLS) * len(TIMEFRAMES)
    done = 0

    for symbol, start_date in SYMBOLS.items():
        for interval in TIMEFRAMES:
            done += 1
            path = f"data/{symbol}_{interval}.csv"
            print(f"[{done}/{total}] {symbol} {interval} ...", end=" ", flush=True)
            try:
                fetcher = MarketDataFetcher(symbol=symbol, interval=interval, limit=1000)
                start = pd.Timestamp(start_date, tz="UTC")
                df = fetcher.fetch_ohlcv_range(start_time=start)
                fetcher.save_to_csv(df, path)
                date_from = df.iloc[0]["open_time"].date()
                date_to   = df.iloc[-1]["open_time"].date()
                print(f"OK ({len(df)} candles, {date_from} → {date_to})")
            except Exception as e:
                print(f"FAIL — {e}")

    print("\nDone!")


if __name__ == "__main__":
    main()
