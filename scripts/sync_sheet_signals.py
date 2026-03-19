#!/usr/bin/env python3
"""
Push syncable signals from SQLite to Google Sheets (same rules as orchestrator).

Requires: GOOGLE_SHEETS_ENABLED=1, GOOGLE_SHEETS_ID, GOOGLE_CREDENTIALS_PATH

  set -a && source .env && set +a
  .venv/bin/python scripts/sync_sheet_signals.py
  .venv/bin/python scripts/sync_sheet_signals.py BTCUSDT   # optional symbol filter
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.google_sheets_sync import GoogleSheetsSignalLogger, SYNCABLE_SIGNAL_STATUSES, safe_sync_signal
from storage.wave_repository import WaveRepository


def main(argv: list[str]) -> int:
    logger = GoogleSheetsSignalLogger.from_env()
    if logger is None:
        print(
            "Sheets logger not configured (GOOGLE_SHEETS_ENABLED=1 and ID + credentials path).",
            file=sys.stderr,
        )
        return 1
    store = WaveRepository()
    sym_filter = argv[1].strip().upper() if len(argv) > 1 and argv[1].strip() else None
    placeholders = ",".join("?" for _ in sorted(SYNCABLE_SIGNAL_STATUSES))
    statuses = tuple(sorted(SYNCABLE_SIGNAL_STATUSES))
    with store._connect() as conn:
        if sym_filter:
            rows = conn.execute(
                f"""
                SELECT * FROM signals
                WHERE status IN ({placeholders}) AND UPPER(symbol) = ?
                ORDER BY id ASC
                """,
                (*statuses, sym_filter),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                SELECT * FROM signals
                WHERE status IN ({placeholders})
                ORDER BY id ASC
                """,
                statuses,
            ).fetchall()
    n = 0
    for row in rows:
        safe_sync_signal(row, logger)
        n += 1
    print(f"synced {n} signal row(s) to Google Sheets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
