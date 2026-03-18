"""
In-memory Binance USDT-M futures client for unit tests (no network).

Implements the subset of methods used by PositionManager and reconciler.
"""

from __future__ import annotations

from typing import Any

import requests


def _btc_exchange_info() -> dict:
    return {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                    {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                    {"filterType": "MIN_NOTIONAL", "notional": "5"},
                ],
            }
        ]
    }


class FakeBinanceFuturesClient:
    """
    Simulates positions, open orders, cancel, market entry/exit.
    Set ``fail_duplicate_entry_client_ids`` to simulate HTTP duplicate clientOrderId
    on the *second* place_market_order with the same newClientOrderId (position must
    already exist from the first attempt).
    """

    def __init__(
        self,
        *,
        fail_duplicate_entry_client_ids: frozenset[str] | None = None,
    ):
        self._amt: dict[str, float] = {}
        self._entry: dict[str, float] = {}
        self._orders: list[dict[str, Any]] = []
        self._order_history: dict[int, dict[str, Any]] = {}
        self._next_oid = 1
        self._market_cids_seen: set[str] = set()
        self._fail_dup_cids = fail_duplicate_entry_client_ids or frozenset()

    def get_balance(self) -> list[dict]:
        return [{"asset": "USDT", "availableBalance": "100000"}]

    def get_account_balance(self) -> list[dict]:
        return self.get_balance()

    def get_exchange_info(self, symbol: str | None = None) -> dict:
        return _btc_exchange_info()

    def get_position_risk(self) -> list[dict]:
        out = []
        for sym, amt in self._amt.items():
            if abs(amt) < 1e-12:
                continue
            out.append(
                {
                    "symbol": sym,
                    "positionAmt": str(amt),
                    "entryPrice": str(self._entry.get(sym, 50000.0)),
                }
            )
        return out or [{"symbol": "BTCUSDT", "positionAmt": "0", "entryPrice": "0"}]

    def get_position(self, symbol: str) -> dict | None:
        sym = symbol.upper()
        for row in self.get_position_risk():
            if str(row.get("symbol") or "").upper() == sym:
                return row
        return {"symbol": sym, "positionAmt": "0", "entryPrice": "0"}

    def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        sym = symbol.upper() if symbol else None
        return [o for o in self._orders if sym is None or o.get("symbol") == sym]

    def query_order(self, *, symbol: str, order_id: int) -> dict[str, Any]:
        sym = symbol.upper()
        for o in self._orders:
            if int(o["orderId"]) == int(order_id) and o.get("symbol") == sym:
                return {
                    "orderId": order_id,
                    "symbol": sym,
                    "status": o.get("status", "NEW"),
                    "origQty": str(o.get("origQty", 0)),
                }
        h = self._order_history.get(int(order_id))
        if h:
            return dict(h)
        return {"orderId": order_id, "symbol": sym, "status": "FILLED", "origQty": "0"}

    def set_margin_type(self, symbol: str, margin_type: str) -> dict:
        return {}

    def set_leverage(self, symbol: str, leverage: int) -> dict:
        return {}

    def _alloc_oid(self) -> int:
        self._next_oid += 1
        return self._next_oid

    def _raise_dup(self) -> None:
        resp = requests.Response()
        resp.status_code = 400
        resp._content = b'{"code":-4116,"msg":"Duplicate client order id"}'
        resp.encoding = "utf-8"

        def _json() -> dict:
            import json

            return json.loads(resp._content.decode())

        resp.json = _json  # type: ignore[method-assign]
        raise requests.HTTPError(response=resp)

    def place_market_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        sym = symbol.upper()
        q = float(quantity)
        cid = client_order_id or ""
        if cid and cid in self._market_cids_seen and cid in self._fail_dup_cids:
            self._raise_dup()
        if cid:
            self._market_cids_seen.add(cid)
        is_long = side.upper() == "LONG"
        cur = self._amt.get(sym, 0.0)
        if is_long:
            self._amt[sym] = cur + q
        else:
            self._amt[sym] = cur - q
        ep = 50000.0 if is_long else 50000.0
        if sym not in self._entry or abs(self._amt[sym]) < 1e-12:
            self._entry[sym] = ep
        oid = self._alloc_oid()
        return {"orderId": oid, "executedQty": str(q), "avgPrice": str(self._entry.get(sym, ep))}

    def place_stop_market_reduce_only(
        self,
        *,
        symbol: str,
        side: str,
        stop_price: float,
        quantity: float,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        sym = symbol.upper()
        oid = self._alloc_oid()
        exit_side = "SELL" if side.upper() == "LONG" else "BUY"
        o = {
            "orderId": oid,
            "symbol": sym,
            "type": "STOP_MARKET",
            "side": exit_side,
            "stopPrice": str(stop_price),
            "origQty": str(quantity),
            "reduceOnly": True,
            "status": "NEW",
            "clientOrderId": client_order_id,
        }
        self._orders.append(o)
        return {"orderId": oid}

    def place_take_profit_market_reduce_only(
        self,
        *,
        symbol: str,
        side: str,
        stop_price: float,
        quantity: float,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        sym = symbol.upper()
        oid = self._alloc_oid()
        exit_side = "SELL" if side.upper() == "LONG" else "BUY"
        o = {
            "orderId": oid,
            "symbol": sym,
            "type": "TAKE_PROFIT_MARKET",
            "side": exit_side,
            "stopPrice": str(stop_price),
            "origQty": str(quantity),
            "reduceOnly": True,
            "status": "NEW",
            "clientOrderId": client_order_id,
        }
        self._orders.append(o)
        return {"orderId": oid}

    def place_market_reduce_only(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        sym = symbol.upper()
        q = float(quantity)
        if side.upper() == "SELL":
            self._amt[sym] = self._amt.get(sym, 0.0) - q
        else:
            self._amt[sym] = self._amt.get(sym, 0.0) + q
        if abs(self._amt.get(sym, 0.0)) < 1e-12:
            self._amt[sym] = 0.0
        return {"orderId": self._alloc_oid()}

    def cancel_order(
        self,
        *,
        symbol: str,
        order_id: int | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        sym = symbol.upper()
        new_open: list[dict] = []
        canceled: dict | None = None
        for o in self._orders:
            if o.get("symbol") != sym:
                new_open.append(o)
                continue
            match = False
            if order_id is not None and int(o["orderId"]) == int(order_id):
                match = True
            if client_order_id and o.get("clientOrderId") == client_order_id:
                match = True
            if match:
                c = dict(o)
                c["status"] = "CANCELED"
                self._order_history[int(o["orderId"])] = c
                canceled = c
            else:
                new_open.append(o)
        self._orders = new_open
        return canceled or {"orderId": order_id, "status": "CANCELED"}

    def cancel_all_orders(self, *, symbol: str) -> dict:
        sym = symbol.upper()
        for o in list(self._orders):
            if o.get("symbol") == sym:
                c = dict(o)
                c["status"] = "CANCELED"
                self._order_history[int(o["orderId"])] = c
        self._orders = [o for o in self._orders if o.get("symbol") != sym]
        return {"code": 200}

    def simulate_fill_order(self, order_id: int) -> None:
        """Remove protective order from book; reduce position by filled qty (reduce-only)."""
        sym = None
        qty = 0.0
        side_exit = None
        new_list = []
        for o in self._orders:
            if int(o["orderId"]) != int(order_id):
                new_list.append(o)
                continue
            sym = o.get("symbol")
            qty = float(o.get("origQty") or 0)
            side_exit = o.get("side")
            h = dict(o)
            h["status"] = "FILLED"
            self._order_history[int(order_id)] = h
        self._orders = new_list
        if sym and qty > 0 and side_exit:
            if side_exit == "SELL":
                self._amt[sym] = self._amt.get(sym, 0.0) - qty
            else:
                self._amt[sym] = self._amt.get(sym, 0.0) + qty
            if abs(self._amt[sym]) < 1e-12:
                self._amt[sym] = 0.0

    def seed_position(self, symbol: str, position_amt: float, entry_price: float = 50000.0) -> None:
        """Pretend a position exists (e.g. duplicate-entry recovery test)."""
        sym = symbol.upper()
        self._amt[sym] = float(position_amt)
        self._entry[sym] = float(entry_price)
