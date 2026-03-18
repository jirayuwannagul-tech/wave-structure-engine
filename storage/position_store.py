"""SQLite persistence for live exchange positions (separate from paper signal lifecycle)."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _json_dump(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


class PositionStore:
    """Stores exchange_positions, exchange_position_orders, exchange_position_events."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.getenv("WAVE_DB_PATH", "storage/wave_engine.db")
        self._ensure_tables()

    @contextmanager
    def _connect(self):
        path = Path(self.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
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
                CREATE TABLE IF NOT EXISTS exchange_positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_signal_id INTEGER,
                    signal_hash TEXT,
                    quantity REAL NOT NULL,
                    entry_price REAL,
                    entry_order_id INTEGER,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    close_reason TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_exchange_positions_symbol_status
                ON exchange_positions(symbol, status);

                CREATE INDEX IF NOT EXISTS idx_exchange_positions_signal
                ON exchange_positions(source_signal_id);

                CREATE TABLE IF NOT EXISTS exchange_position_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    position_id INTEGER NOT NULL,
                    client_order_id TEXT,
                    order_id INTEGER,
                    order_kind TEXT NOT NULL,
                    side TEXT,
                    order_type TEXT,
                    quantity REAL,
                    stop_price REAL,
                    status TEXT NOT NULL DEFAULT 'NEW',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(position_id) REFERENCES exchange_positions(id)
                );

                CREATE INDEX IF NOT EXISTS idx_exchange_position_orders_position
                ON exchange_position_orders(position_id);

                CREATE TABLE IF NOT EXISTS exchange_position_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    position_id INTEGER NOT NULL,
                    event_time TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    details_json TEXT,
                    FOREIGN KEY(position_id) REFERENCES exchange_positions(id)
                );

                CREATE INDEX IF NOT EXISTS idx_exchange_position_events_position
                ON exchange_position_events(position_id);
                """
            )
            self._ensure_column(conn, "exchange_positions", "stop_loss_price", "REAL")
            self._ensure_column(conn, "exchange_positions", "recovered", "INTEGER DEFAULT 0")
            self._ensure_column(conn, "exchange_position_orders", "reduce_only", "INTEGER DEFAULT 1")

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        table: str,
        column: str,
        col_type: str,
    ) -> None:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")

    def has_open_position_for_signal(self, signal_id: int) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM exchange_positions
                WHERE source_signal_id = ? AND status = 'OPEN'
                LIMIT 1
                """,
                (int(signal_id),),
            ).fetchone()
        return row is not None

    def has_open_position_for_symbol(self, symbol: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM exchange_positions
                WHERE symbol = ? AND status = 'OPEN'
                LIMIT 1
                """,
                (symbol.upper(),),
            ).fetchone()
        return row is not None

    def create_position(
        self,
        *,
        symbol: str,
        side: str,
        source_signal_id: int | None,
        signal_hash: str | None,
        quantity: float,
        entry_price: float | None,
        entry_order_id: int | None,
        stop_loss_price: float | None = None,
        recovered: int = 0,
    ) -> int:
        now = _utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO exchange_positions (
                    created_at, updated_at, symbol, side, status,
                    source_signal_id, signal_hash, quantity, entry_price,
                    entry_order_id, opened_at, stop_loss_price, recovered
                ) VALUES (?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    now,
                    symbol.upper(),
                    side.upper(),
                    source_signal_id,
                    signal_hash,
                    float(quantity),
                    entry_price,
                    entry_order_id,
                    now,
                    stop_loss_price,
                    int(recovered),
                ),
            )
            pid = int(cur.lastrowid)
            conn.execute(
                """
                INSERT INTO exchange_position_events (position_id, event_time, event_type, details_json)
                VALUES (?, ?, ?, ?)
                """,
                (pid, now, "POSITION_OPENED", _json_dump({"quantity": quantity, "entry_price": entry_price})),
            )
            return pid

    def append_event(self, position_id: int, event_type: str, details: dict | None = None) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO exchange_position_events (position_id, event_time, event_type, details_json)
                VALUES (?, ?, ?, ?)
                """,
                (position_id, now, event_type, _json_dump(details or {})),
            )
            conn.execute(
                "UPDATE exchange_positions SET updated_at = ? WHERE id = ?",
                (now, position_id),
            )

    def record_order(
        self,
        position_id: int,
        *,
        order_kind: str,
        order_id: int | None,
        client_order_id: str | None,
        side: str | None,
        order_type: str,
        quantity: float | None,
        stop_price: float | None,
        status: str = "NEW",
        reduce_only: bool = True,
    ) -> int:
        now = _utc_now()
        ro = 1 if reduce_only else 0
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO exchange_position_orders (
                    position_id, client_order_id, order_id, order_kind, side, order_type,
                    quantity, stop_price, status, reduce_only, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    position_id,
                    client_order_id,
                    order_id,
                    order_kind,
                    side,
                    order_type,
                    quantity,
                    stop_price,
                    status,
                    ro,
                    now,
                    now,
                ),
            )
            return int(cur.lastrowid)

    def update_order_exchange_id(self, row_id: int, order_id: int) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE exchange_position_orders
                SET order_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (order_id, now, row_id),
            )

    def close_position(self, position_id: int, reason: str) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE exchange_positions
                SET status = 'CLOSED', closed_at = ?, close_reason = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, reason, now, position_id),
            )
            conn.execute(
                """
                INSERT INTO exchange_position_events (position_id, event_time, event_type, details_json)
                VALUES (?, ?, ?, ?)
                """,
                (position_id, now, "POSITION_CLOSED", _json_dump({"reason": reason})),
            )

    def get_open_position_by_symbol(self, symbol: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT * FROM exchange_positions
                WHERE symbol = ? AND status = 'OPEN'
                ORDER BY id DESC LIMIT 1
                """,
                (symbol.upper(),),
            ).fetchone()

    def get_open_position_by_signal(self, signal_id: int) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT * FROM exchange_positions
                WHERE source_signal_id = ? AND status = 'OPEN'
                ORDER BY id DESC LIMIT 1
                """,
                (int(signal_id),),
            ).fetchone()

    def update_order_status_by_kind(
        self,
        position_id: int,
        order_kind: str,
        status: str,
    ) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE exchange_position_orders
                SET status = ?, updated_at = ?
                WHERE id = (
                    SELECT id FROM exchange_position_orders
                    WHERE position_id = ? AND order_kind = ?
                    ORDER BY id DESC LIMIT 1
                )
                """,
                (status, now, position_id, order_kind),
            )

    def update_stop_loss_price(self, position_id: int, stop_loss_price: float) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE exchange_positions
                SET stop_loss_price = ?, updated_at = ? WHERE id = ?
                """,
                (stop_loss_price, now, position_id),
            )

    def update_position_order_row_status(self, order_row_id: int, status: str) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE exchange_position_orders
                SET status = ?, updated_at = ? WHERE id = ?
                """,
                (status, now, int(order_row_id)),
            )

    def list_open_protective_orders(self, position_id: int) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT * FROM exchange_position_orders
                WHERE position_id = ? AND order_kind IN ('SL', 'TP1', 'TP2', 'TP3')
                ORDER BY id ASC
                """,
                (position_id,),
            ).fetchall()
