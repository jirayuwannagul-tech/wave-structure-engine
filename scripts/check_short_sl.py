#!/usr/bin/env python3
"""One-off: list ACTIVE SHORT signals where stop_loss <= entry (blocks Binance open)."""
from __future__ import annotations

import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from config.settings import load_env_file  # noqa: E402

load_env_file(".env")
db = os.getenv("WAVE_DB_PATH", "storage/wave_engine.db")
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """
    SELECT id, symbol, timeframe, side, entry_price, stop_loss, status
    FROM signals
    WHERE status IN ('ACTIVE', 'PARTIAL_TP1', 'PARTIAL_TP2')
      AND UPPER(TRIM(side)) = 'SHORT'
    """
).fetchall()
bad = []
for r in rows:
    ep, sl = r["entry_price"], r["stop_loss"]
    if ep is None or sl is None:
        continue
    try:
        if float(sl) <= float(ep):
            bad.append(dict(r))
    except (TypeError, ValueError):
        continue
print("Invalid SHORT (SL must be > entry):", len(bad))
for b in bad[:30]:
    print(b)
conn.close()
