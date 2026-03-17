from __future__ import annotations

import pandas as pd

from services.market_data_sync import sync_market_data, sync_recent_market_data
from storage.wave_repository import WaveRepository


def _sample_df(start: str, periods: int, freq: str) -> pd.DataFrame:
    open_times = pd.date_range(start=start, periods=periods, freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "open_time": open_times,
            "open": [100.0 + idx for idx in range(periods)],
            "high": [101.0 + idx for idx in range(periods)],
            "low": [99.0 + idx for idx in range(periods)],
            "close": [100.5 + idx for idx in range(periods)],
            "volume": [10.0 + idx for idx in range(periods)],
            "close_time": open_times + pd.Timedelta(hours=1),
            "quote_asset_volume": [20.0 + idx for idx in range(periods)],
            "number_of_trades": [5 + idx for idx in range(periods)],
        }
    )


def test_sync_market_data_backfills_csv_and_db(tmp_path, monkeypatch):
    repository = WaveRepository(db_path=str(tmp_path / "wave.db"))
    monkeypatch.setattr(
        "services.market_data_sync._dataset_path",
        lambda symbol, timeframe: tmp_path / f"{symbol}_{timeframe.lower()}.csv",
    )
    monkeypatch.setattr(
        "services.market_data_sync._fetch_full_history",
        lambda symbol, timeframe, start_time: _sample_df("2026-01-01", 3, "1D"),
    )

    summary = sync_market_data(
        symbols=["BTCUSDT"],
        timeframes=["1D"],
        repository=repository,
        start_time=pd.Timestamp("2026-01-01", tz="UTC"),
    )

    item = summary["items"]["BTCUSDT:1D"]
    assert item["rows"] == 3
    assert repository.count_market_candles("BTCUSDT", "1D") == 3
    assert (tmp_path / "BTCUSDT_1d.csv").exists()


def test_sync_recent_market_data_merges_into_existing_csv_and_db(tmp_path, monkeypatch):
    repository = WaveRepository(db_path=str(tmp_path / "wave.db"))
    path = tmp_path / "ETHUSDT_4h.csv"
    _sample_df("2026-01-01", 2, "4h").to_csv(path, index=False)

    monkeypatch.setattr(
        "services.market_data_sync._dataset_path",
        lambda symbol, timeframe: path,
    )
    monkeypatch.setattr(
        "services.market_data_sync._fetch_recent_history",
        lambda symbol, timeframe, lookback_candles=3: _sample_df("2026-01-01 04:00:00+00:00", 2, "4h"),
    )

    summary = sync_recent_market_data(
        symbols=["ETHUSDT"],
        timeframes=["4H"],
        repository=repository,
        lookback_candles=2,
    )

    item = summary["items"]["ETHUSDT:4H"]
    assert item["rows_fetched"] == 2
    assert item["csv_rows_total"] == 3
    assert repository.count_market_candles("ETHUSDT", "4H") == 2


def test_sync_recent_market_data_recovers_from_empty_existing_csv(tmp_path, monkeypatch):
    repository = WaveRepository(db_path=str(tmp_path / "wave.db"))
    path = tmp_path / "DOGEUSDT_1d.csv"
    path.write_text("")

    monkeypatch.setattr(
        "services.market_data_sync._dataset_path",
        lambda symbol, timeframe: path,
    )
    monkeypatch.setattr(
        "services.market_data_sync._fetch_recent_history",
        lambda symbol, timeframe, lookback_candles=3: _sample_df("2026-01-01", 2, "1D"),
    )

    summary = sync_recent_market_data(
        symbols=["DOGEUSDT"],
        timeframes=["1D"],
        repository=repository,
        lookback_candles=2,
    )

    item = summary["items"]["DOGEUSDT:1D"]
    assert item["rows_fetched"] == 2
    assert item["csv_rows_total"] == 2
    assert repository.count_market_candles("DOGEUSDT", "1D") == 2
