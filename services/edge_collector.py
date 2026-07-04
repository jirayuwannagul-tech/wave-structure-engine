"""Reads closed signals from the DB and computes edge statistics.

Saves results to storage/edge_store.json. Run this whenever a new trade closes.
All data sourced exclusively from actual DB records — no assumptions about signal quality.
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path


_TP1_PCT = 0.40
_TP2_PCT = 0.30
_TP3_PCT = 0.30

_DB_PATH = Path(__file__).parent.parent / "storage" / "wave_engine.db"
_STORE_PATH = Path(__file__).parent.parent / "storage" / "edge_store.json"

# Closed terminal statuses to include
_CLOSED_STATUSES = {"TP3_HIT", "STOPPED"}


def _classify_result(row: sqlite3.Row) -> str:
    if row["tp3_hit_at"]:
        return "TP3_HIT"
    if row["tp2_hit_at"]:
        return "TP2_THEN_SL"
    if row["tp1_hit_at"]:
        return "TP1_THEN_SL"
    return "SL_HIT"


def _realized_rr(row: sqlite3.Row, result: str) -> float:
    """Realized R-multiple using 40/30/30 TP sizing."""
    rr1 = float(row["rr_tp1"] or 0)
    rr2 = float(row["rr_tp2"] or 0)
    rr3 = float(row["rr_tp3"] or 0)
    if result == "TP3_HIT":
        return _TP1_PCT * rr1 + _TP2_PCT * rr2 + _TP3_PCT * rr3
    if result == "TP2_THEN_SL":
        # SL moves to TP1 after TP2 hit → remaining 30% exits at TP1 (profit)
        return _TP1_PCT * rr1 + _TP2_PCT * rr2 + _TP3_PCT * rr1
    if result == "TP1_THEN_SL":
        # SL moves to breakeven after TP1 hit → remaining 60% exits at 0
        return _TP1_PCT * rr1
    return -1.0


def _stat_bucket() -> dict:
    return {"n": 0, "wins": 0, "sum_rr": 0.0}


def _finalize(bucket: dict) -> dict:
    n = bucket["n"]
    wins = bucket["wins"]
    return {
        "n": n,
        "wins": wins,
        "losses": n - wins,
        "wr": round(wins / n, 4) if n else 0.0,
        "avg_rr": round(bucket["sum_rr"] / n, 4) if n else 0.0,
    }


def _record_trade(bucket: dict, win: bool, rr: float) -> None:
    bucket["n"] += 1
    if win:
        bucket["wins"] += 1
    bucket["sum_rr"] += rr


def _compute_streaks(trades: list[dict]) -> dict:
    if not trades:
        return {"current_type": None, "current_count": 0,
                "max_win_streak": 0, "max_loss_streak": 0}

    max_w = max_l = cur = 0
    cur_type = None

    for t in trades:
        t_type = "W" if t["win"] else "L"
        if t_type == cur_type:
            cur += 1
        else:
            cur_type = t_type
            cur = 1
        if t_type == "W":
            max_w = max(max_w, cur)
        else:
            max_l = max(max_l, cur)

    return {
        "current_type": cur_type,
        "current_count": cur,
        "max_win_streak": max_w,
        "max_loss_streak": max_l,
    }


def collect(db_path: Path | None = None, store_path: Path | None = None) -> dict:
    """Pull all closed signals, compute stats, return and save edge_store dict."""
    db = db_path or _DB_PATH
    out = store_path or _STORE_PATH

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT id, symbol, timeframe, pattern_type, scenario_name, bias, side,
               status, close_reason,
               rr_tp1, rr_tp2, rr_tp3,
               tp1_hit_at, tp2_hit_at, tp3_hit_at,
               entry_triggered_at, closed_at,
               analysis_summary_json
        FROM signals
        WHERE status IN ('TP3_HIT', 'STOPPED')
          AND entry_triggered_at IS NOT NULL
        ORDER BY closed_at ASC
        """
    ).fetchall()
    conn.close()

    trades: list[dict] = []
    overall = _stat_bucket()
    by_symbol: dict[str, dict] = defaultdict(_stat_bucket)
    by_timeframe: dict[str, dict] = defaultdict(_stat_bucket)
    by_pattern: dict[str, dict] = defaultdict(_stat_bucket)
    by_leg: dict[str, dict] = defaultdict(_stat_bucket)
    by_side: dict[str, dict] = defaultdict(_stat_bucket)
    by_scenario: dict[str, dict] = defaultdict(_stat_bucket)
    by_hour: dict[str, dict] = defaultdict(_stat_bucket)
    by_result: dict[str, int] = defaultdict(int)

    last_id = 0

    for row in rows:
        result = _classify_result(row)
        win = result != "SL_HIT"
        rr = _realized_rr(row, result)

        # Extract leg from analysis_summary_json (populated for new signals)
        leg: str | None = None
        if row["analysis_summary_json"]:
            try:
                summary = json.loads(row["analysis_summary_json"])
                leg = summary.get("current_leg")
            except (json.JSONDecodeError, AttributeError):
                pass

        # Hour of day from entry_triggered_at (UTC)
        hour_utc: int | None = None
        if row["entry_triggered_at"]:
            try:
                dt_str = row["entry_triggered_at"].replace("+00:00", "").replace("Z", "")
                dt = datetime.fromisoformat(dt_str)
                hour_utc = dt.hour
            except (ValueError, AttributeError):
                pass

        trade = {
            "id": row["id"],
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "pattern_type": row["pattern_type"],
            "scenario_name": row["scenario_name"],
            "side": row["side"],
            "bias": row["bias"],
            "leg": leg,
            "hour_utc": hour_utc,
            "result": result,
            "win": win,
            "realized_rr": round(rr, 4),
            "entry_triggered_at": row["entry_triggered_at"],
            "closed_at": row["closed_at"],
        }
        trades.append(trade)

        _record_trade(overall, win, rr)
        _record_trade(by_symbol[row["symbol"]], win, rr)
        _record_trade(by_timeframe[row["timeframe"]], win, rr)
        if row["pattern_type"]:
            _record_trade(by_pattern[row["pattern_type"]], win, rr)
        if leg:
            _record_trade(by_leg[leg], win, rr)
        if row["side"]:
            _record_trade(by_side[row["side"]], win, rr)
        if row["scenario_name"]:
            _record_trade(by_scenario[row["scenario_name"]], win, rr)
        if hour_utc is not None:
            _record_trade(by_hour[str(hour_utc)], win, rr)
        by_result[result] += 1

        last_id = max(last_id, row["id"])

    store = {
        "last_updated": datetime.now(UTC).isoformat(),
        "last_processed_id": last_id,
        "total_closed": len(trades),
        "trades": trades,
        "stats": {
            "overall": _finalize(overall),
            "by_symbol": {k: _finalize(v) for k, v in sorted(by_symbol.items())},
            "by_timeframe": {k: _finalize(v) for k, v in sorted(by_timeframe.items())},
            "by_pattern_type": {k: _finalize(v) for k, v in sorted(by_pattern.items())},
            "by_leg": {k: _finalize(v) for k, v in sorted(by_leg.items())},
            "by_side": {k: _finalize(v) for k, v in sorted(by_side.items())},
            "by_scenario": {k: _finalize(v) for k, v in sorted(by_scenario.items())},
            "by_hour_utc": {k: _finalize(v) for k, v in sorted(by_hour.items(), key=lambda x: int(x[0]))},
            "by_result": dict(by_result),
            "streaks": _compute_streaks(trades),
        },
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(store, indent=2, ensure_ascii=False))
    return store
