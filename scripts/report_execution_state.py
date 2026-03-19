#!/usr/bin/env python3
"""
Print open exchange positions + linked signal ids from SQLite (truth for VPS).

The default Google Sheet tab `wave_log` has NO signal_id column — compare manually using
symbol, timeframe, side, entry, sl, tp*.

Usage on VPS:
  cd /root/wave-structure-engine
  set -a && source .env && set +a
  .venv/bin/python scripts/report_execution_state.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from execution.settings import load_execution_config
from storage.position_store import PositionStore
from storage.wave_repository import WaveRepository, OPEN_SIGNAL_STATUSES


def main() -> int:
    cfg = load_execution_config()
    store = PositionStore()
    repo = WaveRepository(db_path=store.db_path)

    out: dict = {
        "execution": {
            "BINANCE_EXECUTION_ENABLED": cfg.enabled,
            "BINANCE_LIVE_ORDER_ENABLED": cfg.live_order_enabled,
            "credentials_ready": cfg.credentials_ready,
            "KILL_SWITCH": str(os.getenv("KILL_SWITCH", "0")).strip().lower()
            in {"1", "true", "yes", "on"},
            "note": "SL/TP are only sent when execution+live are true and KILL_SWITCH is off.",
        },
        "open_exchange_positions": [],
        "active_signals_by_symbol": {},
        "sheet_note": "wave_log columns: date,symbol,timeframe,side,entry,sl,tp1,tp2,tp3,... — no signal id.",
    }

    with store._connect() as conn:
        pos_rows = conn.execute(
            """
            SELECT id, symbol, side, status, source_signal_id, quantity, entry_price,
                   stop_loss_price, tp1_price, tp2_price, tp3_price, recovered
            FROM exchange_positions
            WHERE status = 'OPEN'
            ORDER BY symbol, id
            """
        ).fetchall()

    for r in pos_rows:
        sid = r["source_signal_id"]
        sig_snip = None
        if sid is not None:
            srow = repo.fetch_signal(int(sid))
            if srow is not None:
                sig_snip = {
                    "id": int(srow["id"]),
                    "status": str(srow["status"] or ""),
                    "timeframe": str(srow["timeframe"] or ""),
                    "entry_price": srow["entry_price"],
                    "stop_loss": srow["stop_loss"],
                }
        out["open_exchange_positions"].append(
            {
                "position_db_id": int(r["id"]),
                "symbol": str(r["symbol"] or ""),
                "side": str(r["side"] or ""),
                "source_signal_id": int(sid) if sid is not None else None,
                "signal_row": sig_snip,
                "position_entry_price": r["entry_price"],
                "stop_loss_price": r["stop_loss_price"],
                "tp1_price": r["tp1_price"],
                "recovered": int(r["recovered"] or 0),
            }
        )

    # All ACTIVE-family signals per symbol (to spot duplicate LINK rows)
    placeholders = ",".join("?" for _ in sorted(OPEN_SIGNAL_STATUSES))
    statuses = tuple(sorted(OPEN_SIGNAL_STATUSES))
    with repo._connect() as conn:
        sigs = conn.execute(
            f"""
            SELECT id, symbol, timeframe, side, status, entry_price, stop_loss
            FROM signals
            WHERE status IN ({placeholders})
            ORDER BY symbol, id
            """,
            statuses,
        ).fetchall()

    by_sym: dict[str, list] = {}
    for s in sigs:
        sym = str(s["symbol"] or "").upper()
        by_sym.setdefault(sym, []).append(
            {
                "signal_id": int(s["id"]),
                "timeframe": str(s["timeframe"] or ""),
                "side": str(s["side"] or ""),
                "status": str(s["status"] or ""),
                "entry_price": s["entry_price"],
                "stop_loss": s["stop_loss"],
            }
        )
    out["active_signals_by_symbol"] = dict(sorted(by_sym.items()))

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
