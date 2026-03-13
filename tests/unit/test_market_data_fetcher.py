import pandas as pd

from data.market_data_fetcher import MarketDataFetcher, _interval_to_milliseconds


class DummyResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_fetch_ohlcv_returns_dataframe(monkeypatch):
    sample_payload = [
        [
            1704067200000,
            "100.0",
            "110.0",
            "90.0",
            "105.0",
            "1000.0",
            1704153599999,
            "100000.0",
            123,
            "500.0",
            "50000.0",
            "0",
        ]
    ]

    def fake_get(*args, **kwargs):
        return DummyResponse(sample_payload)

    monkeypatch.setattr("data.market_data_fetcher.requests.get", fake_get)

    fetcher = MarketDataFetcher(symbol="BTCUSDT", interval="1d", limit=1)
    df = fetcher.fetch_ohlcv()

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert float(df.iloc[0]["open"]) == 100.0
    assert float(df.iloc[0]["high"]) == 110.0
    assert float(df.iloc[0]["low"]) == 90.0
    assert float(df.iloc[0]["close"]) == 105.0
    assert float(df.iloc[0]["volume"]) == 1000.0
    assert int(df.iloc[0]["number_of_trades"]) == 123


def test_fetch_latest_price_returns_float(monkeypatch):
    def fake_get(*args, **kwargs):
        return DummyResponse({"symbol": "BTCUSDT", "price": "123456.78"})

    monkeypatch.setattr("data.market_data_fetcher.requests.get", fake_get)

    fetcher = MarketDataFetcher(symbol="BTCUSDT", interval="1d", limit=1)

    assert fetcher.fetch_latest_price() == 123456.78


def test_save_to_csv_creates_file(tmp_path):
    fetcher = MarketDataFetcher(symbol="BTCUSDT", interval="1d", limit=1)

    df = pd.DataFrame(
        {
            "open_time": ["2026-01-01"],
            "open": [100.0],
            "high": [110.0],
            "low": [90.0],
            "close": [105.0],
            "volume": [1000.0],
            "close_time": ["2026-01-01"],
            "quote_asset_volume": [100000.0],
            "number_of_trades": [123],
        }
    )

    output_path = tmp_path / "BTCUSDT_1d.csv"
    saved = fetcher.save_to_csv(df, output_path)

    assert saved.exists()
    loaded = pd.read_csv(saved)
    assert len(loaded) == 1
    assert float(loaded.iloc[0]["close"]) == 105.0


def test_interval_to_milliseconds_supports_daily_and_4h():
    assert _interval_to_milliseconds("1d") == 86_400_000
    assert _interval_to_milliseconds("4h") == 14_400_000


def test_fetch_ohlcv_range_paginates(monkeypatch):
    first_payload = [
        [
            1704067200000,
            "100.0",
            "110.0",
            "90.0",
            "105.0",
            "1000.0",
            1704153599999,
            "100000.0",
            123,
            "500.0",
            "50000.0",
            "0",
        ]
    ]
    second_payload = [
        [
            1704153600000,
            "105.0",
            "112.0",
            "95.0",
            "108.0",
            "1200.0",
            1704239999999,
            "120000.0",
            124,
            "600.0",
            "60000.0",
            "0",
        ]
    ]

    responses = [DummyResponse(first_payload), DummyResponse(second_payload), DummyResponse([])]

    def fake_request(*args, **kwargs):
        return responses.pop(0) if responses else DummyResponse([])

    monkeypatch.setattr("data.market_data_fetcher.requests.get", fake_request)
    monkeypatch.setattr("data.market_data_fetcher.BINANCE_KLINES_MAX_LIMIT", 1)

    fetcher = MarketDataFetcher(symbol="BTCUSDT", interval="1d", limit=1)
    start = pd.Timestamp("2024-01-01T00:00:00Z")
    end = pd.Timestamp("2024-01-03T00:00:00Z")
    df = fetcher.fetch_ohlcv_range(start, end)

    assert len(df) == 2
    assert float(df.iloc[1]["close"]) == 108.0
