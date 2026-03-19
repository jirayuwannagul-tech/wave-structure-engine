from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import traceback
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from analysis.trade_management import (
    evaluate_live_entry_actionability,
    managed_stop_after_target,
    time_stop_bars_for_timeframe,
    volatility_spike_against_position,
)
from scenarios.scenario_state_machine import update_scenario_state
from analysis.risk_reward import calculate_rr_levels

OPEN_SIGNAL_STATUSES = {
    "PENDING_ENTRY",
    "ACTIVE",
    "PARTIAL_TP1",
    "PARTIAL_TP2",
}

SYNCABLE_SIGNAL_STATUSES = {
    "ACTIVE",
    "PARTIAL_TP1",
    "PARTIAL_TP2",
    "TP3_HIT",
    "STOPPED",
}

_OPEN_STATUS_SQL = ",".join(f"'{s}'" for s in sorted(OPEN_SIGNAL_STATUSES))


def _env_truthy(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in ("1", "true", "yes", "on")


def _env_entry_style() -> str:
    raw = (os.getenv("BINANCE_ENTRY_STYLE") or "signal_price").strip().lower()
    if raw in {"market", "m", "immediate"}:
        return "market"
    if raw in {"signal", "signal_price", "entry", "limit", "planned", "plan"}:
        return "signal_price"
    return "signal_price"


def _exchange_managed_signal_entry_enabled() -> bool:
    """True when Binance owns the real fill timing for signal entries."""
    return (
        _env_truthy("BINANCE_EXECUTION_ENABLED")
        and _env_truthy("BINANCE_LIVE_ORDER_ENABLED")
        and _env_entry_style() == "signal_price"
    )


def _signals_entry_only_enabled() -> bool:
    """When true, only persist signals after entry is triggered (no PENDING_ENTRY rows)."""
    if _exchange_managed_signal_entry_enabled():
        # In signal-price execution mode we need a durable PENDING_ENTRY row so Binance can
        # own the actual fill and we can align DB/Sheet/TG to that exchange fill.
        return False
    raw = os.getenv("SIGNALS_ENTRY_ONLY")
    if raw is None or str(raw).strip() == "":
        # Default to entry-only: user wants only actionable signals persisted/synced.
        return True
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _signal_gate_terminal_exit_enabled() -> bool:
    raw = os.getenv("SIGNAL_GATE_TERMINAL_EXIT")
    if raw is None or str(raw).strip() == "":
        # Default to one open trade plan per symbol until it reaches a terminal exit.
        return True
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _parse_iso_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _round_price(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def _json_dump(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _signal_side(bias: str | None) -> str | None:
    if (bias or "").upper() == "BULLISH":
        return "LONG"
    if (bias or "").upper() == "BEARISH":
        return "SHORT"
    return None


def _simplify_scenario(scenario) -> dict:
    return {
        "name": getattr(scenario, "name", None),
        "bias": getattr(scenario, "bias", None),
        "condition": getattr(scenario, "condition", None),
        "confirmation": _round_price(getattr(scenario, "confirmation", None)),
        "invalidation": _round_price(getattr(scenario, "invalidation", None)),
        "stop_loss": _round_price(getattr(scenario, "stop_loss", None)),
        "targets": [_round_price(x) for x in list(getattr(scenario, "targets", []) or [])],
    }


def _execution_scenarios(analysis: dict) -> list:
    if "execution_scenarios" in analysis:
        return list(analysis.get("execution_scenarios") or [])
    return list(analysis.get("scenarios") or [])


def _select_actionable_scenario(
    analysis: dict,
    *,
    current_price: float | None = None,
):
    scenarios = _execution_scenarios(analysis)
    if not scenarios:
        return None

    current = _round_price(
        current_price if current_price is not None else analysis.get("current_price")
    )
    entry_style = "signal_price" if _exchange_managed_signal_entry_enabled() else "market"
    for scenario in scenarios:
        bias = getattr(scenario, "bias", None)
        side = _signal_side(bias)
        if side is None:
            continue
        decision = evaluate_live_entry_actionability(
            side=side,
            planned_entry=getattr(scenario, "confirmation", None),
            stop_loss=getattr(scenario, "stop_loss", None),
            current_price=current,
            entry_style=entry_style,
            invalidation_price=getattr(scenario, "invalidation", None),
        )
        if decision.actionable:
            return scenario
        # Market-style setups can still be a valid pending plan before the
        # confirmation level is crossed. We only want to discard stale or
        # invalidated plans here.
        if decision.reason == "not_confirmed" and decision.entry_style == "market":
            return scenario
    return None


def build_signal_snapshot(analysis: dict, current_price: float | None = None) -> dict | None:
    scenario = _select_actionable_scenario(analysis, current_price=current_price)
    if scenario is None:
        return None

    bias = getattr(scenario, "bias", None)
    side = _signal_side(bias)
    entry = _round_price(getattr(scenario, "confirmation", None))
    stop_loss = _round_price(getattr(scenario, "stop_loss", None))
    targets = [_round_price(x) for x in list(getattr(scenario, "targets", []) or [])]

    if side is None or entry is None or stop_loss is None:
        return None

    if side == "LONG" and stop_loss >= entry:
        return None
    if side == "SHORT" and stop_loss <= entry:
        return None

    while len(targets) < 3:
        targets.append(None)

    rr_levels = calculate_rr_levels(
        side=side,
        entry_price=entry,
        stop_loss=stop_loss,
        tp1=targets[0],
        tp2=targets[1],
        tp3=targets[2],
    )

    position = analysis.get("position")
    payload = {
        "symbol": analysis.get("symbol"),
        "timeframe": analysis.get("timeframe"),
        "pattern_type": analysis.get("primary_pattern_type"),
        "scenario_name": getattr(scenario, "name", None),
        "bias": bias,
        "side": side,
        "entry_price": entry,
        "stop_loss": stop_loss,
        "tp1": targets[0],
        "tp2": targets[1],
        "tp3": targets[2],
        "rr_tp1": rr_levels["rr_tp1"],
        "rr_tp2": rr_levels["rr_tp2"],
        "rr_tp3": rr_levels["rr_tp3"],
        "invalidation_price": _round_price(getattr(scenario, "invalidation", None)),
        "position_structure": getattr(position, "structure", None),
        "position_label": getattr(position, "position", None),
        "position_bias": getattr(position, "bias", None),
        "analysis_summary": {
            "current_price": _round_price(
                current_price if current_price is not None else analysis.get("current_price")
            ),
            "pattern_type": analysis.get("primary_pattern_type"),
            "scenario": _simplify_scenario(scenario),
            "rr_levels": rr_levels,
        },
    }
    return payload


def build_signal_hash(snapshot: dict) -> str:
    identity = {
        "symbol": snapshot.get("symbol"),
        "timeframe": snapshot.get("timeframe"),
        "pattern_type": snapshot.get("pattern_type"),
        "scenario_name": snapshot.get("scenario_name"),
        "bias": snapshot.get("bias"),
        "entry_price": snapshot.get("entry_price"),
        "stop_loss": snapshot.get("stop_loss"),
        "tp1": snapshot.get("tp1"),
        "tp2": snapshot.get("tp2"),
        "tp3": snapshot.get("tp3"),
        "invalidation_price": snapshot.get("invalidation_price"),
    }
    return hashlib.sha256(_json_dump(identity).encode("utf-8")).hexdigest()


class WaveRepository:
    """SQLite-backed store for Elliott Wave signals and analysis snapshots.

    Tracks the full lifecycle of each trading signal:
    PENDING_ENTRY → ACTIVE → PARTIAL_TP1 / PARTIAL_TP2 → TP3_HIT / STOPPED / INVALIDATED / REPLACED.
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.getenv("WAVE_DB_PATH", "storage/wave_engine.db")
        self._last_affected_signal_ids: list[int] = []
        self._initialize()

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

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS analysis_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    current_price REAL,
                    pattern_type TEXT,
                    scenario_name TEXT,
                    bias TEXT,
                    entry_price REAL,
                    stop_loss REAL,
                    tp1 REAL,
                    tp2 REAL,
                    tp3 REAL,
                    rr_tp1 REAL,
                    rr_tp2 REAL,
                    rr_tp3 REAL,
                    signal_hash TEXT,
                    summary_text TEXT,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    pattern_type TEXT,
                    scenario_name TEXT,
                    bias TEXT,
                    side TEXT,
                    status TEXT NOT NULL,
                    signal_hash TEXT NOT NULL UNIQUE,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    tp1 REAL,
                    tp2 REAL,
                    tp3 REAL,
                    rr_tp1 REAL,
                    rr_tp2 REAL,
                    rr_tp3 REAL,
                    invalidation_price REAL,
                    current_price REAL,
                    analysis_summary_json TEXT,
                    entry_triggered_at TEXT,
                    entry_triggered_price REAL,
                    tp1_hit_at TEXT,
                    tp1_hit_price REAL,
                    tp2_hit_at TEXT,
                    tp2_hit_price REAL,
                    tp3_hit_at TEXT,
                    tp3_hit_price REAL,
                    closed_at TEXT,
                    close_reason TEXT
                );

                CREATE TABLE IF NOT EXISTS signal_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id INTEGER NOT NULL,
                    event_time TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    price REAL,
                    details_json TEXT,
                    FOREIGN KEY(signal_id) REFERENCES signals(id)
                );

                CREATE INDEX IF NOT EXISTS idx_signals_symbol_timeframe
                ON signals(symbol, timeframe);

                CREATE INDEX IF NOT EXISTS idx_signals_status
                ON signals(status);

                CREATE INDEX IF NOT EXISTS idx_signal_events_signal_id
                ON signal_events(signal_id);

                CREATE TABLE IF NOT EXISTS market_candles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    open_time TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL,
                    close_time TEXT,
                    quote_asset_volume REAL,
                    number_of_trades INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(symbol, timeframe, open_time)
                );

                CREATE INDEX IF NOT EXISTS idx_market_candles_symbol_timeframe_open_time
                ON market_candles(symbol, timeframe, open_time);

                CREATE TABLE IF NOT EXISTS news_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    link TEXT NOT NULL,
                    published_at TEXT,
                    summary_text TEXT,
                    tag_text TEXT,
                    external_id TEXT NOT NULL UNIQUE
                );

                CREATE INDEX IF NOT EXISTS idx_news_items_external_id
                ON news_items(external_id);

                CREATE TABLE IF NOT EXISTS system_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    event_key TEXT NOT NULL UNIQUE,
                    details_json TEXT
                );
                """
            )
            self._ensure_column(conn, "analysis_snapshots", "rr_tp1", "REAL")
            self._ensure_column(conn, "analysis_snapshots", "rr_tp2", "REAL")
            self._ensure_column(conn, "analysis_snapshots", "rr_tp3", "REAL")
            self._ensure_column(conn, "signals", "rr_tp1", "REAL")
            self._ensure_column(conn, "signals", "rr_tp2", "REAL")
            self._ensure_column(conn, "signals", "rr_tp3", "REAL")

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_type: str,
    ) -> None:
        columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            conn.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            )

    def upsert_market_candles(self, symbol: str, timeframe: str, df) -> int:
        if df is None or len(df) == 0:
            return 0

        now = _utc_now()
        rows = []
        for _, row in df.iterrows():
            open_time = row["open_time"]
            close_time = row.get("close_time")
            rows.append(
                (
                    symbol.upper(),
                    timeframe.upper(),
                    open_time.isoformat() if hasattr(open_time, "isoformat") else str(open_time),
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    float(row["volume"]) if row.get("volume") is not None else None,
                    close_time.isoformat() if hasattr(close_time, "isoformat") else (str(close_time) if close_time is not None else None),
                    float(row["quote_asset_volume"]) if row.get("quote_asset_volume") is not None else None,
                    int(row["number_of_trades"]) if row.get("number_of_trades") is not None else None,
                    now,
                    now,
                )
            )

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO market_candles (
                    symbol, timeframe, open_time, open, high, low, close, volume,
                    close_time, quote_asset_volume, number_of_trades, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timeframe, open_time) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    close_time = excluded.close_time,
                    quote_asset_volume = excluded.quote_asset_volume,
                    number_of_trades = excluded.number_of_trades,
                    updated_at = excluded.updated_at
                """,
                rows,
            )
            conn.commit()

        return len(rows)

    def count_market_candles(self, symbol: str | None = None, timeframe: str | None = None) -> int:
        query = "SELECT COUNT(*) AS count FROM market_candles WHERE 1=1"
        params: list[str] = []
        if symbol is not None:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        if timeframe is not None:
            query += " AND timeframe = ?"
            params.append(timeframe.upper())

        with self._connect() as conn:
            row = conn.execute(query, tuple(params)).fetchone()
        return int(row["count"]) if row is not None else 0

    def fetch_active_signals(self, symbol: str | None = None) -> list[sqlite3.Row]:
        query = "SELECT * FROM signals WHERE status IN ({})".format(
            ",".join("?" for _ in OPEN_SIGNAL_STATUSES)
        )
        params: list[str] = list(OPEN_SIGNAL_STATUSES)
        if symbol is not None:
            query += " AND symbol = ?"
            params.append(symbol)
        query += " ORDER BY id ASC"

        with self._connect() as conn:
            return conn.execute(query, params).fetchall()

    def fetch_recent_syncable_signals(self, symbol: str, limit: int = 20) -> list[sqlite3.Row]:
        """Fetch recent signals that can be safely upserted to Google Sheets.

        This is used to recover sheet state if lifecycle tracking missed an event.
        """
        limit = max(1, int(limit))
        in_sql = ",".join("?" for _ in sorted(SYNCABLE_SIGNAL_STATUSES))
        params: list = [symbol.upper(), *sorted(SYNCABLE_SIGNAL_STATUSES), limit]
        query = f"""
            SELECT *
            FROM signals
            WHERE symbol = ?
              AND status IN ({in_sql})
            ORDER BY id DESC
            LIMIT ?
        """
        with self._connect() as conn:
            return conn.execute(query, tuple(params)).fetchall()

    def fetch_signal_events(self, signal_id: int) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM signal_events WHERE signal_id = ? ORDER BY id ASC",
                (signal_id,),
            ).fetchall()

    def fetch_signal(self, signal_id: int) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM signals WHERE id = ?",
                (signal_id,),
            ).fetchone()

    def close_open_signal(
        self,
        signal_id: int,
        *,
        status: str,
        close_reason: str,
        current_price: float | None = None,
        event_time: str | None = None,
        event_type: str,
    ) -> bool:
        now = event_time or _utc_now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status, current_price FROM signals WHERE id = ?",
                (int(signal_id),),
            ).fetchone()
            if row is None:
                return False
            prev_status = str(row["status"] or "").upper()
            if prev_status not in OPEN_SIGNAL_STATUSES:
                return False
            try:
                price_now = float(
                    current_price
                    if current_price is not None
                    else row["current_price"]
                )
            except (TypeError, ValueError):
                price_now = 0.0
            self._close_signal(
                conn,
                signal_id=int(signal_id),
                status=str(status).upper(),
                close_reason=str(close_reason),
                current_price=price_now,
                event_time=now,
                event_type=str(event_type).upper(),
            )
        return True

    def update_signal_entry_to_exchange_average(self, signal_id: int, avg_entry_price: float) -> bool:
        """After Binance entry fill: align signals.entry_price / entry_triggered_price with avg fill.

        Recalculates rr_tp1/2/3 from the new entry so Google Sheet rows stay consistent with the exchange.
        """
        try:
            ae = float(avg_entry_price)
        except (TypeError, ValueError):
            return False
        if ae <= 0:
            return False
        now = _utc_now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT side, stop_loss, tp1, tp2, tp3 FROM signals WHERE id = ?",
                (int(signal_id),),
            ).fetchone()
            if row is None:
                return False
            try:
                sl = float(row["stop_loss"])
            except (TypeError, ValueError):
                return False
            rr = calculate_rr_levels(
                row["side"],
                ae,
                sl,
                row["tp1"],
                row["tp2"],
                row["tp3"],
            )
            conn.execute(
                """
                UPDATE signals
                SET entry_price = ?,
                    entry_triggered_price = ?,
                    rr_tp1 = ?,
                    rr_tp2 = ?,
                    rr_tp3 = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    ae,
                    ae,
                    rr.get("rr_tp1"),
                    rr.get("rr_tp2"),
                    rr.get("rr_tp3"),
                    now,
                    int(signal_id),
                ),
            )
        return True

    def mark_signal_entry_filled_from_exchange(
        self,
        signal_id: int,
        avg_entry_price: float,
        *,
        event_time: str | None = None,
    ) -> bool:
        """Promote a pending signal to ACTIVE once Binance confirms the entry fill."""
        try:
            ae = float(avg_entry_price)
        except (TypeError, ValueError):
            return False
        if ae <= 0:
            return False

        now = event_time or _utc_now()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT status, side, stop_loss, tp1, tp2, tp3
                FROM signals
                WHERE id = ?
                """,
                (int(signal_id),),
            ).fetchone()
            if row is None:
                return False

            prev_status = str(row["status"] or "").upper()
            if prev_status not in OPEN_SIGNAL_STATUSES:
                return False

            try:
                sl = float(row["stop_loss"])
            except (TypeError, ValueError):
                return False

            rr = calculate_rr_levels(
                row["side"],
                ae,
                sl,
                row["tp1"],
                row["tp2"],
                row["tp3"],
            )
            conn.execute(
                """
                UPDATE signals
                SET status = CASE WHEN status = 'PENDING_ENTRY' THEN 'ACTIVE' ELSE status END,
                    updated_at = ?,
                    entry_price = ?,
                    entry_triggered_price = ?,
                    entry_triggered_at = COALESCE(entry_triggered_at, ?),
                    rr_tp1 = ?,
                    rr_tp2 = ?,
                    rr_tp3 = ?
                WHERE id = ?
                """,
                (
                    now,
                    ae,
                    ae,
                    now,
                    rr.get("rr_tp1"),
                    rr.get("rr_tp2"),
                    rr.get("rr_tp3"),
                    int(signal_id),
                ),
            )
            if prev_status == "PENDING_ENTRY":
                self._insert_event(
                    conn,
                    signal_id=int(signal_id),
                    event_type="ENTRY_TRIGGERED",
                    price=ae,
                    details={"status": "ACTIVE", "source": "BINANCE_FILL"},
                    event_time=now,
                )
        return True

    def has_news_item(self, external_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM news_items WHERE external_id = ?",
                (external_id,),
            ).fetchone()
        return row is not None

    def has_system_event(self, event_key: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM system_events WHERE event_key = ?",
                (event_key,),
            ).fetchone()
        return row is not None

    def record_system_event(self, event_key: str, details: dict | None = None) -> int | None:
        if self.has_system_event(event_key):
            return None

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO system_events (created_at, event_key, details_json)
                VALUES (?, ?, ?)
                """,
                (_utc_now(), event_key, _json_dump(details or {})),
            )
            return int(cursor.lastrowid)

    def record_news_item(
        self,
        *,
        source: str,
        title: str,
        link: str,
        published_at: str | None,
        summary_text: str | None,
        tag_text: str | None,
        external_id: str,
    ) -> int | None:
        if self.has_news_item(external_id):
            return None

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO news_items (
                    created_at, source, title, link, published_at,
                    summary_text, tag_text, external_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _utc_now(),
                    source,
                    title,
                    link,
                    published_at,
                    summary_text,
                    tag_text,
                    external_id,
                ),
            )
            return int(cursor.lastrowid)

    def record_analysis_snapshot(self, analysis: dict, current_price: float | None = None) -> int:
        snapshot = build_signal_snapshot(analysis, current_price=current_price)
        current = _round_price(current_price if current_price is not None else analysis.get("current_price"))
        payload = {
            "symbol": analysis.get("symbol"),
            "timeframe": analysis.get("timeframe"),
            "pattern_type": analysis.get("primary_pattern_type"),
            "current_price": current,
            "position": {
                "structure": getattr(analysis.get("position"), "structure", None),
                "position": getattr(analysis.get("position"), "position", None),
                "bias": getattr(analysis.get("position"), "bias", None),
            },
            "scenario": snapshot,
        }

        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO analysis_snapshots (
                        created_at, symbol, timeframe, current_price, pattern_type,
                        scenario_name, bias, entry_price, stop_loss, tp1, tp2, tp3,
                        rr_tp1, rr_tp2, rr_tp3, signal_hash, summary_text, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _utc_now(),
                        analysis.get("symbol"),
                        analysis.get("timeframe"),
                        current,
                        analysis.get("primary_pattern_type"),
                        snapshot.get("scenario_name") if snapshot else None,
                        snapshot.get("bias") if snapshot else None,
                        snapshot.get("entry_price") if snapshot else None,
                        snapshot.get("stop_loss") if snapshot else None,
                        snapshot.get("tp1") if snapshot else None,
                        snapshot.get("tp2") if snapshot else None,
                        snapshot.get("tp3") if snapshot else None,
                        snapshot.get("rr_tp1") if snapshot else None,
                        snapshot.get("rr_tp2") if snapshot else None,
                        snapshot.get("rr_tp3") if snapshot else None,
                        build_signal_hash(snapshot) if snapshot else None,
                        self._build_summary_text(snapshot),
                        _json_dump(payload),
                    ),
                )
                return int(cursor.lastrowid)
        except sqlite3.Error as exc:
            print(f"[wave_repository] record_analysis_snapshot failed: {exc}")
            traceback.print_exc()
            return -1

    def _signal_gate_blocks_new(self, conn: sqlite3.Connection, snapshot: dict) -> bool:
        """When enabled, block INSERT of a new signal until open trades exit via SL or TP3.

        Open = PENDING_ENTRY / ACTIVE / PARTIAL_TP*. Terminal exits (TP3_HIT, STOPPED, etc.)
        are not open, so a new row is allowed after those.

        - SIGNAL_GATE_TERMINAL_EXIT: master switch.
        Behavior (when enabled): at most one open signal per symbol (across all timeframes).
        This enforces: "เหลือแค่ 1 สัญญาณเปิดต่อเหรียญ (ทุก timeframe)" until SL or TP3.
        """
        if not _signal_gate_terminal_exit_enabled():
            return False

        sym = (snapshot.get("symbol") or "").strip().upper()
        if not sym:
            return False

        row = conn.execute(
            f"""
            SELECT id FROM signals
            WHERE UPPER(TRIM(symbol)) = ?
              AND status IN ({_OPEN_STATUS_SQL})
            LIMIT 1
            """,
            (sym,),
        ).fetchone()
        return row is not None

    def sync_analysis(self, analysis: dict, current_price: float | None = None) -> int | None:
        self.record_analysis_snapshot(analysis, current_price=current_price)
        snapshot = build_signal_snapshot(analysis, current_price=current_price)
        if snapshot is None:
            self._last_affected_signal_ids = []
            return None

        snapshot["current_price"] = _round_price(
            current_price if current_price is not None else analysis.get("current_price")
        )
        signal_hash = build_signal_hash(snapshot)
        now = _utc_now()
        self._last_affected_signal_ids = []

        try:
            with self._connect() as conn:
                existing = conn.execute(
                    "SELECT id, status FROM signals WHERE signal_hash = ?",
                    (signal_hash,),
                ).fetchone()

                if existing is not None:
                    conn.execute(
                        """
                        UPDATE signals
                        SET updated_at = ?,
                            current_price = ?,
                            tp1 = ?,
                            tp2 = ?,
                            tp3 = ?,
                            rr_tp1 = ?,
                            rr_tp2 = ?,
                            rr_tp3 = ?,
                            analysis_summary_json = ?
                        WHERE id = ?
                        """,
                        (
                            now,
                            snapshot.get("current_price"),
                            snapshot["tp1"],
                            snapshot["tp2"],
                            snapshot["tp3"],
                            snapshot["rr_tp1"],
                            snapshot["rr_tp2"],
                            snapshot["rr_tp3"],
                            _json_dump(snapshot["analysis_summary"]),
                            existing["id"],
                        ),
                    )
                    self._last_affected_signal_ids = [int(existing["id"])]
                    return int(existing["id"])

                # Entry-only mode: do not persist non-actionable plans.
                if _signals_entry_only_enabled():
                    side = snapshot.get("side")
                    entry = snapshot.get("entry_price")
                    cp = snapshot.get("current_price")
                    if side and entry is not None and cp is not None:
                        if not self._entry_crossed(str(side), float(cp), float(entry)):
                            self._last_affected_signal_ids = []
                            return None
                    else:
                        self._last_affected_signal_ids = []
                        return None

                if self._signal_gate_blocks_new(conn, snapshot):
                    self._last_affected_signal_ids = []
                    return None

                replaced_ids = self._replace_pending_signals(
                    conn,
                    symbol=snapshot["symbol"],
                    timeframe=snapshot["timeframe"],
                    replacement_hash=signal_hash,
                    event_time=now,
                )

                cursor = conn.execute(
                    """
                    INSERT INTO signals (
                        created_at, updated_at, symbol, timeframe, pattern_type, scenario_name,
                        bias, side, status, signal_hash, entry_price, stop_loss, tp1, tp2, tp3,
                        rr_tp1, rr_tp2, rr_tp3, invalidation_price, current_price, analysis_summary_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now,
                        now,
                        snapshot["symbol"],
                        snapshot["timeframe"],
                        snapshot["pattern_type"],
                        snapshot["scenario_name"],
                        snapshot["bias"],
                        snapshot["side"],
                        "ACTIVE" if _signals_entry_only_enabled() else "PENDING_ENTRY",
                        signal_hash,
                        snapshot["entry_price"],
                        snapshot["stop_loss"],
                        snapshot["tp1"],
                        snapshot["tp2"],
                        snapshot["tp3"],
                        snapshot["rr_tp1"],
                        snapshot["rr_tp2"],
                        snapshot["rr_tp3"],
                        snapshot["invalidation_price"],
                        snapshot.get("current_price"),
                        _json_dump(snapshot["analysis_summary"]),
                    ),
                )
                signal_id = int(cursor.lastrowid)

                if _signals_entry_only_enabled():
                    cp = snapshot.get("current_price")
                    conn.execute(
                        """
                        UPDATE signals
                        SET entry_triggered_at = ?,
                            entry_triggered_price = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (now, cp, now, signal_id),
                    )
                    self._insert_event(
                        conn,
                        signal_id=signal_id,
                        event_type="ENTRY_TRIGGERED",
                        price=cp,
                        details={"status": "ACTIVE", "source": "SYNC_ANALYSIS_ENTRY_ONLY"},
                        event_time=now,
                    )

                self._insert_event(
                    conn,
                    signal_id=signal_id,
                    event_type="SIGNAL_CREATED",
                    price=snapshot.get("current_price"),
                    details=snapshot,
                    event_time=now,
                )
                self._last_affected_signal_ids = [*replaced_ids, signal_id]
                return signal_id
        except sqlite3.Error as exc:
            print(f"[wave_repository] sync_analysis failed: {exc}")
            traceback.print_exc()
            self._last_affected_signal_ids = []
            return None

    def sync_runtime(self, runtime, current_price: float | None = None) -> list[int]:
        """Sync all analyses in a runtime to the database.

        Returns a flat list of affected signal IDs (new + updated + replaced).
        """
        signal_ids: list[int] = []
        for analysis in runtime.analyses:
            signal_id = self.sync_analysis(analysis, current_price=current_price)
            if signal_id is not None:
                signal_ids.extend(self._last_affected_signal_ids or [signal_id])
        return signal_ids

    def track_price_update(
        self,
        symbol: str,
        current_price: float,
        event_time: str | None = None,
        analyses: list[dict] | None = None,
    ) -> list[tuple[int, str]]:
        """Check current price against all open signals and update their lifecycle state.

        Returns a list of (signal_id, event_type) tuples for events that fired,
        e.g. [( 3, "ENTRY_TRIGGERED"), (3, "TP1_HIT")].
        Returns empty list on DB error (does not raise).
        """
        current = _round_price(current_price)
        now = event_time or _utc_now()
        events_created: list[tuple[int, str]] = []

        analysis_by_timeframe = {
            str(item.get("timeframe") or "").upper(): item
            for item in (analyses or [])
            if isinstance(item, dict)
        }

        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM signals
                    WHERE symbol = ?
                      AND status IN ('PENDING_ENTRY', 'ACTIVE', 'PARTIAL_TP1', 'PARTIAL_TP2')
                    ORDER BY id ASC
                    """,
                    (symbol,),
                ).fetchall()

                for row in rows:
                    signal_id = int(row["id"])
                    side = row["side"]
                    status = row["status"]
                    entry = float(row["entry_price"])
                    stop_loss = float(row["stop_loss"])
                    tp1 = row["tp1"]
                    tp2 = row["tp2"]
                    tp3 = row["tp3"]

                    conn.execute(
                        "UPDATE signals SET updated_at = ?, current_price = ? WHERE id = ?",
                        (now, current, signal_id),
                    )

                    if status == "PENDING_ENTRY":
                        if self._stop_crossed(side, current, stop_loss):
                            self._close_signal(
                                conn,
                                signal_id=signal_id,
                                status="INVALIDATED",
                                close_reason="STOP_LOSS_BEFORE_ENTRY",
                                current_price=current,
                                event_time=now,
                                event_type="STOP_LOSS_BEFORE_ENTRY",
                            )
                            events_created.append((signal_id, "STOP_LOSS_BEFORE_ENTRY"))
                            continue

                        if _exchange_managed_signal_entry_enabled():
                            # In signal-price execution mode a pending Binance order controls the
                            # real fill timing. Keep the signal pending until the exchange confirms
                            # the fill so DB/Sheet/TG stay aligned to Binance.
                            continue

                        if self._entry_crossed(side, current, entry):
                            risk = abs(entry - stop_loss)
                            if risk > 0:
                                if side == "LONG" and current > (entry + (risk * 0.35)):
                                    self._close_signal(
                                        conn,
                                        signal_id=signal_id,
                                        status="INVALIDATED",
                                        close_reason="OVEREXTENDED_ENTRY",
                                        current_price=current,
                                        event_time=now,
                                        event_type="ENTRY_SKIPPED",
                                    )
                                    events_created.append((signal_id, "ENTRY_SKIPPED"))
                                    continue
                                if side == "SHORT" and current < (entry - (risk * 0.35)):
                                    self._close_signal(
                                        conn,
                                        signal_id=signal_id,
                                        status="INVALIDATED",
                                        close_reason="OVEREXTENDED_ENTRY",
                                        current_price=current,
                                        event_time=now,
                                        event_type="ENTRY_SKIPPED",
                                    )
                                    events_created.append((signal_id, "ENTRY_SKIPPED"))
                                    continue
                            conn.execute(
                                """
                                UPDATE signals
                                SET status = 'ACTIVE',
                                    updated_at = ?,
                                    current_price = ?,
                                    entry_triggered_at = ?,
                                    entry_triggered_price = ?
                                WHERE id = ?
                                """,
                                (now, current, now, current, signal_id),
                            )
                            self._insert_event(
                                conn,
                                signal_id=signal_id,
                                event_type="ENTRY_TRIGGERED",
                                price=current,
                                details={"status": "ACTIVE"},
                                event_time=now,
                            )
                            events_created.append((signal_id, "ENTRY_TRIGGERED"))
                            status = "ACTIVE"

                    if status in {"ACTIVE", "PARTIAL_TP1", "PARTIAL_TP2"}:
                        if tp1 is not None and row["tp1_hit_at"] is None and self._target_crossed(side, current, float(tp1)):
                            self._mark_target_hit(conn, signal_id, "TP1", current, now, "PARTIAL_TP1")
                            moved_stop = managed_stop_after_target(
                                side=side,
                                current_stop=stop_loss,
                                entry_price=float(row["entry_triggered_price"] or entry),
                                tp1=tp1,
                                target_label="TP1",
                            )
                            if moved_stop != stop_loss:
                                self._update_stop_loss(conn, signal_id, moved_stop, now)
                            events_created.append((signal_id, "TP1_HIT"))
                            row = self._refresh_row(conn, signal_id)
                            status = row["status"]
                            stop_loss = float(row["stop_loss"])

                        if tp2 is not None and row["tp2_hit_at"] is None and self._target_crossed(side, current, float(tp2)):
                            self._mark_target_hit(conn, signal_id, "TP2", current, now, "PARTIAL_TP2")
                            moved_stop = managed_stop_after_target(
                                side=side,
                                current_stop=stop_loss,
                                entry_price=float(row["entry_triggered_price"] or entry),
                                tp1=tp1,
                                target_label="TP2",
                            )
                            if moved_stop != stop_loss:
                                self._update_stop_loss(conn, signal_id, moved_stop, now)
                            events_created.append((signal_id, "TP2_HIT"))
                            row = self._refresh_row(conn, signal_id)
                            status = row["status"]
                            stop_loss = float(row["stop_loss"])

                        if tp3 is not None and row["tp3_hit_at"] is None and self._target_crossed(side, current, float(tp3)):
                            self._mark_target_hit(conn, signal_id, "TP3", current, now, "TP3_HIT")
                            self._close_signal(
                                conn,
                                signal_id=signal_id,
                                status="TP3_HIT",
                                close_reason="TAKE_PROFIT_3",
                                current_price=current,
                                event_time=now,
                                event_type="SIGNAL_CLOSED",
                            )
                            events_created.append((signal_id, "TP3_HIT"))
                            continue

                        if self._stop_crossed(side, current, stop_loss):
                            self._close_signal(
                                conn,
                                signal_id=signal_id,
                                status="STOPPED",
                                close_reason="STOP_LOSS",
                                current_price=current,
                                event_time=now,
                                event_type="STOP_LOSS_HIT",
                            )
                            events_created.append((signal_id, "STOP_LOSS_HIT"))
                            continue

                        opposite_scenario = self._opposite_structure_scenario(
                            analysis_by_timeframe.get(str(row["timeframe"] or "").upper()),
                            side=side,
                            current_price=current,
                        )
                        if opposite_scenario is not None:
                            self._close_signal(
                                conn,
                                signal_id=signal_id,
                                status="STOPPED",
                                close_reason="OPPOSITE_STRUCTURE",
                                current_price=current,
                                event_time=now,
                                event_type="OPPOSITE_STRUCTURE_HIT",
                            )
                            events_created.append((signal_id, "OPPOSITE_STRUCTURE_HIT"))
                            continue

                        if self._volatility_exit_triggered(
                            conn,
                            symbol=symbol,
                            timeframe=row["timeframe"],
                            side=side,
                            current_price=current,
                            entry_price=float(row["entry_triggered_price"] or entry),
                        ):
                            self._close_signal(
                                conn,
                                signal_id=signal_id,
                                status="STOPPED",
                                close_reason="VOLATILITY_EXIT",
                                current_price=current,
                                event_time=now,
                                event_type="VOLATILITY_EXIT_HIT",
                            )
                            events_created.append((signal_id, "VOLATILITY_EXIT_HIT"))
                            continue

                        limit = time_stop_bars_for_timeframe(row["timeframe"])
                        entry_triggered_at = _parse_iso_timestamp(row["entry_triggered_at"])
                        if (
                            limit is not None
                            and entry_triggered_at is not None
                            and row["tp1_hit_at"] is None
                        ):
                            now_dt = _parse_iso_timestamp(now)
                            if now_dt is not None:
                                bars_elapsed = self._bars_elapsed(row["timeframe"], entry_triggered_at, now_dt)
                                if bars_elapsed >= limit:
                                    self._close_signal(
                                        conn,
                                        signal_id=signal_id,
                                        status="STOPPED",
                                        close_reason="TIME_STOP",
                                        current_price=current,
                                        event_time=now,
                                        event_type="TIME_STOP_HIT",
                                    )
                                    events_created.append((signal_id, "TIME_STOP_HIT"))

        except sqlite3.Error as exc:
            print(f"[wave_repository] track_price_update failed: {exc}")
            traceback.print_exc()

        return events_created

    def _opposite_structure_scenario(
        self,
        analysis: dict | None,
        *,
        side: str,
        current_price: float,
    ):
        if not analysis:
            return None

        target_bias = "BEARISH" if side == "LONG" else "BULLISH"
        for scenario in _execution_scenarios(analysis):
            if (getattr(scenario, "bias", None) or "").upper() != target_bias:
                continue
            if update_scenario_state(scenario, current_price) == "CONFIRMED":
                return scenario
        return None

    def _volatility_exit_triggered(
        self,
        conn: sqlite3.Connection,
        *,
        symbol: str,
        timeframe: str,
        side: str,
        current_price: float,
        entry_price: float,
    ) -> bool:
        rows = conn.execute(
            """
            SELECT open, high, low, close
            FROM market_candles
            WHERE symbol = ? AND timeframe = ?
            ORDER BY open_time DESC
            LIMIT 6
            """,
            (symbol.upper(), str(timeframe or "").upper()),
        ).fetchall()
        if len(rows) < 3:
            return False

        latest = rows[0]
        baseline_ranges = [
            max(float(row["high"]) - float(row["low"]), 0.0)
            for row in rows[1:]
        ]
        baseline_range = sum(baseline_ranges) / len(baseline_ranges) if baseline_ranges else 0.0
        if baseline_range <= 0:
            return False

        candle = {
            "open": float(latest["open"]),
            "high": float(latest["high"]),
            "low": float(latest["low"]),
            "close": float(current_price),
        }
        return volatility_spike_against_position(
            candle,
            side,
            baseline_range,
            entry_price,
        )

    def _replace_pending_signals(
        self,
        conn: sqlite3.Connection,
        symbol: str,
        timeframe: str,
        replacement_hash: str,
        event_time: str,
    ) -> list[int]:
        rows = conn.execute(
            """
            SELECT id FROM signals
            WHERE symbol = ?
              AND timeframe = ?
              AND status = 'PENDING_ENTRY'
              AND signal_hash != ?
            """,
            (symbol, timeframe, replacement_hash),
        ).fetchall()
        replaced_ids: list[int] = []

        for row in rows:
            signal_id = int(row["id"])
            replaced_ids.append(signal_id)
            conn.execute(
                """
                UPDATE signals
                SET status = 'REPLACED',
                    updated_at = ?,
                    closed_at = ?,
                    close_reason = 'REPLACED_BY_NEW_SIGNAL'
                WHERE id = ?
                """,
                (event_time, event_time, signal_id),
            )
            self._insert_event(
                conn,
                signal_id=signal_id,
                event_type="SIGNAL_REPLACED",
                price=None,
                details={"reason": "REPLACED_BY_NEW_SIGNAL"},
                event_time=event_time,
            )

        return replaced_ids

    def _mark_target_hit(
        self,
        conn: sqlite3.Connection,
        signal_id: int,
        target_label: str,
        current_price: float,
        event_time: str,
        status: str,
    ) -> None:
        column_prefix = target_label.lower()
        conn.execute(
            f"""
            UPDATE signals
            SET status = ?,
                updated_at = ?,
                current_price = ?,
                {column_prefix}_hit_at = ?,
                {column_prefix}_hit_price = ?
            WHERE id = ?
            """,
            (status, event_time, current_price, event_time, current_price, signal_id),
        )
        self._insert_event(
            conn,
            signal_id=signal_id,
            event_type=f"{target_label}_HIT",
            price=current_price,
            details={"status": status},
            event_time=event_time,
        )

    def _update_stop_loss(
        self,
        conn: sqlite3.Connection,
        signal_id: int,
        stop_loss: float,
        event_time: str,
    ) -> None:
        conn.execute(
            """
            UPDATE signals
            SET stop_loss = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (_round_price(stop_loss), event_time, signal_id),
        )
        self._insert_event(
            conn,
            signal_id=signal_id,
            event_type="STOP_MOVED",
            price=_round_price(stop_loss),
            details={"stop_loss": _round_price(stop_loss)},
            event_time=event_time,
        )

    def _close_signal(
        self,
        conn: sqlite3.Connection,
        signal_id: int,
        status: str,
        close_reason: str,
        current_price: float,
        event_time: str,
        event_type: str,
    ) -> None:
        conn.execute(
            """
            UPDATE signals
            SET status = ?,
                updated_at = ?,
                current_price = ?,
                closed_at = ?,
                close_reason = ?
            WHERE id = ?
            """,
            (status, event_time, current_price, event_time, close_reason, signal_id),
        )
        self._insert_event(
            conn,
            signal_id=signal_id,
            event_type=event_type,
            price=current_price,
            details={"close_reason": close_reason, "status": status},
            event_time=event_time,
        )

    def _bars_elapsed(self, timeframe: str | None, start: datetime, end: datetime) -> int:
        mapping_seconds = {
            "4H": 4 * 60 * 60,
            "1D": 24 * 60 * 60,
            "1W": 7 * 24 * 60 * 60,
        }
        seconds = mapping_seconds.get((timeframe or "").upper())
        if not seconds:
            return 0
        elapsed = max(0.0, (end - start).total_seconds())
        return int(elapsed // seconds)

    def _refresh_row(self, conn: sqlite3.Connection, signal_id: int) -> sqlite3.Row:
        return conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()

    def _insert_event(
        self,
        conn: sqlite3.Connection,
        signal_id: int,
        event_type: str,
        price: float | None,
        details: dict | None,
        event_time: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO signal_events (signal_id, event_time, event_type, price, details_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                signal_id,
                event_time,
                event_type,
                _round_price(price),
                _json_dump(details or {}),
            ),
        )

    def _build_summary_text(self, snapshot: dict | None) -> str | None:
        if snapshot is None:
            return None
        return (
            f"{snapshot['timeframe']} | {snapshot['pattern_type']} | {snapshot['scenario_name']}\n"
            f"Bias: {snapshot['bias']}\n"
            f"Entry: {snapshot['entry_price']}\n"
            f"SL: {snapshot['stop_loss']}\n"
            f"TP1: {snapshot['tp1']}\n"
            f"TP2: {snapshot['tp2']}\n"
            f"TP3: {snapshot['tp3']}\n"
            f"RR1: {snapshot['rr_tp1']}\n"
            f"RR2: {snapshot['rr_tp2']}\n"
            f"RR3: {snapshot['rr_tp3']}"
        )

    def _entry_crossed(self, side: str, current_price: float, entry_price: float) -> bool:
        if side == "LONG":
            return current_price >= entry_price
        return current_price <= entry_price

    def _stop_crossed(self, side: str, current_price: float, stop_price: float) -> bool:
        if side == "LONG":
            return current_price <= stop_price
        return current_price >= stop_price

    def _target_crossed(self, side: str, current_price: float, target_price: float) -> bool:
        if side == "LONG":
            return current_price >= target_price
        return current_price <= target_price
