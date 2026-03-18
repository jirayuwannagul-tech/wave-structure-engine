from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from execution.binance_futures_client import BinanceFuturesClient


@dataclass(frozen=True)
class SymbolFilters:
    symbol: str
    price_tick: float
    qty_step: float
    min_qty: float | None
    min_notional: float | None


def _parse_symbol_filters(raw: dict) -> SymbolFilters:
    symbol = str(raw.get("symbol") or "").upper()
    price_tick = 0.0
    qty_step = 0.0
    min_qty: float | None = None
    min_notional: float | None = None

    for f in raw.get("filters", []):
        ftype = f.get("filterType")
        if ftype == "PRICE_FILTER":
            price_tick = float(f.get("tickSize", 0.0))
        elif ftype == "LOT_SIZE":
            qty_step = float(f.get("stepSize", 0.0))
            try:
                min_qty_val = float(f.get("minQty", 0.0))
            except (TypeError, ValueError):
                min_qty_val = 0.0
            min_qty = min_qty_val if min_qty_val > 0 else None
        elif ftype == "MIN_NOTIONAL":
            try:
                mn = float(f.get("notional", 0.0))
            except (TypeError, ValueError):
                mn = 0.0
            min_notional = mn if mn > 0 else None

    return SymbolFilters(
        symbol=symbol,
        price_tick=price_tick or 0.0,
        qty_step=qty_step or 0.0,
        min_qty=min_qty,
        min_notional=min_notional,
    )


@lru_cache(maxsize=128)
def get_symbol_filters(client: BinanceFuturesClient, symbol: str) -> SymbolFilters:
    """Fetch and cache exchange filters for a single symbol."""
    info = client.get_exchange_info(symbol.upper())
    symbols = info.get("symbols") or []
    symbol_u = symbol.upper()
    for item in symbols:
        if str(item.get("symbol") or "").upper() == symbol_u:
            return _parse_symbol_filters(item)
    # Fallback: minimal filters if symbol not found (e.g. testnet mismatch)
    return SymbolFilters(symbol=symbol_u, price_tick=0.0, qty_step=0.0, min_qty=None, min_notional=None)


def round_price(client: BinanceFuturesClient, symbol: str, price: float) -> float:
    """Round price down to nearest valid tick size."""
    filters = get_symbol_filters(client, symbol)
    tick = float(filters.price_tick or 0.0)
    if tick <= 0:
        return float(price)
    steps = int(float(price) / tick)
    return round(steps * tick, 8)


def round_quantity(client: BinanceFuturesClient, symbol: str, quantity: float) -> float:
    """Round quantity down to nearest valid lot size."""
    filters = get_symbol_filters(client, symbol)
    step = float(filters.qty_step or 0.0)
    if step <= 0:
        return float(quantity)
    steps = int(float(quantity) / step)
    return round(steps * step, 8)


def validate_order(
    client: BinanceFuturesClient,
    symbol: str,
    price: float,
    quantity: float,
) -> None:
    """Raise ValueError if the order violates basic exchange filters.

    This is a safety check against obviously invalid orders, not a strategy filter.
    """
    filters = get_symbol_filters(client, symbol)
    qty = float(quantity)
    if filters.min_qty is not None and qty < filters.min_qty:
        raise ValueError(f"Order quantity {qty} is below minQty {filters.min_qty} for {symbol}.")

    notional = float(price) * qty
    if filters.min_notional is not None and notional < filters.min_notional:
        raise ValueError(
            f"Order notional {notional} is below MIN_NOTIONAL {filters.min_notional} for {symbol}."
        )


def round_qty(client: BinanceFuturesClient, symbol: str, qty: float) -> float:
    """Alias for :func:`round_quantity` (spec naming)."""
    return round_quantity(client, symbol, qty)

