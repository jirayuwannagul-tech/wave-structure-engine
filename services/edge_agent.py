"""Background agent: detects newly closed trades, updates edge stats, calls Gemini.

Runs as a systemd service. Checks every POLL_INTERVAL seconds for new closed signals.
Gemini analysis fires only when new trades are detected (per-trade trigger, not time-based).

Usage:
    python -m services.edge_agent
    python services/edge_agent.py
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from pathlib import Path

from services.edge_collector import collect
from services.gemini_analyst import analyze

logging.basicConfig(level=logging.INFO, format="%(asctime)s [edge-agent] %(message)s")
log = logging.getLogger(__name__)

_POLL_INTERVAL = int(os.getenv("EDGE_AGENT_POLL_INTERVAL", "600"))  # default 10 min
_DB_PATH = Path(__file__).parent.parent / "storage" / "wave_engine.db"
_STATE_PATH = Path(__file__).parent.parent / "storage" / "edge_agent_state.json"
_STORE_PATH = Path(__file__).parent.parent / "storage" / "edge_store.json"


def _load_state() -> dict:
    if _STATE_PATH.exists():
        try:
            return json.loads(_STATE_PATH.read_text())
        except Exception:
            pass
    return {"last_processed_id": 0, "last_run": None}


def _save_state(state: dict) -> None:
    _STATE_PATH.write_text(json.dumps(state, indent=2))


def _count_new_closed(last_id: int) -> int:
    if not _DB_PATH.exists():
        return 0
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        row = conn.execute(
            "SELECT COUNT(*) FROM signals WHERE status IN ('TP3_HIT','STOPPED') "
            "AND entry_triggered_at IS NOT NULL AND id > ?",
            (last_id,),
        ).fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception as e:
        log.warning("DB check failed: %s", e)
        return 0


def _run_once(state: dict) -> dict:
    last_id = state.get("last_processed_id", 0)
    new_count = _count_new_closed(last_id)

    if new_count == 0:
        log.debug("No new closed trades since id=%d", last_id)
        return state

    log.info("Found %d new closed trade(s) since id=%d — collecting stats", new_count, last_id)
    try:
        store = collect()
        log.info(
            "Edge stats updated: %d total, WR=%.1f%%, avg_rr=%.3f",
            store["total_closed"],
            store["stats"]["overall"]["wr"] * 100,
            store["stats"]["overall"]["avg_rr"],
        )
        state["last_processed_id"] = store["last_processed_id"]
    except Exception as e:
        log.error("edge_collector failed: %s", e)
        return state

    try:
        insights = analyze(store)
        if insights:
            log.info("Gemini analysis saved (through signal id=%d)", insights.get("analyzed_through_signal_id"))
        else:
            log.debug("Gemini skipped (no API key)")
    except Exception as e:
        log.error("gemini_analyst failed: %s", e)

    from datetime import UTC, datetime
    state["last_run"] = datetime.now(UTC).isoformat()
    return state


def run() -> None:
    log.info("Edge agent started (poll_interval=%ds)", _POLL_INTERVAL)
    state = _load_state()
    while True:
        try:
            state = _run_once(state)
            _save_state(state)
        except Exception as e:
            log.error("Unexpected error in run loop: %s", e)
        time.sleep(_POLL_INTERVAL)


if __name__ == "__main__":
    run()
