"""
Portfolio-level gates before opening a new exchange position.

Caps concurrent positions and aggregate estimated risk vs equity — not signal filters.
"""

from __future__ import annotations

import os
from typing import Any

from execution.models import ExecutionConfig
from storage.position_store import PositionStore


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
) -> dict[str, Any]:
    """
    Empty dict => allow. Otherwise {"skipped": reason_key, ...} => block (soft; caller returns ok=True).
    """
    if portfolio_pause_new_entries():
        return {"skipped": "portfolio_pause_new_entries"}

    if equity_usdt <= 0:
        return {"skipped": "invalid_equity", "equity_usdt": equity_usdt}

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
        if store.has_open_leg_for_symbol(symbol, ps):
            return {"skipped": "symbol_leg_already_open", "leg": ps}

    return {}
