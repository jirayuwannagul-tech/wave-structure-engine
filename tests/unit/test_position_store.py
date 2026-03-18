import os
import sqlite3
import tempfile

import pytest

from storage.position_store import PositionStore


@pytest.fixture
def temp_store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        yield PositionStore(db_path=path)
    finally:
        os.unlink(path)


def test_position_store_creates_tables_and_open_close(temp_store: PositionStore):
    assert not temp_store.has_open_position_for_signal(1)
    pid = temp_store.create_position(
        symbol="BTCUSDT",
        side="LONG",
        source_signal_id=1,
        signal_hash="abc",
        quantity=0.01,
        entry_price=50000.0,
        entry_order_id=100,
    )
    assert pid > 0
    assert temp_store.has_open_position_for_signal(1)
    assert temp_store.has_open_position_for_symbol("BTCUSDT")
    temp_store.close_position(pid, "TEST")
    assert not temp_store.has_open_position_for_signal(1)

    with temp_store._connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM exchange_position_events WHERE position_id = ?", (pid,)).fetchone()[0]
    assert n >= 2
