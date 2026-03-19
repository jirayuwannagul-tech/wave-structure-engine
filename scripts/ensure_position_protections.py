#!/usr/bin/env python3
"""
Place missing SL/TP on *current* open positions only.

- Does NOT market-close positions or cancel working entry orders.
- Runs reconcile per symbol (sync DB ↔ exchange, resize SL qty if needed, then
  PositionManager.ensure_protection: backfill levels from active signals + SL + TP).

VPS (after deploy, same env as orchestrator — WorkingDirectory + .env):

  cd /root/wave-structure-engine   # or your DEPLOY_PATH
  set -a && source .env && set +a
  .venv/bin/python scripts/ensure_position_protections.py

Optional symbols (default: union of DB OPEN + exchange non-flat legs):

  .venv/bin/python scripts/ensure_position_protections.py BTCUSDT ETHUSDT
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Repo root on path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from execution.binance_futures_client import BinanceFuturesClient
from execution.reconciler import reconcile_symbol
from execution.settings import load_execution_config
from storage.position_store import PositionStore


def _truthy_kill_switch() -> bool:
    return str(os.getenv("KILL_SWITCH", "0")).strip().lower() in {"1", "true", "yes", "on"}


def _symbols_from_exchange(client: BinanceFuturesClient) -> set[str]:
    out: set[str] = set()
    for row in client.get_position_risk() or []:
        try:
            amt = float(row.get("positionAmt") or 0)
        except (TypeError, ValueError):
            amt = 0.0
        if abs(amt) < 1e-12:
            continue
        sym = str(row.get("symbol") or "").upper()
        if sym:
            out.add(sym)
    return out


def _config_diagnostic(cfg) -> dict:
    """Safe snapshot (no secrets) for debugging why orders are not sent."""
    return {
        "BINANCE_EXECUTION_ENABLED": cfg.enabled,
        "BINANCE_LIVE_ORDER_ENABLED": cfg.live_order_enabled,
        "BINANCE_USE_TESTNET": cfg.use_testnet,
        "credentials_ready": cfg.credentials_ready,
        "KILL_SWITCH": _truthy_kill_switch(),
    }


def main(argv: list[str]) -> int:
    cfg = load_execution_config()
    diag = _config_diagnostic(cfg)
    if not cfg.enabled:
        print(
            "ERROR: BINANCE_EXECUTION_ENABLED is not true — execution layer is off.\n"
            "Set BINANCE_EXECUTION_ENABLED=1 in .env (same file systemd/orchestrator loads).",
            file=sys.stderr,
        )
        print(json.dumps({"ok": False, "diagnostic": diag}, indent=2))
        return 1
    if not cfg.live_order_enabled:
        print(
            "ERROR: BINANCE_LIVE_ORDER_ENABLED is not true — SL/TP will NEVER be sent to Binance.\n"
            "This is the most common reason protective orders do not appear on the exchange.\n"
            "Set BINANCE_LIVE_ORDER_ENABLED=1 in .env, then restart orchestrator or re-run this script.",
            file=sys.stderr,
        )
        print(json.dumps({"ok": False, "diagnostic": diag}, indent=2))
        return 1
    if not cfg.credentials_ready:
        print(
            "ERROR: BINANCE_FUTURES_API_KEY / BINANCE_FUTURES_API_SECRET missing or empty.",
            file=sys.stderr,
        )
        print(json.dumps({"ok": False, "diagnostic": diag}, indent=2))
        return 1
    if _truthy_kill_switch():
        print("ERROR: KILL_SWITCH is on — no orders are allowed.", file=sys.stderr)
        print(json.dumps({"ok": False, "diagnostic": diag}, indent=2))
        return 1

    store = PositionStore()
    client = BinanceFuturesClient(cfg)

    if len(argv) > 1:
        syms = {a.strip().upper() for a in argv[1:] if a.strip()}
    else:
        syms = set(store.list_open_symbols()) | _symbols_from_exchange(client)

    if not syms:
        print(json.dumps({"ok": True, "message": "no_open_symbols", "symbols": []}))
        return 0

    results: list[dict] = []
    for sym in sorted(syms):
        try:
            r = reconcile_symbol(client, store, sym, cfg)
            results.append({"symbol": sym, "reconcile": r})
        except Exception as exc:
            results.append({"symbol": sym, "error": str(exc)})

    print(
        json.dumps(
            {"ok": True, "diagnostic": diag, "symbols": sorted(syms), "results": results},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
