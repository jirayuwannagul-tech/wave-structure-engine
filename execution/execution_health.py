"""Persist execution health markers into ``system_events`` (same DB as wave engine)."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import sqlite3


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def record_execution_health(
    event_key: str,
    details: dict,
    *,
    db_path: str | None = None,
) -> None:
    """
    Upsert a row in system_events (event_key UNIQUE).
    Keys: e.g. execution:last_open_ok, execution:last_portfolio_skip
    """
    db_path = db_path or os.getenv("WAVE_DB_PATH", "storage/wave_engine.db")
    path = Path(db_path)
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS system_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                event_key TEXT NOT NULL UNIQUE,
                details_json TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO system_events (created_at, event_key, details_json)
            VALUES (?, ?, ?)
            ON CONFLICT(event_key) DO UPDATE SET
                created_at = excluded.created_at,
                details_json = excluded.details_json
            """,
            (_utc_now(), event_key, json.dumps(details, sort_keys=True)),
        )
        conn.commit()
    finally:
        conn.close()


def read_execution_health(event_key: str, *, db_path: str | None = None) -> dict | None:
    db_path = db_path or os.getenv("WAVE_DB_PATH", "storage/wave_engine.db")
    path = Path(db_path)
    if not path.exists():
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        try:
            row = conn.execute(
                "SELECT created_at, details_json FROM system_events WHERE event_key = ? LIMIT 1",
                (str(event_key),),
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        if row is None:
            return None
        try:
            payload = json.loads(row["details_json"] or "{}")
        except Exception:
            payload = {}
        payload["_created_at"] = row["created_at"]
        return payload
    finally:
        conn.close()


def clear_execution_health(event_key: str, *, db_path: str | None = None) -> None:
    """Remove a health marker (e.g. pending entry order after fill or cancel)."""
    db_path = db_path or os.getenv("WAVE_DB_PATH", "storage/wave_engine.db")
    path = Path(db_path)
    if not path.exists():
        return
    conn = sqlite3.connect(db_path)
    try:
        try:
            conn.execute("DELETE FROM system_events WHERE event_key = ?", (str(event_key),))
            conn.commit()
        except sqlite3.OperationalError:
            pass
    finally:
        conn.close()
