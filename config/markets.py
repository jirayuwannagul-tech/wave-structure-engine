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


# Symbol-specific trading rules — only override what's necessary.
SYMBOL_RULES: dict[str, dict] = {
    "DOGEUSDT": {
        # SHORT requires price below EMA200 (long-term bearish confirmed)
        "short_requires_ema200_bearish": True,
        # SHORT requires RSI < 45 (stronger momentum, not just < 50)
        "short_rsi_threshold": 45.0,
        # Minimum R:R for any trade (default is 0.8)
        "min_rr": 1.2,
        # 4H SHORT requires 2 confirmations like 1D (not just 1)
        "short_4h_min_confirmations": 2,
    },
}


def get_symbol_rules(symbol: str) -> dict:
    return SYMBOL_RULES.get(symbol.upper(), {})
