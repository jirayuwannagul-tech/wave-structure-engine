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


def _env_optional_float(name: str) -> float | None:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return None
    return float(raw)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _normalize_tp_allocations(tp1: float, tp2: float, tp3: float) -> tuple[float, float, float]:
    """
    Normalize TP allocation percentages so they always sum to 1.0 within a small tolerance.

    This is a safety helper, not a strategy filter: it prevents configuration mistakes
    from producing over- or under-sized total exits.
    """
    total = float(tp1) + float(tp2) + float(tp3)
    if total <= 0:
        # Fall back to a sensible default split if misconfigured
        return 0.4, 0.3, 0.3

    # If already within tolerance of 1.0, keep as-is
    if 0.98 <= total <= 1.02:
        return float(tp1), float(tp2), float(tp3)

    # Scale proportionally to sum to 1.0
    scale = 1.0 / total
    return float(tp1) * scale, float(tp2) * scale, float(tp3) * scale


def _env_entry_style() -> str:
    raw = (os.getenv("BINANCE_ENTRY_STYLE") or "signal_price").strip().lower()
    if raw in {"market", "m", "immediate"}:
        return "market"
    if raw in {
        "signal",
        "signal_price",
        "entry",
        "limit",
        "planned",
        "plan",
    }:
        return "signal_price"
    return "signal_price"


def load_execution_config() -> ExecutionConfig:
    entry_style = _env_entry_style()
    tp1 = _env_float("BINANCE_TP1_SIZE_PCT", 0.40)
    tp2 = _env_float("BINANCE_TP2_SIZE_PCT", 0.30)
    tp3 = _env_float("BINANCE_TP3_SIZE_PCT", 0.30)
    raw_sum = float(tp1) + float(tp2) + float(tp3)
    if raw_sum <= 0:
        raise ValueError(
            "BINANCE_TP1_SIZE_PCT + BINANCE_TP2_SIZE_PCT + BINANCE_TP3_SIZE_PCT must be "
            f"positive (got sum={raw_sum}). Fix .env allocation weights."
        )
    tp1, tp2, tp3 = _normalize_tp_allocations(tp1, tp2, tp3)

    notional_frac = _env_optional_float("BINANCE_POSITION_NOTIONAL_FRACTION")
    if notional_frac is not None and notional_frac <= 0:
        notional_frac = None

    return ExecutionConfig(
        enabled=_env_flag("BINANCE_EXECUTION_ENABLED", False),
        live_order_enabled=_env_flag("BINANCE_LIVE_ORDER_ENABLED", False),
        use_testnet=_env_flag("BINANCE_USE_TESTNET", True),
        api_key=os.getenv("BINANCE_FUTURES_API_KEY"),
        api_secret=os.getenv("BINANCE_FUTURES_API_SECRET"),
        recv_window=_env_int("BINANCE_RECV_WINDOW", 5000),
        risk_per_trade=_env_float("BINANCE_RISK_PER_TRADE", 0.01),
        position_notional_fraction=notional_frac,
        leverage=_env_int("BINANCE_DEFAULT_LEVERAGE", 1),
        margin_type=(os.getenv("BINANCE_MARGIN_TYPE") or "ISOLATED").upper(),
        allow_long=_env_flag("BINANCE_ALLOW_LONG", True),
        allow_short=_env_flag("BINANCE_ALLOW_SHORT", True),
        tp1_size_pct=tp1,
        tp2_size_pct=tp2,
        tp3_size_pct=tp3,
        portfolio_max_open_positions=_env_int("PORTFOLIO_MAX_OPEN_POSITIONS", 100),
        portfolio_max_risk_fraction=_env_float("PORTFOLIO_MAX_RISK_FRACTION", 1.0),
        hedge_position_mode=_env_flag("BINANCE_HEDGE_POSITION_MODE", False),
        http_max_retries=max(1, _env_int("BINANCE_HTTP_MAX_RETRIES", 3)),
        http_retry_backoff_sec=max(0.1, _env_float("BINANCE_HTTP_RETRY_BACKOFF_SEC", 0.6)),
        allow_scale_in_same_leg=_env_flag("BINANCE_ALLOW_SCALE_IN_SAME_LEG", False),
        execution_queue_enabled=_env_flag("EXECUTION_QUEUE_ENABLED", entry_style == "signal_price"),
        execution_queue_max_tasks_per_cycle=max(1, _env_int("EXECUTION_QUEUE_MAX_TASKS_PER_CYCLE", 10)),
        circuit_breaker_enabled=_env_flag("EXECUTION_CIRCUIT_BREAKER_ENABLED", True),
        circuit_breaker_failures=max(1, _env_int("EXECUTION_CIRCUIT_BREAKER_FAILURES", 5)),
        circuit_breaker_cooldown_sec=max(1.0, _env_float("EXECUTION_CIRCUIT_BREAKER_COOLDOWN_SEC", 60.0)),
        drawdown_de_risk_enabled=_env_flag("PORTFOLIO_DRAWDOWN_DE_RISK_ENABLED", False),
        drawdown_start_fraction=max(0.0, _env_float("PORTFOLIO_DRAWDOWN_START_FRACTION", 0.10)),
        drawdown_full_fraction=max(0.0, _env_float("PORTFOLIO_DRAWDOWN_FULL_FRACTION", 0.30)),
        drawdown_min_risk_multiplier=max(0.0, _env_float("PORTFOLIO_DRAWDOWN_MIN_RISK_MULTIPLIER", 0.25)),
        entry_style=entry_style,
    )
