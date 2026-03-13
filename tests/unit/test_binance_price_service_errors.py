"""Tests for error handling in binance_price_service."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from services.binance_price_service import get_last_price


class TestGetLastPriceRetry:
    def test_returns_price_on_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"price": "83500.0"}
        with patch("services.binance_price_service.requests.get", return_value=mock_resp):
            price = get_last_price("BTCUSDT")
        assert price == 83500.0

    def test_retries_on_connection_error_then_succeeds(self):
        good_resp = MagicMock()
        good_resp.json.return_value = {"price": "83500.0"}

        with patch("services.binance_price_service.requests.get") as mock_get, \
             patch("services.binance_price_service.time.sleep"):
            mock_get.side_effect = [
                requests.ConnectionError("timeout"),
                good_resp,
            ]
            price = get_last_price("BTCUSDT")

        assert price == 83500.0
        assert mock_get.call_count == 2

    def test_raises_after_max_retries_exhausted(self):
        with patch("services.binance_price_service.requests.get") as mock_get, \
             patch("services.binance_price_service.time.sleep"):
            mock_get.side_effect = requests.ConnectionError("no network")
            with pytest.raises(requests.ConnectionError):
                get_last_price("BTCUSDT")

        assert mock_get.call_count == 3  # _MAX_RETRIES

    def test_raises_on_http_error_after_retries(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("503")

        with patch("services.binance_price_service.requests.get", return_value=mock_resp), \
             patch("services.binance_price_service.time.sleep"):
            with pytest.raises(requests.HTTPError):
                get_last_price("BTCUSDT")
