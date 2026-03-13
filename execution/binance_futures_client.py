from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode

import requests

from execution.models import ExecutionConfig


class BinanceFuturesClient:
    def __init__(self, config: ExecutionConfig):
        self.config = config

    def _timestamp_ms(self) -> int:
        return int(time.time() * 1000)

    def _sign(self, params: dict) -> str:
        if not self.config.api_secret:
            raise RuntimeError("Binance API secret is not configured.")
        query_string = urlencode(params, doseq=True)
        return hmac.new(
            self.config.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _headers(self) -> dict[str, str]:
        if not self.config.api_key:
            raise RuntimeError("Binance API key is not configured.")
        return {"X-MBX-APIKEY": self.config.api_key}

    def _request(self, method: str, path: str, *, params: dict | None = None, signed: bool = False):
        payload = dict(params or {})
        if signed:
            payload.setdefault("timestamp", self._timestamp_ms())
            payload.setdefault("recvWindow", self.config.recv_window)
            payload["signature"] = self._sign(payload)

        response = requests.request(
            method=method,
            url=f"{self.config.base_url}{path}",
            params=payload,
            headers=self._headers() if (signed or self.config.api_key) else None,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def ping(self):
        return self._request("GET", "/fapi/v1/ping")

    def get_account_information(self):
        return self._request("GET", "/fapi/v2/account", signed=True)

    def get_balance(self):
        return self._request("GET", "/fapi/v2/balance", signed=True)

    def get_position_risk(self):
        return self._request("GET", "/fapi/v2/positionRisk", signed=True)

    def set_leverage(self, symbol: str, leverage: int):
        return self._request(
            "POST",
            "/fapi/v1/leverage",
            params={"symbol": symbol, "leverage": leverage},
            signed=True,
        )

    def set_margin_type(self, symbol: str, margin_type: str):
        return self._request(
            "POST",
            "/fapi/v1/marginType",
            params={"symbol": symbol, "marginType": margin_type.upper()},
            signed=True,
        )

    def place_market_order(self, *, symbol: str, side: str, quantity: float):
        if not self.config.live_order_enabled:
            raise RuntimeError("Live Binance order placement is disabled.")

        order_side = "BUY" if side.upper() == "LONG" else "SELL"
        return self._request(
            "POST",
            "/fapi/v1/order",
            params={
                "symbol": symbol,
                "side": order_side,
                "type": "MARKET",
                "quantity": quantity,
            },
            signed=True,
        )
