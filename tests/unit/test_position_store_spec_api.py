"""Spec API: views, create_position_from_signal, update_order_status, close_price."""

import os
import tempfile

import pytest

from storage.position_store import PositionStore


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        yield PositionStore(db_path=path)
    finally:
        os.unlink(path)


def test_views_positions_and_position_orders(store: PositionStore):
    pid = store.create_position(
        symbol="BTCUSDT",
        side="LONG",
        source_signal_id=9,
        signal_hash="h",
        quantity=0.01,
        entry_price=100.0,
        entry_order_id=1,
        stop_loss_price=99.0,
    )
    with store._connect() as conn:
        row = conn.execute("SELECT qty, source_signal_hash FROM positions WHERE id=?", (pid,)).fetchone()
    assert row is not None
    assert float(row["qty"]) == pytest.approx(0.01)
    assert row["source_signal_hash"] == "h"


def test_create_position_from_signal(store: PositionStore):
    signal_row = {"id": 3, "symbol": "BTCUSDT", "signal_hash": "abc"}
    intent = type("I", (), {"side": "long"})()
    pid = store.create_position_from_signal(
        signal_row,
        intent,
        {"executedQty": "0.02", "avgPrice": "50000", "orderId": 777},
        stop_loss_price=49000.0,
    )
    row = store.get_position_by_signal(3)
    assert row is not None
    assert int(row["id"]) == pid
    assert float(row["quantity"]) == pytest.approx(0.02)


def test_get_open_position_alias(store: PositionStore):
    store.create_position(
        symbol="ETHUSDT",
        side="SHORT",
        source_signal_id=None,
        signal_hash=None,
        quantity=0.5,
        entry_price=2000.0,
        entry_order_id=None,
    )
    assert store.get_open_position("ethusdt") is not None


def test_update_order_status_and_close_price(store: PositionStore):
    pid = store.create_position(
        symbol="BTCUSDT",
        side="LONG",
        source_signal_id=1,
        signal_hash=None,
        quantity=0.01,
        entry_price=100.0,
        entry_order_id=10,
    )
    rid = store.record_order(
        pid,
        order_kind="TP1",
        order_id=555,
        client_order_id="c1",
        side="SELL",
        order_type="TAKE_PROFIT_MARKET",
        quantity=0.01,
        stop_price=110.0,
        status="NEW",
    )
    assert store.update_order_status(555, "FILLED") >= 1
    with store._connect() as conn:
        st = conn.execute(
            "SELECT status FROM exchange_position_orders WHERE id=?",
            (rid,),
        ).fetchone()[0]
    assert st == "FILLED"

    store.close_position(pid, "TEST_EXIT", close_price=101.5)
    with store._connect() as conn:
        cp = conn.execute("SELECT close_price FROM exchange_positions WHERE id=?", (pid,)).fetchone()[0]
    assert float(cp) == pytest.approx(101.5)
