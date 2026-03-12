from __future__ import annotations

import time

from analysis.pivot_detector import detect_pivots
from analysis.wave_detector import detect_latest_abc
from data.market_data_fetcher import MarketDataFetcher
from monitor.wave_state_machine import evaluate_price_vs_c_end


def monitor(symbol: str = "BTCUSDT", interval: str = "1d", limit: int = 200, sleep_seconds: int = 10) -> None:
    while True:
        fetcher = MarketDataFetcher(symbol=symbol, interval=interval, limit=limit)
        df = fetcher.fetch_ohlcv()

        pivots = detect_pivots(df)
        pattern = detect_latest_abc(pivots)

        if pattern is None:
            print("No ABC pattern")
        else:
            current_price = float(df.iloc[-1]["close"])
            state = evaluate_price_vs_c_end(current_price, pattern.c.price)
            print(f"price={current_price} c_end={pattern.c.price} state={state.state}")

        time.sleep(sleep_seconds)


if __name__ == "__main__":
    monitor()