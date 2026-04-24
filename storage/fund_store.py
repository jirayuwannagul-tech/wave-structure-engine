"""SQLite-backed store for pooled fund management."""

from __future__ import annotations

import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


def _generate_token() -> str:
    return secrets.token_urlsafe(24)


@dataclass
class FundMember:
    id: int
    name: str
    email: str
    phone: str
    balance_usdt: float
    initial_deposit: float
    joined_at: str
    active: bool
    token: str
    note: str | None


@dataclass
class FundTrade:
    id: int
    symbol: str
    timeframe: str
    side: str
    entry: float
    sl: float
    opened_at: str
    closed_at: str | None
    result: str | None
    realized_rr: float | None
    risk_pct: float | None   # |SL-entry|/entry
    pnl_pct: float | None    # realized_rr × risk_pct
    settlement_month: str | None  # YYYY-MM


@dataclass
class FundParticipation:
    id: int
    trade_id: int
    member_id: int
    balance_at_open: float
    pnl_pct: float | None
    pnl_usdt: float | None
    balance_after: float | None


class FundStore:
    def __init__(self, db_path: str = "storage/wave_engine.db"):
        self.db_path = db_path
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
                CREATE TABLE IF NOT EXISTS fund_members (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    name             TEXT NOT NULL DEFAULT '',
                    email            TEXT NOT NULL DEFAULT '',
                    phone            TEXT NOT NULL DEFAULT '',
                    balance_usdt     REAL NOT NULL DEFAULT 0,
                    initial_deposit  REAL NOT NULL DEFAULT 0,
                    joined_at        TEXT NOT NULL,
                    active           INTEGER NOT NULL DEFAULT 1,
                    token            TEXT NOT NULL UNIQUE,
                    note             TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fund_trades (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol            TEXT NOT NULL,
                    timeframe         TEXT NOT NULL DEFAULT '',
                    side              TEXT NOT NULL,
                    entry             REAL NOT NULL,
                    sl                REAL NOT NULL,
                    opened_at         TEXT NOT NULL,
                    closed_at         TEXT,
                    result            TEXT,
                    realized_rr       REAL,
                    risk_pct          REAL,
                    pnl_pct           REAL,
                    settlement_month  TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fund_participations (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id         INTEGER NOT NULL,
                    member_id        INTEGER NOT NULL,
                    balance_at_open  REAL NOT NULL,
                    pnl_pct          REAL,
                    pnl_usdt         REAL,
                    balance_after    REAL,
                    UNIQUE(trade_id, member_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fund_settlements (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    month        TEXT NOT NULL UNIQUE,
                    settled_at   TEXT NOT NULL,
                    total_pnl    REAL NOT NULL DEFAULT 0,
                    total_fee    REAL NOT NULL DEFAULT 0,
                    net_pnl      REAL NOT NULL DEFAULT 0,
                    notes        TEXT
                )
            """)

    # ── Members ──────────────────────────────────────────────────────────────

    def add_member(self, name: str, email: str, phone: str,
                   deposit_usdt: float, joined_at: str, note: str | None = None) -> FundMember:
        token = _generate_token()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO fund_members
                   (name, email, phone, balance_usdt, initial_deposit, joined_at, token, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (name.strip(), email.strip(), phone.strip(),
                 deposit_usdt, deposit_usdt, joined_at, token, note),
            )
            row_id = cur.lastrowid
        return self.get_member(row_id)

    def get_member(self, member_id: int) -> FundMember | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM fund_members WHERE id=?", (member_id,)).fetchone()
        return self._to_member(row) if row else None

    def get_member_by_token(self, token: str) -> FundMember | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM fund_members WHERE token=?", (token,)).fetchone()
        return self._to_member(row) if row else None

    def list_members(self, active_only: bool = False) -> list[FundMember]:
        q = "SELECT * FROM fund_members"
        if active_only:
            q += " WHERE active=1"
        q += " ORDER BY joined_at"
        with self._connect() as conn:
            rows = conn.execute(q).fetchall()
        return [self._to_member(r) for r in rows]

    def update_member_balance(self, member_id: int, new_balance: float) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE fund_members SET balance_usdt=? WHERE id=?",
                         (new_balance, member_id))

    def deactivate_member(self, member_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE fund_members SET active=0 WHERE id=?", (member_id,))

    def delete_member(self, member_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM fund_members WHERE id=?", (member_id,))

    def _to_member(self, row) -> FundMember:
        return FundMember(
            id=row["id"], name=row["name"], email=row["email"], phone=row["phone"],
            balance_usdt=row["balance_usdt"], initial_deposit=row["initial_deposit"],
            joined_at=row["joined_at"], active=bool(row["active"]),
            token=row["token"], note=row["note"],
        )

    # ── Trades ───────────────────────────────────────────────────────────────

    def add_trade(self, symbol: str, timeframe: str, side: str,
                  entry: float, sl: float, opened_at: str) -> FundTrade:
        risk_pct = abs(sl - entry) / entry
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO fund_trades
                   (symbol, timeframe, side, entry, sl, opened_at, risk_pct)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (symbol, timeframe, side.upper(), entry, sl, opened_at, risk_pct),
            )
            trade_id = cur.lastrowid
        # snapshot active members into participations
        self._snapshot_members(trade_id, opened_at)
        return self.get_trade(trade_id)

    def _snapshot_members(self, trade_id: int, opened_at: str) -> None:
        """Record which members are active at trade open and their current balance."""
        with self._connect() as conn:
            members = conn.execute(
                "SELECT * FROM fund_members WHERE active=1 AND joined_at <= ?",
                (opened_at,)
            ).fetchall()
            for m in members:
                conn.execute(
                    """INSERT OR IGNORE INTO fund_participations
                       (trade_id, member_id, balance_at_open)
                       VALUES (?, ?, ?)""",
                    (trade_id, m["id"], m["balance_usdt"]),
                )

    def close_trade(self, trade_id: int, closed_at: str, result: str,
                    realized_rr: float) -> FundTrade:
        trade = self.get_trade(trade_id)
        if not trade:
            raise ValueError(f"Trade {trade_id} not found")
        pnl_pct = realized_rr * trade.risk_pct
        month = closed_at[:7]  # YYYY-MM
        with self._connect() as conn:
            conn.execute(
                """UPDATE fund_trades
                   SET closed_at=?, result=?, realized_rr=?, pnl_pct=?, settlement_month=?
                   WHERE id=?""",
                (closed_at, result, realized_rr, pnl_pct, month, trade_id),
            )
        # update each participant's pnl and balance
        self._apply_pnl(trade_id, pnl_pct)
        return self.get_trade(trade_id)

    def _apply_pnl(self, trade_id: int, pnl_pct: float) -> None:
        with self._connect() as conn:
            parts = conn.execute(
                "SELECT * FROM fund_participations WHERE trade_id=?", (trade_id,)
            ).fetchall()
            for p in parts:
                bal = p["balance_at_open"]
                pnl_usdt = bal * pnl_pct
                bal_after = bal + pnl_usdt
                conn.execute(
                    """UPDATE fund_participations
                       SET pnl_pct=?, pnl_usdt=?, balance_after=? WHERE id=?""",
                    (pnl_pct, pnl_usdt, bal_after, p["id"]),
                )
                conn.execute(
                    "UPDATE fund_members SET balance_usdt=? WHERE id=?",
                    (bal_after, p["member_id"]),
                )

    def get_trade(self, trade_id: int) -> FundTrade | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM fund_trades WHERE id=?", (trade_id,)).fetchone()
        return self._to_trade(row) if row else None

    def list_trades(self, month: str | None = None) -> list[FundTrade]:
        if month:
            q, args = "SELECT * FROM fund_trades WHERE settlement_month=? ORDER BY opened_at", (month,)
        else:
            q, args = "SELECT * FROM fund_trades ORDER BY opened_at DESC", ()
        with self._connect() as conn:
            rows = conn.execute(q, args).fetchall()
        return [self._to_trade(r) for r in rows]

    def list_open_trades(self) -> list[FundTrade]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM fund_trades WHERE closed_at IS NULL ORDER BY opened_at"
            ).fetchall()
        return [self._to_trade(r) for r in rows]

    def _to_trade(self, row) -> FundTrade:
        return FundTrade(
            id=row["id"], symbol=row["symbol"], timeframe=row["timeframe"],
            side=row["side"], entry=row["entry"], sl=row["sl"],
            opened_at=row["opened_at"], closed_at=row["closed_at"],
            result=row["result"], realized_rr=row["realized_rr"],
            risk_pct=row["risk_pct"], pnl_pct=row["pnl_pct"],
            settlement_month=row["settlement_month"],
        )

    # ── Settlement ────────────────────────────────────────────────────────────

    def get_settlement_data(self, month: str) -> list[dict]:
        """Per-member P&L summary for a given month (YYYY-MM)."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT
                    m.id, m.name, m.email, m.phone,
                    m.initial_deposit,
                    MIN(m2.balance_usdt) as balance_start,
                    SUM(p.pnl_usdt) as gross_pnl,
                    COUNT(p.id) as trades_count,
                    SUM(CASE WHEN p.pnl_usdt > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN p.pnl_usdt < 0 THEN 1 ELSE 0 END) as losses
                FROM fund_members m
                JOIN fund_participations p ON p.member_id = m.id
                JOIN fund_trades t ON t.id = p.trade_id
                LEFT JOIN fund_members m2 ON m2.id = m.id
                WHERE t.settlement_month = ? AND t.closed_at IS NOT NULL
                GROUP BY m.id
                ORDER BY m.joined_at
            """, (month,)).fetchall()

            # get current balance per member
            balances = {r["id"]: r["balance_usdt"] for r in conn.execute(
                "SELECT id, balance_usdt FROM fund_members"
            ).fetchall()}

        result = []
        for r in rows:
            gross = r["gross_pnl"] or 0.0
            fee = max(gross * 0.03, 0)  # 3% fee only on profit
            net = gross - fee
            result.append({
                "id": r["id"],
                "name": r["name"],
                "email": r["email"],
                "phone": r["phone"],
                "initial_deposit": r["initial_deposit"],
                "balance_end": balances.get(r["id"], 0),
                "gross_pnl": round(gross, 4),
                "fee": round(fee, 4),
                "net_pnl": round(net, 4),
                "trades_count": r["trades_count"],
                "wins": r["wins"] or 0,
                "losses": r["losses"] or 0,
                "return_pct": round(gross / r["initial_deposit"] * 100, 2) if r["initial_deposit"] else 0,
            })
        return result

    def get_participation_detail(self, member_id: int, month: str) -> list[dict]:
        """Per-trade detail for one member in a given month."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT t.symbol, t.timeframe, t.side, t.opened_at, t.closed_at,
                       t.result, t.realized_rr, t.risk_pct, t.pnl_pct,
                       p.balance_at_open, p.pnl_usdt, p.balance_after
                FROM fund_participations p
                JOIN fund_trades t ON t.id = p.trade_id
                WHERE p.member_id = ? AND t.settlement_month = ?
                  AND t.closed_at IS NOT NULL
                ORDER BY t.opened_at
            """, (member_id, month)).fetchall()
        return [dict(r) for r in rows]

    def available_months(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT settlement_month FROM fund_trades "
                "WHERE settlement_month IS NOT NULL ORDER BY settlement_month DESC"
            ).fetchall()
        return [r[0] for r in rows]
