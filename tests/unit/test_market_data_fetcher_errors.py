"""Tests for error handling in MarketDataFetcher."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from data.market_data_fetcher import MarketDataFetcher, _request_with_retry


class TestRequestWithRetry:
    def test_returns_response_on_success(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        with patch("data.market_data_fetcher.requests.get", return_value=mock_resp):
            result = _request_with_retry("https://example.com", {}, 10)
        assert result is mock_resp

    def test_retries_on_connection_error(self):
        good_resp = MagicMock()
        good_resp.raise_for_status.return_value = None
        with patch("data.market_data_fetcher.requests.get") as mock_get, \
             patch("data.market_data_fetcher.time.sleep"):
            mock_get.side_effect = [requests.ConnectionError("down"), good_resp]
            result = _request_with_retry("https://example.com", {}, 10)
        assert result is good_resp
        assert mock_get.call_count == 2

    def test_raises_after_all_retries(self):
        with patch("data.market_data_fetcher.requests.get") as mock_get, \
             patch("data.market_data_fetcher.time.sleep"):
            mock_get.side_effect = requests.ConnectionError("down")
            with pytest.raises(requests.ConnectionError):
                _request_with_retry("https://example.com", {}, 10)
        assert mock_get.call_count == 3


class TestMarketDataFetcherRetry:
    def test_fetch_latest_price_retries_on_error(self):
        good_resp = MagicMock()
        good_resp.raise_for_status.return_value = None
        good_resp.json.return_value = {"price": "83000.0"}

        fetcher = MarketDataFetcher(symbol="BTCUSDT")
        with patch("data.market_data_fetcher.requests.get") as mock_get, \
             patch("data.market_data_fetcher.time.sleep"):
            mock_get.side_effect = [requests.ConnectionError("timeout"), good_resp]
            price = fetcher.fetch_latest_price()

        assert price == 83000.0
        assert mock_get.call_count == 2
