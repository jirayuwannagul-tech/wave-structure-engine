"""SQLite-backed store for managed client accounts."""

from __future__ import annotations

import datetime
import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime as dt
from pathlib import Path


def _utc_now() -> str:
    return dt.now(UTC).replace(microsecond=0).isoformat()


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


def _mask(value: str) -> str:
    if not value or len(value) < 8:
        return "****"
    return value[:4] + "****" + value[-4:]


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}:{h.hex()}"


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        salt, h = password_hash.split(":", 1)
        expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
        return expected.hex() == h
    except Exception:
        return False


def _get_fernet():
    key = os.getenv("API_ENCRYPT_KEY", "")
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode())
    except Exception:
        return None


def _encrypt(value: str) -> str:
    if not value:
        return value
    f = _get_fernet()
    if not f:
        return value
    return f.encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    if not value:
        return value
    f = _get_fernet()
    if not f:
        return value
    try:
        return f.decrypt(value.encode()).decode()
    except Exception:
        return value  # plaintext fallback for migration


@dataclass
class Account:
    id: int
    label: str
    email: str
    api_key: str
    api_secret: str
    token: str
    active: bool
    created_at: str
    activated_at: str | None
    note: str | None
    paid_until: str | None
    role: str  # 'admin' or 'member'
    password_hash: str

    @property
    def api_key_masked(self) -> str:
        return _mask(self.api_key)

    @property
    def payment_status(self) -> str:
        if self.role == "admin":
            return "admin"
        if not self.paid_until:
            return "unpaid"
        today = datetime.date.today().isoformat()
        return "paid" if self.paid_until >= today else "overdue"

    @property
    def days_remaining(self) -> int:
        if not self.paid_until:
            return 0
        try:
            delta = datetime.date.fromisoformat(self.paid_until) - datetime.date.today()
            return delta.days
        except Exception:
            return 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "email": self.email,
            "token": self.token,
            "active": self.active,
            "role": self.role,
            "created_at": self.created_at,
            "activated_at": self.activated_at,
            "note": self.note,
            "paid_until": self.paid_until,
            "payment_status": self.payment_status,
            "days_remaining": self.days_remaining,
            "api_key_masked": self.api_key_masked,
            "has_api_key": bool(self.api_key),
        }


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
                    label        TEXT NOT NULL DEFAULT '',
                    email        TEXT NOT NULL DEFAULT '',
                    api_key      TEXT NOT NULL DEFAULT '',
                    api_secret   TEXT NOT NULL DEFAULT '',
                    token        TEXT NOT NULL UNIQUE,
                    active       INTEGER NOT NULL DEFAULT 0,
                    role         TEXT NOT NULL DEFAULT 'member',
                    created_at   TEXT NOT NULL,
                    activated_at TEXT,
                    paid_until   TEXT,
                    note         TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_token ON accounts(token)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_active ON accounts(active)")
            # migrate existing tables that may lack new columns
            for col, definition in [
                ("email", "TEXT NOT NULL DEFAULT ''"),
                ("paid_until", "TEXT"),
                ("role", "TEXT NOT NULL DEFAULT 'member'"),
                ("password_hash", "TEXT NOT NULL DEFAULT ''"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE accounts ADD COLUMN {col} {definition}")
                except Exception:
                    pass

    def _row_to_account(self, row) -> Account:
        return Account(
            id=row["id"],
            label=row["label"] or "",
            email=row["email"] or "",
            api_key=_decrypt(row["api_key"] or ""),
            api_secret=_decrypt(row["api_secret"] or ""),
            token=row["token"],
            active=bool(row["active"]),
            created_at=row["created_at"],
            activated_at=row["activated_at"],
            note=row["note"],
            paid_until=row["paid_until"],
            role=row["role"] or "member",
            password_hash=row["password_hash"] or "",
        )

    def seed_admin(self, email: str) -> Account:
        """Create admin account if none exists. Safe to call multiple times."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE role='admin' LIMIT 1").fetchone()
            if row:
                return self._row_to_account(row)
            token = _generate_token()
            now = _utc_now()
            cur = conn.execute(
                """INSERT INTO accounts (label, email, api_key, api_secret, token, active, role, created_at)
                   VALUES (?, ?, ?, ?, ?, 1, 'admin', ?)""",
                ("Admin", email, "", "", token, now),
            )
            row_id = cur.lastrowid
        return self.get_by_id(row_id)

    def register(self, email: str, password: str) -> Account:
        """Step 1: create account with email + password only (no API key yet)."""
        token = _generate_token()
        now = _utc_now()
        pw_hash = _hash_password(password)
        label = email.split("@")[0]
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO accounts (label, email, api_key, api_secret, token, active, role, created_at, password_hash)
                   VALUES (?, ?, ?, ?, ?, 0, 'member', ?, ?)""",
                (label, email.strip().lower(), "", "", token, now, pw_hash),
            )
            row_id = cur.lastrowid
        return self.get_by_id(row_id)

    def verify_password(self, email: str, password: str) -> Account | None:
        acc = self.get_by_email(email)
        if acc and _verify_password(password, acc.password_hash):
            return acc
        return None

    def create(self, label: str, email: str, api_key: str, api_secret: str, note: str | None = None) -> Account:
        token = _generate_token()
        now = _utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO accounts (label, email, api_key, api_secret, token, active, role, created_at, note)
                   VALUES (?, ?, ?, ?, ?, 0, 'member', ?, ?)""",
                (label.strip(), email.strip().lower(), _encrypt(api_key.strip()), _encrypt(api_secret.strip()), token, now, note),
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

    def get_by_email(self, email: str) -> Account | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE email = ?", (email.strip().lower(),)).fetchone()
        return self._row_to_account(row) if row else None

    def list_all(self) -> list[Account]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM accounts ORDER BY role DESC, created_at DESC").fetchall()
        return [self._row_to_account(r) for r in rows]

    def list_active(self) -> list[Account]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM accounts WHERE active = 1 ORDER BY created_at DESC"
            ).fetchall()
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
            cur = conn.execute("UPDATE accounts SET active = 0 WHERE id = ?", (account_id,))
        return cur.rowcount > 0

    def mark_paid(self, account_id: int, months: int = 1) -> bool:
        """Extend paid_until by N months from today (or from current paid_until if still future)."""
        acc = self.get_by_id(account_id)
        if not acc:
            return False
        today = datetime.date.today()
        try:
            base = datetime.date.fromisoformat(acc.paid_until) if acc.paid_until else today
            if base < today:
                base = today
        except Exception:
            base = today
        new_date = base + datetime.timedelta(days=30 * months)
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE accounts SET paid_until = ? WHERE id = ?",
                (new_date.isoformat(), account_id),
            )
        return cur.rowcount > 0

    def update_api_key(self, account_id: int, api_key: str, api_secret: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE accounts SET api_key = ?, api_secret = ? WHERE id = ?",
                (_encrypt(api_key.strip()), _encrypt(api_secret.strip()), account_id),
            )
        return cur.rowcount > 0

    def delete(self, account_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        return cur.rowcount > 0

    def update_note(self, account_id: int, note: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE accounts SET note = ? WHERE id = ?", (note, account_id)
            )
        return cur.rowcount > 0
