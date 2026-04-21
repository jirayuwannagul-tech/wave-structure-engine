"""SQLite-backed store for managed client accounts."""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


def _mask(value: str) -> str:
    """Return first 4 + last 4 chars with middle masked."""
    if not value or len(value) < 8:
        return "****"
    return value[:4] + "****" + value[-4:]


@dataclass
class Account:
    id: int
    label: str
    api_key: str
    api_secret: str
    token: str
    active: bool
    created_at: str
    activated_at: str | None
    note: str | None

    @property
    def api_key_masked(self) -> str:
        return _mask(self.api_key)

    def to_dict(self, include_secrets: bool = False) -> dict:
        d = {
            "id": self.id,
            "label": self.label,
            "token": self.token,
            "active": self.active,
            "created_at": self.created_at,
            "activated_at": self.activated_at,
            "note": self.note,
            "api_key_masked": self.api_key_masked,
        }
        if include_secrets:
            d["api_key"] = self.api_key
            d["api_secret"] = self.api_secret
        return d


class AccountStore:
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
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_tables(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    label        TEXT NOT NULL,
                    api_key      TEXT NOT NULL,
                    api_secret   TEXT NOT NULL,
                    token        TEXT NOT NULL UNIQUE,
                    active       INTEGER NOT NULL DEFAULT 0,
                    created_at   TEXT NOT NULL,
                    activated_at TEXT,
                    note         TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_token ON accounts(token)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_active ON accounts(active)")

    def _row_to_account(self, row) -> Account:
        return Account(
            id=row["id"],
            label=row["label"],
            api_key=row["api_key"],
            api_secret=row["api_secret"],
            token=row["token"],
            active=bool(row["active"]),
            created_at=row["created_at"],
            activated_at=row["activated_at"],
            note=row["note"],
        )

    def create(self, label: str, api_key: str, api_secret: str, note: str | None = None) -> Account:
        token = _generate_token()
        now = _utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO accounts (label, api_key, api_secret, token, active, created_at, note)
                   VALUES (?, ?, ?, ?, 0, ?, ?)""",
                (label.strip(), api_key.strip(), api_secret.strip(), token, now, note),
            )
            row_id = cur.lastrowid
        return self.get_by_id(row_id)

    def get_by_id(self, account_id: int) -> Account | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return self._row_to_account(row) if row else None

    def get_by_token(self, token: str) -> Account | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE token = ?", (token,)).fetchone()
        return self._row_to_account(row) if row else None

    def list_all(self) -> list[Account]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM accounts ORDER BY created_at DESC").fetchall()
        return [self._row_to_account(r) for r in rows]

    def list_active(self) -> list[Account]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM accounts WHERE active = 1 ORDER BY created_at DESC").fetchall()
        return [self._row_to_account(r) for r in rows]

    def activate(self, account_id: int) -> bool:
        now = _utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE accounts SET active = 1, activated_at = ? WHERE id = ?",
                (now, account_id),
            )
        return cur.rowcount > 0

    def deactivate(self, account_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE accounts SET active = 0 WHERE id = ?",
                (account_id,),
            )
        return cur.rowcount > 0

    def delete(self, account_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        return cur.rowcount > 0

    def update_note(self, account_id: int, note: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE accounts SET note = ? WHERE id = ?",
                (note, account_id),
            )
        return cur.rowcount > 0
