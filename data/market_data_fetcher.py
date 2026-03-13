from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import requests


BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/price"
BINANCE_KLINES_MAX_LIMIT = 1000

_MAX_RETRIES = 3
_RETRY_DELAY = 2.0  # seconds, doubles on each attempt


def _request_with_retry(url: str, params: dict, timeout: int) -> requests.Response:
    """GET request with exponential backoff retry on network/HTTP errors."""
    delay = _RETRY_DELAY
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            if attempt == _MAX_RETRIES:
                raise
            print(f"[market_data_fetcher] attempt {attempt} failed ({exc}), retrying in {delay}s…")
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")  # pragma: no cover


def _interval_to_milliseconds(interval: str) -> int:
    interval = interval.strip().lower()
    if not interval:
        raise ValueError("interval is required")

    unit = interval[-1]
    amount = int(interval[:-1])
    factor = {
        "m": 60_000,
        "h": 3_600_000,
        "d": 86_400_000,
        "w": 604_800_000,
    }.get(unit)

    if factor is None:
        raise ValueError(f"Unsupported Binance interval: {interval}")

    return amount * factor


@dataclass
class MarketDataFetcher:
    symbol: str = "BTCUSDT"
    interval: str = "1d"
    limit: int = 500
    timeout: int = 10

    def _fetch_ohlcv_chunk(
        self,
        limit: int | None = None,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> pd.DataFrame:
        params = {
            "symbol": self.symbol.upper(),
            "interval": self.interval,
            "limit": min(limit or self.limit, BINANCE_KLINES_MAX_LIMIT),
        }
        if start_time_ms is not None:
            params["startTime"] = int(start_time_ms)
        if end_time_ms is not None:
            params["endTime"] = int(end_time_ms)

        response = _request_with_retry(BINANCE_KLINES_URL, params, self.timeout)
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

    def fetch_ohlcv(self) -> pd.DataFrame:
        return self._fetch_ohlcv_chunk()

    def fetch_ohlcv_range(
        self,
        start_time: pd.Timestamp,
        end_time: pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        start_time = pd.Timestamp(start_time)
        if start_time.tzinfo is None:
            start_time = start_time.tz_localize("UTC")
        else:
            start_time = start_time.tz_convert("UTC")

        if end_time is None:
            end_time = pd.Timestamp.now(tz="UTC")
        else:
            end_time = pd.Timestamp(end_time)
            if end_time.tzinfo is None:
                end_time = end_time.tz_localize("UTC")
            else:
                end_time = end_time.tz_convert("UTC")
        interval_ms = _interval_to_milliseconds(self.interval)

        rows: list[pd.DataFrame] = []
        cursor_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        while cursor_ms < end_ms:
            chunk = self._fetch_ohlcv_chunk(
                limit=BINANCE_KLINES_MAX_LIMIT,
                start_time_ms=cursor_ms,
                end_time_ms=end_ms,
            )
            if chunk.empty:
                break

            rows.append(chunk)
            last_open_ms = int(chunk.iloc[-1]["open_time"].timestamp() * 1000)
            next_cursor_ms = last_open_ms + interval_ms
            if next_cursor_ms <= cursor_ms:
                break
            cursor_ms = next_cursor_ms

            if len(chunk) < BINANCE_KLINES_MAX_LIMIT:
                break

        if not rows:
            return self._fetch_ohlcv_chunk(limit=0).iloc[0:0].copy()

        df = pd.concat(rows, ignore_index=True)
        df = df.drop_duplicates(subset=["open_time"]).sort_values("open_time").reset_index(drop=True)
        return df[df["open_time"] >= start_time].copy()

    def fetch_latest_price(self) -> float:
        response = _request_with_retry(
            BINANCE_TICKER_URL,
            params={"symbol": self.symbol.upper()},
            timeout=self.timeout,
        )
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
