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
    "NEARUSDT",
    "TRXUSDT",
    "ARBUSDT",
    "ATOMUSDT",
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
        "short_requires_ema200_bearish": True,
        "short_rsi_threshold": 45.0,
        "min_rr": 1.2,
        "short_4h_min_confirmations": 2,
    },
    # NEAR — L1, ประวัติตั้งแต่ 2020, trending ชัด
    "NEARUSDT": {
        "short_requires_ema200_bearish": True,
        "min_rr": 1.2,
    },
    # TRX — volume สูง, ประวัติยาวตั้งแต่ 2018, ตาม BTC ใกล้ชิด
    "TRXUSDT": {
        "short_requires_ema200_bearish": True,
        "short_rsi_threshold": 45.0,
        "min_rr": 1.2,
        "short_4h_min_confirmations": 2,
    },
    # ARB — L2, ประวัติสั้น (2022), ตาม ETH ใกล้ชิด
    "ARBUSDT": {
        "short_requires_ema200_bearish": True,
        "min_rr": 1.5,
        "short_4h_min_confirmations": 2,
    },
    # ATOM — Cosmos, ประวัติตั้งแต่ 2019, trending ชัด
    "ATOMUSDT": {
        "short_requires_ema200_bearish": True,
        "min_rr": 1.2,
    },
}


def get_symbol_rules(symbol: str) -> dict:
    return SYMBOL_RULES.get(symbol.upper(), {})
