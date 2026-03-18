from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any, Iterable
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

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        signed: bool = False,
    ) -> Any:
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

    def _kill_switch_active(self) -> bool:
        raw = os.getenv("KILL_SWITCH", "0")
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    def _ensure_trading_enabled(self) -> None:
        if self._kill_switch_active():
            raise RuntimeError("Global kill switch is active. Order placement is disabled.")
        if not self.config.enabled:
            raise RuntimeError("Binance execution is disabled.")
        if not self.config.live_order_enabled:
            raise RuntimeError("Live Binance order placement is disabled.")

    # --------------------------------------------------------------------- #
    # Public REST helpers                                                   #
    # --------------------------------------------------------------------- #

    def ping(self) -> Any:
        return self._request("GET", "/fapi/v1/ping")

    def get_account_information(self) -> Any:
        return self._request("GET", "/fapi/v2/account", signed=True)

    def get_balance(self) -> Any:
        return self._request("GET", "/fapi/v2/balance", signed=True)

    def get_position_risk(self) -> Any:
        return self._request("GET", "/fapi/v2/positionRisk", signed=True)

    def get_position(self, symbol: str) -> dict | None:
        """Return the first positionRisk entry for the given symbol, or None."""
        symbol_u = symbol.upper()
        payload = self.get_position_risk() or []
        for row in payload:
            if str(row.get("symbol") or "").upper() == symbol_u:
                return row
        return None

    def get_exchange_info(self, symbol: str | None = None) -> Any:
        params = {"symbol": symbol.upper()} if symbol else None
        return self._request("GET", "/fapi/v1/exchangeInfo", params=params or {}, signed=False)

    def get_open_orders(self, symbol: str | None = None) -> Any:
        params: dict[str, str] = {}
        if symbol:
            params["symbol"] = symbol.upper()
        return self._request("GET", "/fapi/v1/openOrders", params=params, signed=True)

    def cancel_order(
        self,
        *,
        symbol: str,
        order_id: int | None = None,
        client_order_id: str | None = None,
    ) -> Any:
        self._ensure_trading_enabled()
        params: dict[str, Any] = {"symbol": symbol.upper()}
        if order_id is not None:
            params["orderId"] = int(order_id)
        if client_order_id is not None:
            params["origClientOrderId"] = client_order_id
        return self._request("DELETE", "/fapi/v1/order", params=params, signed=True)

    def query_order(self, *, symbol: str, order_id: int) -> Any:
        """GET order status (FILLED / CANCELED / NEW / …) for sync with DB."""
        params = {"symbol": symbol.upper(), "orderId": int(order_id)}
        return self._request("GET", "/fapi/v1/order", params=params, signed=True)

    def cancel_all_orders(self, *, symbol: str) -> Any:
        self._ensure_trading_enabled()
        params = {"symbol": symbol.upper()}
        return self._request("DELETE", "/fapi/v1/allOpenOrders", params=params, signed=True)

    # --------------------------------------------------------------------- #
    # Order placement                                                       #
    # --------------------------------------------------------------------- #

    def _entry_side(self, side: str) -> str:
        return "BUY" if side.upper() == "LONG" else "SELL"

    def _exit_side(self, side: str) -> str:
        # Exit is always opposite of the position side
        return "SELL" if side.upper() == "LONG" else "BUY"

    def _place_order(
        self,
        *,
        symbol: str,
        side: str,
        type_: str,
        quantity: float,
        extra_params: dict | None = None,
        client_order_id: str | None = None,
    ) -> Any:
        self._ensure_trading_enabled()
        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "side": side,
            "type": type_,
            "quantity": quantity,
        }
        if client_order_id:
            params["newClientOrderId"] = client_order_id
        if extra_params:
            params.update(extra_params)
        return self._request("POST", "/fapi/v1/order", params=params, signed=True)

    def place_market_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        client_order_id: str | None = None,
    ) -> Any:
        order_side = self._entry_side(side)
        return self._place_order(
            symbol=symbol,
            side=order_side,
            type_="MARKET",
            quantity=quantity,
            extra_params=None,
            client_order_id=client_order_id,
        )

    def place_market_entry(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        client_order_id: str | None = None,
    ) -> Any:
        """Alias for :meth:`place_market_order` (spec naming)."""
        return self.place_market_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            client_order_id=client_order_id,
        )

    def place_market_reduce_only(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        client_order_id: str | None = None,
    ) -> Any:
        """Close or reduce position: side must be BUY or SELL."""
        s = side.upper()
        if s not in {"BUY", "SELL"}:
            raise ValueError("place_market_reduce_only side must be BUY or SELL")
        return self._place_order(
            symbol=symbol,
            side=s,
            type_="MARKET",
            quantity=quantity,
            extra_params={"reduceOnly": "true"},
            client_order_id=client_order_id,
        )

    def place_stop_market_reduce_only(
        self,
        *,
        symbol: str,
        side: str,
        stop_price: float,
        quantity: float,
        client_order_id: str | None = None,
    ) -> Any:
        """Place a STOP_MARKET reduce-only order used as protective stop loss."""
        order_side = self._exit_side(side)
        extra = {
            "stopPrice": stop_price,
            "reduceOnly": "true",
            "workingType": "CONTRACT_PRICE",
        }
        return self._place_order(
            symbol=symbol,
            side=order_side,
            type_="STOP_MARKET",
            quantity=quantity,
            extra_params=extra,
            client_order_id=client_order_id,
        )

    def place_take_profit_market_reduce_only(
        self,
        *,
        symbol: str,
        side: str,
        stop_price: float,
        quantity: float,
        client_order_id: str | None = None,
    ) -> Any:
        """Place a TAKE_PROFIT_MARKET reduce-only order used as TP."""
        order_side = self._exit_side(side)
        extra = {
            "stopPrice": stop_price,
            "reduceOnly": "true",
            "workingType": "CONTRACT_PRICE",
        }
        return self._place_order(
            symbol=symbol,
            side=order_side,
            type_="TAKE_PROFIT_MARKET",
            quantity=quantity,
            extra_params=extra,
            client_order_id=client_order_id,
        )
