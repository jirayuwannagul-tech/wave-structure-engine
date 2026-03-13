from __future__ import annotations

import os

from execution.models import ExecutionConfig


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def load_execution_config() -> ExecutionConfig:
    return ExecutionConfig(
        enabled=_env_flag("BINANCE_EXECUTION_ENABLED", False),
        live_order_enabled=_env_flag("BINANCE_LIVE_ORDER_ENABLED", False),
        use_testnet=_env_flag("BINANCE_USE_TESTNET", True),
        api_key=os.getenv("BINANCE_FUTURES_API_KEY"),
        api_secret=os.getenv("BINANCE_FUTURES_API_SECRET"),
        recv_window=_env_int("BINANCE_RECV_WINDOW", 5000),
        risk_per_trade=_env_float("BINANCE_RISK_PER_TRADE", 0.01),
        leverage=_env_int("BINANCE_DEFAULT_LEVERAGE", 1),
        margin_type=(os.getenv("BINANCE_MARGIN_TYPE") or "ISOLATED").upper(),
        allow_long=_env_flag("BINANCE_ALLOW_LONG", True),
        allow_short=_env_flag("BINANCE_ALLOW_SHORT", True),
        tp1_size_pct=_env_float("BINANCE_TP1_SIZE_PCT", 0.40),
        tp2_size_pct=_env_float("BINANCE_TP2_SIZE_PCT", 0.30),
        tp3_size_pct=_env_float("BINANCE_TP3_SIZE_PCT", 0.30),
    )
