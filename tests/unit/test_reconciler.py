import os
import tempfile

import pytest

from execution.fake_binance_client import FakeBinanceFuturesClient
from execution.models import ExecutionConfig
from execution.position_manager import PositionManager
from execution.reconciler import reconcile_symbol
from storage.position_store import PositionStore


def _cfg():
    return ExecutionConfig(
        enabled=True,
        live_order_enabled=True,
        use_testnet=True,
        api_key="k",
        api_secret="s",
        risk_per_trade=0.01,
        tp1_size_pct=0.4,
        tp2_size_pct=0.3,
        tp3_size_pct=0.3,
    )


@pytest.fixture
def rec_setup():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = PositionStore(db_path=path)
    client = FakeBinanceFuturesClient()
    try:
        yield client, store, _cfg(), path
    finally:
        os.unlink(path)


def test_reconcile_closes_stale_db_when_exchange_flat(rec_setup):
    client, store, cfg, _ = rec_setup
    pid = store.create_position(
        symbol="BTCUSDT",
        side="LONG",
        source_signal_id=1,
        signal_hash=None,
        quantity=0.1,
        entry_price=100.0,
        entry_order_id=1,
        stop_loss_price=95.0,
    )
    out = reconcile_symbol(client, store, "BTCUSDT", cfg)
    assert out["action"] == "closed_stale"
    assert out["position_id"] == pid
    assert store.get_open_position_by_symbol("BTCUSDT") is None


def test_reconcile_recover_exchange_position_no_db(rec_setup):
    client, store, cfg, _ = rec_setup
    client.seed_position("BTCUSDT", 0.1, 50000.0)
    out = reconcile_symbol(client, store, "BTCUSDT", cfg)
    assert out["action"] == "recovered"
    row = store.get_open_position_by_symbol("BTCUSDT")
    assert row is not None
    assert int(row["recovered"]) == 1
    assert row["stop_loss_price"] is not None


def test_reconcile_still_open_calls_ensure_sl(rec_setup):
    client, store, cfg, _ = rec_setup
    store.create_position(
        symbol="BTCUSDT",
        side="LONG",
        source_signal_id=2,
        signal_hash=None,
        quantity=0.1,
        entry_price=100.0,
        entry_order_id=2,
        stop_loss_price=90.0,
    )
    client.seed_position("BTCUSDT", 0.1, 100.0)
    out = reconcile_symbol(client, store, "BTCUSDT", cfg)
    assert out["action"] == "still_open"
    rows = store.list_open_protective_orders(int(out["position_id"]))
    sl = [r for r in rows if r["order_kind"] == "SL"]
    assert len(sl) >= 1


def test_reconcile_syncs_tp_filled_via_query_order(rec_setup):
    client, store, cfg, _ = rec_setup
    pm = PositionManager(client, cfg, store)
    signal_row = {
        "id": 200,
        "symbol": "BTCUSDT",
        "timeframe": "1D",
        "side": "LONG",
        "entry_price": 50000.0,
        "stop_loss": 49000.0,
        "tp1": 51000.0,
        "tp2": 52000.0,
        "tp3": 53000.0,
    }
    out = pm.open_from_signal(signal_row)
    assert out["ok"]
    pid = out["position_id"]
    tp1_oid = None
    for o in client.get_open_orders("BTCUSDT"):
        if o.get("type") == "TAKE_PROFIT_MARKET" and "TP1" in str(o.get("clientOrderId") or ""):
            tp1_oid = int(o["orderId"])
            break
    assert tp1_oid is not None
    client.simulate_fill_order(tp1_oid)
    reconcile_symbol(client, store, "BTCUSDT", cfg)
    with store._connect() as conn:
        st = conn.execute(
            "SELECT status FROM exchange_position_orders WHERE position_id=? AND order_kind='TP1'",
            (pid,),
        ).fetchone()
    assert st and st[0] == "FILLED"


def test_reconcile_resizes_sl_after_partial_tp(rec_setup):
    client, store, cfg, _ = rec_setup
    pm = PositionManager(client, cfg, store)
    signal_row = {
        "id": 201,
        "symbol": "BTCUSDT",
        "timeframe": "1D",
        "side": "LONG",
        "entry_price": 50000.0,
        "stop_loss": 49000.0,
        "tp1": 51000.0,
        "tp2": 52000.0,
        "tp3": 53000.0,
    }
    pm.open_from_signal(signal_row)
    tp1_oid = next(
        int(o["orderId"])
        for o in client.get_open_orders("BTCUSDT")
        if o.get("type") == "TAKE_PROFIT_MARKET" and "TP1" in str(o.get("clientOrderId") or "")
    )
    pos_before = abs(float(client.get_position("BTCUSDT")["positionAmt"]))
    client.simulate_fill_order(tp1_oid)
    pos_after = abs(float(client.get_position("BTCUSDT")["positionAmt"]))
    assert pos_after < pos_before - 1e-9
    reconcile_symbol(client, store, "BTCUSDT", cfg)
    sl_orders = [
        o
        for o in client.get_open_orders("BTCUSDT")
        if o.get("type") == "STOP_MARKET"
        and str(o.get("reduceOnly")).lower() in ("true", "1")
    ]
    assert len(sl_orders) >= 1
    sl_qty = float(sl_orders[0].get("origQty") or 0)
    assert sl_qty == pytest.approx(pos_after, rel=0, abs=0.002)
