"""Integration-style test: Binance client + recorded-style response (no real network)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from execution.models import ExecutionConfig
from execution.binance_futures_client import BinanceFuturesClient


@pytest.fixture
def cfg():
    return ExecutionConfig(
        enabled=True,
        live_order_enabled=True,
        use_testnet=True,
        api_key="k",
        api_secret="secretsecretsecretsecretsecret12",
        risk_per_trade=0.01,
        tp1_size_pct=0.4,
        tp2_size_pct=0.3,
        tp3_size_pct=0.3,
    )


def test_query_order_matches_recorded_fixture_shape(cfg):
    fixture = Path(__file__).resolve().parent.parent / "fixtures" / "binance_query_order_filled.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=payload)

    with patch("execution.binance_futures_client.requests.request", return_value=mock_resp):
        client = BinanceFuturesClient(cfg)
        out = client.query_order(symbol="BTCUSDT", order_id=int(payload["orderId"]))

    assert out.get("status") == "FILLED"
    mock_resp.raise_for_status.assert_called_once()


def test_get_account_balance_delegates_to_balance(cfg):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=[{"asset": "USDT", "availableBalance": "123.45"}])

    with patch("execution.binance_futures_client.requests.request", return_value=mock_resp):
        client = BinanceFuturesClient(cfg)
        assert client.get_account_balance() == [{"asset": "USDT", "availableBalance": "123.45"}]
