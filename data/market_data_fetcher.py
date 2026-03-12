from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import requests


BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/price"


@dataclass
class MarketDataFetcher:
    symbol: str = "BTCUSDT"
    interval: str = "1d"
    limit: int = 500
    timeout: int = 10

    def fetch_ohlcv(self) -> pd.DataFrame:
        params = {
            "symbol": self.symbol.upper(),
            "interval": self.interval,
            "limit": self.limit,
        }

        response = requests.get(
            BINANCE_KLINES_URL,
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()

        raw = response.json()

        columns = [
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_asset_volume",
            "number_of_trades",
            "taker_buy_base_volume",
            "taker_buy_quote_volume",
            "ignore",
        ]

        df = pd.DataFrame(raw, columns=columns)

        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_asset_volume",
            "taker_buy_base_volume",
            "taker_buy_quote_volume",
        ]

        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df["number_of_trades"] = pd.to_numeric(df["number_of_trades"], errors="coerce")
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)

        return df[
            [
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_asset_volume",
                "number_of_trades",
            ]
        ].copy()

    def fetch_latest_price(self) -> float:
        response = requests.get(
            BINANCE_TICKER_URL,
            params={"symbol": self.symbol.upper()},
            timeout=self.timeout,
        )
        response.raise_for_status()

        payload = response.json()
        return float(payload["price"])

    def save_to_csv(self, df: pd.DataFrame, output_path: str | Path) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        return output_path


if __name__ == "__main__":
    fetcher = MarketDataFetcher(symbol="BTCUSDT", interval="1d", limit=200)
    df = fetcher.fetch_ohlcv()
    saved_path = fetcher.save_to_csv(df, "data/BTCUSDT_1d.csv")

    print(df.tail())
    print(f"\nSaved to: {saved_path}")
