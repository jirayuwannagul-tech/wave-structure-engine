from __future__ import annotations

import os


# Large-cap, liquid USDT pairs with enough Binance history to support 1W/1D/4H.
DEFAULT_MONITOR_SYMBOLS: tuple[str, ...] = (
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "DOGEUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "LTCUSDT",
)


def get_default_monitor_symbols() -> list[str]:
    configured = os.getenv("MONITOR_SYMBOLS")
    if configured:
        symbols = [item.strip().upper() for item in configured.split(",") if item.strip()]
        if symbols:
            return symbols
    return list(DEFAULT_MONITOR_SYMBOLS)
