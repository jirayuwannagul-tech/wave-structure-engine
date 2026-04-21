"""Fan-out trade execution to all active managed accounts."""

from __future__ import annotations

import concurrent.futures
import logging
import os
from dataclasses import replace

from execution.binance_futures_client import BinanceFuturesClient
from execution.models import ExecutionConfig
from execution.position_manager import PositionManager
from execution.settings import load_execution_config
from storage.account_store import Account, AccountStore
from storage.position_store import PositionStore

logger = logging.getLogger(__name__)

_MAX_WORKERS = 10


def _client_for_account(account: Account, base_config: ExecutionConfig) -> BinanceFuturesClient:
    cfg = replace(base_config, api_key=account.api_key, api_secret=account.api_secret)
    return BinanceFuturesClient(cfg)


def _execute_for_account(account: Account, event_type: str, signal_row, base_config: ExecutionConfig) -> dict:
    """Run open/close execution for a single account. Returns result dict."""
    try:
        client = _client_for_account(account, base_config)
        store = PositionStore()
        pm = PositionManager(client, base_config, store)

        if event_type in ("ENTRY_TRIGGERED", "SIGNAL_CREATED"):
            try:
                bal = client.get_account_balance()
                eq_usdt = 0.0
                if isinstance(bal, list):
                    for row in bal:
                        if str(row.get("asset") or "").upper() == "USDT":
                            for key in ("availableBalance", "walletBalance", "balance"):
                                v = row.get(key)
                                if v is not None:
                                    eq_usdt = float(v)
                                    break
                            if eq_usdt > 0:
                                break
            except Exception:
                eq_usdt = 0.0
            result = pm.open_from_signal(signal_row, equity_usdt=eq_usdt)

        elif event_type == "SIGNAL_CLOSED":
            result = pm.close_from_signal(signal_row)
        else:
            return {"ok": False, "skipped": f"unknown event_type: {event_type}"}

        logger.info("fanout account=%s event=%s result=%s", account.id, event_type, result)
        return {"ok": True, "account_id": account.id, "result": result}

    except Exception as exc:
        logger.error("fanout account=%s event=%s error=%s", account.id, event_type, exc, exc_info=True)
        return {"ok": False, "account_id": account.id, "error": str(exc)}


def fanout_to_active_accounts(event_type: str, signal_row) -> list[dict]:
    """
    Send trade event to all active managed accounts in parallel.
    Each account runs independently — one failure does not affect others.
    Returns list of per-account results.
    """
    db_path = os.getenv("WAVE_DB_PATH", "storage/wave_engine.db")
    store = AccountStore(db_path=db_path)
    accounts = store.list_active()

    if not accounts:
        return []

    base_config = load_execution_config()
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(accounts))) as executor:
        futures = {
            executor.submit(_execute_for_account, acc, event_type, signal_row, base_config): acc
            for acc in accounts
        }
        for future in concurrent.futures.as_completed(futures):
            acc = futures[future]
            try:
                results.append(future.result(timeout=30))
            except Exception as exc:
                results.append({"ok": False, "account_id": acc.id, "error": str(exc)})

    return results
