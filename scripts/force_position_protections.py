#!/usr/bin/env python3
"""
Cancel existing reduce-only SL/TP on Binance for one open leg, write levels into SQLite,
then run ensure_protection (places SL + TP1/2/3 from DB).

Example (LINK 4H SHORT from sheet):
  set -a && source .env && set +a
  .venv/bin/python scripts/force_position_protections.py LINKUSDT SHORT \\
    --sl 9.7161 --tp1 9.1964 --tp2 9.12 --tp3 9.0656

Requires: BINANCE_EXECUTION_ENABLED, BINANCE_LIVE_ORDER_ENABLED, keys, KILL_SWITCH off.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from execution.binance_futures_client import BinanceFuturesClient
from execution.position_manager import PositionManager, exit_order_side_for_position
from execution.settings import load_execution_config
from storage.position_store import PositionStore


def _kill_on() -> bool:
    return str(os.getenv("KILL_SWITCH", "0")).strip().lower() in {"1", "true", "yes", "on"}


def _cancel_exchange_protective_for_leg(
    client: BinanceFuturesClient,
    symbol_u: str,
    *,
    position_side_long_short: str,
    position_side_tag: str | None,
    hedge: bool,
) -> list[int]:
    exit_side = exit_order_side_for_position(position_side_long_short)
    pst = (position_side_tag or "").upper() if position_side_tag else ""
    raw = client.get_open_orders(symbol_u) or []
    if not isinstance(raw, list):
        return []
    canceled: list[int] = []
    for o in raw:
        ot = str(o.get("type") or "").upper()
        if ot not in {"STOP_MARKET", "TAKE_PROFIT_MARKET"}:
            continue
        if str(o.get("reduceOnly") or "").lower() not in ("true", "1"):
            continue
        if str(o.get("side") or "").upper() != exit_side:
            continue
        if hedge and pst:
            if str(o.get("positionSide") or "").upper() != pst:
                continue
        oid = o.get("orderId")
        if oid is None:
            continue
        try:
            oid_i = int(oid)
            client.cancel_order(symbol=symbol_u, order_id=oid_i)
            canceled.append(oid_i)
        except Exception:
            pass
    return canceled


def main() -> int:
    p = argparse.ArgumentParser(description="Force SL/TP levels on an open position")
    p.add_argument("symbol", help="e.g. LINKUSDT")
    p.add_argument("side", choices=["LONG", "SHORT"])
    p.add_argument("--sl", type=float, required=True)
    p.add_argument("--tp1", type=float, required=True)
    p.add_argument("--tp2", type=float, required=True)
    p.add_argument("--tp3", type=float, required=True)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print what would be updated (no cancel, no place)",
    )
    args = p.parse_args()

    cfg = load_execution_config()
    if not cfg.enabled or not cfg.live_order_enabled or not cfg.credentials_ready:
        print("ERROR: execution disabled or live off or missing API keys.", file=sys.stderr)
        return 1
    if _kill_on():
        print("ERROR: KILL_SWITCH is on.", file=sys.stderr)
        return 1

    symbol_u = args.symbol.strip().upper()
    side_u = args.side.upper()
    store = PositionStore()
    rows = [
        r
        for r in store.list_open_positions_for_symbol(symbol_u)
        if str(r["side"] or "").upper() == side_u
    ]
    if not rows:
        print(json.dumps({"ok": False, "error": "no_open_position", "symbol": symbol_u, "side": side_u}))
        return 2
    if len(rows) > 1:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "multiple_open_rows_use_hedge_or_close_duplicates",
                    "ids": [int(r["id"]) for r in rows],
                }
            ),
            file=sys.stderr,
        )
        return 3

    row = rows[0]
    pid = int(row["id"])
    pst = row["position_side_tag"]

    out: dict = {"ok": True, "position_id": pid, "symbol": symbol_u, "side": side_u}

    if args.dry_run:
        out["dry_run"] = True
        out["would_set"] = {
            "sl": args.sl,
            "tp1": args.tp1,
            "tp2": args.tp2,
            "tp3": args.tp3,
        }
        print(json.dumps(out, indent=2))
        return 0

    client = BinanceFuturesClient(cfg)
    canceled = _cancel_exchange_protective_for_leg(
        client,
        symbol_u,
        position_side_long_short=side_u,
        position_side_tag=str(pst) if pst else None,
        hedge=bool(cfg.hedge_position_mode),
    )
    out["canceled_order_ids"] = canceled

    # Clear stale NEW rows so ensure_protection does not think TP/SL still live on book via DB.
    for r in store.list_open_protective_orders(pid):
        if str(r["status"] or "") == "NEW":
            store.update_position_order_row_status(int(r["id"]), "CANCELED")

    store.update_protection_prices(
        pid,
        stop_loss_price=float(args.sl),
        tp1_price=float(args.tp1),
        tp2_price=float(args.tp2),
        tp3_price=float(args.tp3),
    )
    store.append_event(
        pid,
        "FORCED_PROTECTION_LEVELS",
        {"sl": args.sl, "tp1": args.tp1, "tp2": args.tp2, "tp3": args.tp3},
    )

    pm = PositionManager(client, cfg, store)
    prot = pm.ensure_protection(symbol_u)
    out["ensure_protection"] = prot
    print(json.dumps(out, indent=2, default=str))
    return 0 if prot.get("ok") else 4


if __name__ == "__main__":
    raise SystemExit(main())
