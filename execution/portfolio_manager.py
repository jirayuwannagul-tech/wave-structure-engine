"""
Portfolio-level gates before opening a new exchange position.

Caps concurrent positions and aggregate estimated risk vs equity — not signal filters.
"""

from __future__ import annotations

import os
from typing import Any

from execution.models import ExecutionConfig
from storage.position_store import PositionStore
from execution.execution_health import read_execution_health, record_execution_health


def portfolio_pause_new_entries() -> bool:
    return str(os.getenv("PORTFOLIO_PAUSE_NEW_ENTRIES", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def evaluate_new_position(
    *,
    store: PositionStore,
    config: ExecutionConfig,
    equity_usdt: float,
    new_trade_risk_usdt: float,
    symbol: str,
    position_side: str,
    allow_existing_leg: bool = False,
) -> dict[str, Any]:
    """
    Empty dict => allow. Otherwise {"skipped": reason_key, ...} => block (soft; caller returns ok=True).
    """
    if portfolio_pause_new_entries():
        return {"skipped": "portfolio_pause_new_entries"}

    if equity_usdt <= 0:
        return {"skipped": "invalid_equity", "equity_usdt": equity_usdt}

    # Drawdown-based de-risking (risk scaling only; does not block entries)
    risk_multiplier: float = 1.0
    if config.drawdown_de_risk_enabled:
        peak = read_execution_health("execution:equity_peak_usdt", db_path=store.db_path) or {}
        try:
            peak_eq = float(peak.get("equity_peak_usdt") or 0)
        except (TypeError, ValueError):
            peak_eq = 0.0
        if equity_usdt > peak_eq:
            record_execution_health(
                "execution:equity_peak_usdt",
                {"equity_peak_usdt": float(equity_usdt)},
                db_path=store.db_path,
            )
            peak_eq = float(equity_usdt)
        dd = (peak_eq - equity_usdt) / peak_eq if peak_eq > 0 else 0.0
        start = float(config.drawdown_start_fraction)
        full = float(config.drawdown_full_fraction)
        min_mult = float(config.drawdown_min_risk_multiplier)
        if dd > start and full > start and min_mult > 0:
            # Linear scale from 1.0 down to min_mult
            t = min(1.0, max(0.0, (dd - start) / (full - start)))
            risk_multiplier = max(min_mult, 1.0 - t * (1.0 - min_mult))

    n_open = store.count_open_positions()
    cap_n = int(config.portfolio_max_open_positions)
    if cap_n > 0 and n_open >= cap_n:
        return {
            "skipped": "portfolio_max_open_positions",
            "open_count": n_open,
            "max_open": cap_n,
        }

    frac = float(config.portfolio_max_risk_fraction)
    # frac >= ~1.0 => no aggregate risk cap (default)
    if 0 < frac <= 0.999:
        agg = store.aggregate_open_risk_estimate_usdt()
        cap_risk = float(equity_usdt) * frac
        if agg + float(new_trade_risk_usdt) > cap_risk + 1e-9:
            return {
                "skipped": "portfolio_max_risk_fraction",
                "aggregate_risk_usdt": agg,
                "new_risk_usdt": new_trade_risk_usdt,
                "cap_risk_usdt": cap_risk,
            }

    if not config.hedge_position_mode:
        if store.has_open_position_for_symbol(symbol):
            return {"skipped": "symbol_already_has_open_position"}
    else:
        ps = str(position_side).upper()
        if (not allow_existing_leg) and store.has_open_leg_for_symbol(symbol, ps):
            return {"skipped": "symbol_leg_already_open", "leg": ps}

    out: dict[str, Any] = {}
    if abs(risk_multiplier - 1.0) > 1e-9:
        out["risk_multiplier"] = risk_multiplier
    return out
