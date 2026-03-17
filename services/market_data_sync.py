from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from data.market_data_fetcher import MarketDataFetcher, _interval_to_milliseconds
from storage.wave_repository import WaveRepository


DEFAULT_SYNC_TIMEFRAMES = ("1W", "1D", "4H")


def _dataset_path(symbol: str, timeframe: str) -> Path:
    return Path(f"data/{symbol.upper()}_{timeframe.lower()}.csv")


def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "open_time" in out.columns:
        out["open_time"] = pd.to_datetime(out["open_time"], utc=True)
    if "close_time" in out.columns:
        out["close_time"] = pd.to_datetime(out["close_time"], utc=True)
    return out.sort_values("open_time").drop_duplicates(subset=["open_time"]).reset_index(drop=True)


def _merge_with_existing_csv(path: Path, df: pd.DataFrame) -> pd.DataFrame:
    if not path.exists():
        return _normalize_dataframe(df)

    try:
        existing = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return _normalize_dataframe(df)

    existing = _normalize_dataframe(existing)
    combined = pd.concat([existing, df], ignore_index=True)
    return _normalize_dataframe(combined)


def _fetch_full_history(symbol: str, timeframe: str, start_time: pd.Timestamp) -> pd.DataFrame:
    fetcher = MarketDataFetcher(symbol=symbol, interval=timeframe.lower(), limit=1000)
    df = fetcher.fetch_ohlcv_range(start_time=start_time, end_time=pd.Timestamp.now(tz="UTC"))
    return _normalize_dataframe(df)


def _fetch_recent_history(symbol: str, timeframe: str, lookback_candles: int = 3) -> pd.DataFrame:
    interval_ms = _interval_to_milliseconds(timeframe.lower())
    start_time = pd.Timestamp.now(tz="UTC") - pd.Timedelta(milliseconds=interval_ms * lookback_candles)
    fetcher = MarketDataFetcher(symbol=symbol, interval=timeframe.lower(), limit=max(lookback_candles + 2, 10))
    df = fetcher.fetch_ohlcv_range(start_time=start_time, end_time=pd.Timestamp.now(tz="UTC"))
    return _normalize_dataframe(df)


def sync_market_data(
    *,
    symbols: list[str],
    timeframes: list[str] | None = None,
    repository: WaveRepository | None = None,
    start_time: pd.Timestamp | None = None,
) -> dict:
    repository = repository or WaveRepository()
    resolved_timeframes = [item.upper() for item in (timeframes or DEFAULT_SYNC_TIMEFRAMES)]
    sync_start = start_time or pd.Timestamp("2018-01-01", tz="UTC")
    results: dict[str, dict] = {}

    for symbol in [item.upper() for item in symbols]:
        for timeframe in resolved_timeframes:
            df = _fetch_full_history(symbol, timeframe, sync_start)
            path = _dataset_path(symbol, timeframe)
            merged = _merge_with_existing_csv(path, df)
            MarketDataFetcher(symbol=symbol, interval=timeframe.lower()).save_to_csv(merged, path)
            upserted = repository.upsert_market_candles(symbol, timeframe, merged)
            results[f"{symbol}:{timeframe}"] = {
                "symbol": symbol,
                "timeframe": timeframe,
                "rows": len(merged),
                "db_rows_upserted": upserted,
                "csv_path": str(path),
                "first_open_time": merged.iloc[0]["open_time"].isoformat() if len(merged) else None,
                "last_open_time": merged.iloc[-1]["open_time"].isoformat() if len(merged) else None,
            }

    return {
        "synced_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "symbols": [item.upper() for item in symbols],
        "timeframes": resolved_timeframes,
        "items": results,
    }


def sync_recent_market_data(
    *,
    symbols: list[str],
    timeframes: list[str] | None = None,
    repository: WaveRepository | None = None,
    lookback_candles: int = 3,
) -> dict:
    repository = repository or WaveRepository()
    resolved_timeframes = [item.upper() for item in (timeframes or DEFAULT_SYNC_TIMEFRAMES)]
    results: dict[str, dict] = {}

    for symbol in [item.upper() for item in symbols]:
        for timeframe in resolved_timeframes:
            df = _fetch_recent_history(symbol, timeframe, lookback_candles=lookback_candles)
            path = _dataset_path(symbol, timeframe)
            merged = _merge_with_existing_csv(path, df)
            MarketDataFetcher(symbol=symbol, interval=timeframe.lower()).save_to_csv(merged, path)
            upserted = repository.upsert_market_candles(symbol, timeframe, df)
            results[f"{symbol}:{timeframe}"] = {
                "symbol": symbol,
                "timeframe": timeframe,
                "rows_fetched": len(df),
                "db_rows_upserted": upserted,
                "csv_rows_total": len(merged),
                "csv_path": str(path),
                "last_open_time": merged.iloc[-1]["open_time"].isoformat() if len(merged) else None,
            }

    return {
        "synced_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "symbols": [item.upper() for item in symbols],
        "timeframes": resolved_timeframes,
        "items": results,
    }
