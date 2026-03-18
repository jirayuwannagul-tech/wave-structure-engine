from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from execution.binance_futures_client import BinanceFuturesClient

# Raw exchangeInfo JSON per client instance + symbol (spec: get_exchange_info_cached)
_exchange_info_cache: dict[tuple[int, str], dict[str, Any]] = {}
_EXCHANGE_INFO_CACHE_MAX = 128


@dataclass(frozen=True)
class SymbolFilters:
    symbol: str
    price_tick: float
    qty_step: float
    min_qty: float | None
    min_notional: float | None


def get_exchange_info_cached(
    client: BinanceFuturesClient,
    symbol: str | None = None,
) -> dict[str, Any]:
    """
    Cached ``exchangeInfo`` for a symbol (or full market if symbol is None).
    Spec name; avoids redundant REST calls when resolving filters.
    """
    sym = (symbol or "").upper()
    key = (id(client), sym)
    if key not in _exchange_info_cache:
        if len(_exchange_info_cache) >= _EXCHANGE_INFO_CACHE_MAX:
            _exchange_info_cache.clear()
        _exchange_info_cache[key] = client.get_exchange_info(symbol)
    return _exchange_info_cache[key]


def clear_exchange_info_cache(client: BinanceFuturesClient | None = None) -> None:
    """Clear cache for one client or entire cache (tests)."""
    global _exchange_info_cache
    if client is None:
        _exchange_info_cache = {}
        return
    cid = id(client)
    _exchange_info_cache = {k: v for k, v in _exchange_info_cache.items() if k[0] != cid}


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


def get_symbol_filters(client: BinanceFuturesClient, symbol: str) -> SymbolFilters:
    """tickSize / stepSize / minQty / minNotional for one symbol."""
    info = get_exchange_info_cached(client, symbol.upper())
    symbols = info.get("symbols") or []
    symbol_u = symbol.upper()
    for item in symbols:
        if str(item.get("symbol") or "").upper() == symbol_u:
            return _parse_symbol_filters(item)
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


def round_quantity_clamped(
    client: BinanceFuturesClient,
    symbol: str,
    quantity: float,
    *,
    reference_price: float,
) -> float:
    """
    Like round_quantity; if result is 0, clamp to minQty when notional still passes MIN_NOTIONAL.
    Spec: helper so qty is not left at 0 after rounding when exchange allows min lot.
    """
    q = round_quantity(client, symbol, quantity)
    if q > 0:
        return q
    filters = get_symbol_filters(client, symbol)
    ref = float(reference_price or 0.0)
    if filters.min_qty and filters.min_qty > 0 and ref > 0:
        mq = float(filters.min_qty)
        notional = ref * mq
        if filters.min_notional is None or notional + 1e-12 >= float(filters.min_notional):
            return round_quantity(client, symbol, mq)
    raise ValueError(
        f"Quantity for {symbol} rounds to zero after lot step and cannot clamp to minQty "
        f"within MIN_NOTIONAL (reference_price={reference_price})."
    )


def validate_order(
    client: BinanceFuturesClient,
    symbol: str,
    price: float,
    quantity: float,
) -> None:
    """Raise ValueError if the order violates basic exchange filters."""
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
