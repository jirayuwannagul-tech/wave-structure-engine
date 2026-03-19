"""SQLite-backed execution task queue (open/close) for live trading."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


class ExecutionQueueStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.getenv("WAVE_DB_PATH", "storage/wave_engine.db")
        self._ensure_tables()

    @contextmanager
    def _connect(self):
        path = Path(self.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=30000;")
        except Exception:
            pass
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_tables(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS execution_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    dedupe_key TEXT,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_run_at TEXT,
                    last_error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_execution_queue_status_next
                ON execution_queue(status, next_run_at);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_execution_queue_dedupe
                ON execution_queue(dedupe_key)
                WHERE dedupe_key IS NOT NULL;
                """
            )

    def enqueue(self, task_type: str, payload: dict[str, Any], *, dedupe_key: str | None = None) -> int | None:
        now = _utc_now()
        with self._connect() as conn:
            try:
                cur = conn.execute(
                    """
                    INSERT INTO execution_queue (created_at, updated_at, task_type, dedupe_key, payload_json, status)
                    VALUES (?, ?, ?, ?, ?, 'PENDING')
                    """,
                    (now, now, str(task_type), dedupe_key, json.dumps(payload, sort_keys=True)),
                )
                return int(cur.lastrowid)
            except sqlite3.IntegrityError:
                return None

    def fetch_ready(self, limit: int = 10) -> list[sqlite3.Row]:
        now = datetime.now(UTC)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM execution_queue
                WHERE status IN ('PENDING', 'RETRY')
                  AND (next_run_at IS NULL OR next_run_at <= ?)
                ORDER BY id ASC
                LIMIT ?
                """,
                (now.replace(microsecond=0).isoformat(), int(limit)),
            ).fetchall()
        return list(rows or [])

    def mark_running(self, task_id: int) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE execution_queue SET status='RUNNING', updated_at=? WHERE id=?",
                (now, int(task_id)),
            )

    def mark_done(self, task_id: int) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE execution_queue SET status='DONE', updated_at=? WHERE id=?",
                (now, int(task_id)),
            )

    def mark_defer(self, task_id: int, *, backoff_seconds: float, note: str = "") -> None:
        """Reschedule without incrementing attempts (e.g. limit entry still resting)."""
        now_dt = datetime.now(UTC).replace(microsecond=0)
        next_dt = now_dt + timedelta(seconds=float(backoff_seconds))
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE execution_queue
                SET status='RETRY', updated_at=?, next_run_at=?, last_error=?
                WHERE id=?
                """,
                (now_dt.isoformat(), next_dt.isoformat(), str(note)[:500], int(task_id)),
            )

    def mark_retry(self, task_id: int, *, error: str, backoff_seconds: float) -> None:
        now_dt = datetime.now(UTC).replace(microsecond=0)
        next_dt = now_dt + timedelta(seconds=float(backoff_seconds))
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE execution_queue
                SET status='RETRY', attempts=attempts+1, updated_at=?, next_run_at=?, last_error=?
                WHERE id=?
                """,
                (now_dt.isoformat(), next_dt.isoformat(), str(error)[:500], int(task_id)),
            )

    def mark_failed(self, task_id: int, *, error: str) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE execution_queue SET status='FAILED', updated_at=?, last_error=? WHERE id=?",
                (now, str(error)[:500], int(task_id)),
            )

    def count_pending(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM execution_queue WHERE status IN ('PENDING','RETRY','RUNNING')",
            ).fetchone()
        return int(row["n"] or 0)

