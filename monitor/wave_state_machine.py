from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WaveState:
    state: str
    message: str


def evaluate_price_vs_c_end(current_price: float, c_end: float) -> WaveState:
    if current_price > c_end:
        return WaveState(
            state="impulse_possible",
            message="price is above C end",
        )

    if current_price < c_end:
        return WaveState(
            state="correction_continues",
            message="price is below C end",
        )

    return WaveState(
        state="level_touched",
        message="price is exactly at C end",
    )


if __name__ == "__main__":
    from analysis.pivot_detector import detect_pivots
    from analysis.wave_detector import detect_latest_abc
    from data.market_data_fetcher import MarketDataFetcher

    fetcher = MarketDataFetcher(symbol="BTCUSDT", interval="1d", limit=200)
    df = fetcher.fetch_ohlcv()

    pivots = detect_pivots(df)
    pattern = detect_latest_abc(pivots)

    if pattern is None:
        print("No ABC pattern")
    else:
        current_price = float(df.iloc[-1]["close"])
        state = evaluate_price_vs_c_end(current_price=current_price, c_end=pattern.c.price)
        print(state)