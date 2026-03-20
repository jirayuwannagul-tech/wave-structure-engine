"""Integration-style test: Binance client + recorded-style response (no real network)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

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


def test_query_order_falls_back_to_algo_endpoint(cfg):
    err_resp = MagicMock()
    err_resp.status_code = 400
    err_resp.json.return_value = {"code": -2013, "msg": "Order does not exist"}
    regular_resp = MagicMock()
    regular_resp.raise_for_status.side_effect = requests.HTTPError(response=err_resp)

    algo_payload = {
        "algoId": 77,
        "clientAlgoId": "E77SL",
        "algoType": "CONDITIONAL",
        "orderType": "STOP_MARKET",
        "symbol": "BTCUSDT",
        "side": "SELL",
        "positionSide": "BOTH",
        "quantity": "0.01",
        "algoStatus": "TRIGGERED",
        "actualOrderId": "991",
        "actualPrice": "49000.0",
        "triggerPrice": "49000.0",
        "triggerTime": 1750514941540,
        "closePosition": True,
        "reduceOnly": False,
    }
    algo_resp = MagicMock()
    algo_resp.raise_for_status = MagicMock()
    algo_resp.json = MagicMock(return_value=algo_payload)

    with patch(
        "execution.binance_futures_client.requests.request",
        side_effect=[regular_resp, algo_resp],
    ) as req:
        client = BinanceFuturesClient(cfg)
        out = client.query_order(symbol="BTCUSDT", order_id=77)

    assert out["status"] == "FILLED"
    assert out["orderId"] == 77
    assert out["clientOrderId"] == "E77SL"
    assert req.call_count == 2


def test_get_open_orders_merges_algo_orders(cfg):
    regular_resp = MagicMock()
    regular_resp.raise_for_status = MagicMock()
    regular_resp.json = MagicMock(
        return_value=[
            {
                "orderId": 11,
                "symbol": "BTCUSDT",
                "type": "LIMIT",
                "status": "NEW",
                "clientOrderId": "REG1",
            }
        ]
    )
    algo_resp = MagicMock()
    algo_resp.raise_for_status = MagicMock()
    algo_resp.json = MagicMock(
        return_value=[
            {
                "algoId": 22,
                "clientAlgoId": "ALG1",
                "symbol": "BTCUSDT",
                "orderType": "STOP_MARKET",
                "algoStatus": "NEW",
                "quantity": "0.1",
                "triggerPrice": "49000",
                "closePosition": True,
            }
        ]
    )

    with patch(
        "execution.binance_futures_client.requests.request",
        side_effect=[regular_resp, algo_resp],
    ):
        client = BinanceFuturesClient(cfg)
        out = client.get_open_orders("BTCUSDT")

    assert len(out) == 2
    algo = next(o for o in out if int(o["orderId"]) == 22)
    assert algo["clientOrderId"] == "ALG1"
    assert algo["type"] == "STOP_MARKET"
    assert algo["stopPrice"] == "49000"
