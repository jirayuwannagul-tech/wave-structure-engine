from execution.binance_futures_client import BinanceFuturesClient
from execution.models import ExecutionConfig


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_binance_futures_client_signed_request(monkeypatch):
    captured = {}

    def fake_request(method, url, params=None, headers=None, timeout=None):
        captured["method"] = method
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _Response({"ok": True})

    monkeypatch.setattr("execution.binance_futures_client.requests.request", fake_request)

    client = BinanceFuturesClient(
        ExecutionConfig(
            api_key="key",
            api_secret="secret",
            use_testnet=True,
        )
    )

    result = client.get_account_information()

    assert result == {"ok": True}
    assert captured["method"] == "GET"
    assert captured["url"] == "https://testnet.binancefuture.com/fapi/v2/account"
    assert captured["headers"]["X-MBX-APIKEY"] == "key"
    assert "timestamp" in captured["params"]
    assert "signature" in captured["params"]


def test_binance_futures_client_position_risk(monkeypatch):
    captured = {}

    def fake_request(method, url, params=None, headers=None, timeout=None):
        captured["method"] = method
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        return _Response([{"symbol": "BTCUSDT"}])

    monkeypatch.setattr("execution.binance_futures_client.requests.request", fake_request)

    client = BinanceFuturesClient(
        ExecutionConfig(
            api_key="key",
            api_secret="secret",
            use_testnet=False,
        )
    )

    result = client.get_position_risk()

    assert result == [{"symbol": "BTCUSDT"}]
    assert captured["method"] == "GET"
    assert captured["url"] == "https://fapi.binance.com/fapi/v2/positionRisk"
