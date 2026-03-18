import os
import tempfile

import pytest

from execution.fake_binance_client import FakeBinanceFuturesClient
from execution.models import ExecutionConfig
from execution.position_manager import PositionManager
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
def temp_pm():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = PositionStore(db_path=path)
    client = FakeBinanceFuturesClient()
    pm = PositionManager(client, _cfg(), store)
    try:
        yield pm
    finally:
        os.unlink(path)


def test_open_from_signal_places_entry_sl_tp(temp_pm: PositionManager):
    signal_row = {
        "id": 42,
        "symbol": "BTCUSDT",
        "timeframe": "1D",
        "side": "LONG",
        "entry_price": 50000.0,
        "stop_loss": 49000.0,
        "tp1": 51000.0,
        "tp2": 52000.0,
        "tp3": 53000.0,
        "signal_hash": "h",
    }
    out = temp_pm.open_from_signal(signal_row)
    assert out["ok"] is True
    assert out.get("position_id")

    with temp_pm.store._connect() as conn:
        rows = conn.execute(
            "SELECT order_kind, reduce_only FROM exchange_position_orders WHERE position_id = ? ORDER BY id",
            (out["position_id"],),
        ).fetchall()
    kinds = [r[0] for r in rows]
    assert "ENTRY" in kinds
    assert "SL" in kinds
    assert "TP1" in kinds
    entry_ro = next(r[1] for r in rows if r[0] == "ENTRY")
    assert entry_ro == 0
    sl_ro = next(r[1] for r in rows if r[0] == "SL")
    assert sl_ro == 1


def test_open_same_signal_idempotent(temp_pm: PositionManager):
    signal_row = {
        "id": 99,
        "symbol": "BTCUSDT",
        "timeframe": "1D",
        "side": "LONG",
        "entry_price": 50000.0,
        "stop_loss": 49000.0,
        "tp1": 51000.0,
        "tp2": None,
        "tp3": None,
        "signal_hash": "x",
    }
    assert temp_pm.open_from_signal(signal_row)["ok"] is True
    out2 = temp_pm.open_from_signal(signal_row)
    assert out2.get("skipped") == "already_open_for_signal"


def test_close_symbol_cleanup_cancels_orders_closes_db(temp_pm: PositionManager):
    signal_row = {
        "id": 7,
        "symbol": "BTCUSDT",
        "timeframe": "1D",
        "side": "LONG",
        "entry_price": 50000.0,
        "stop_loss": 49000.0,
        "tp1": 51000.0,
        "tp2": None,
        "tp3": None,
    }
    temp_pm.open_from_signal(signal_row)
    client = temp_pm.client
    assert len(client.get_open_orders("BTCUSDT")) >= 1
    assert abs(float(client.get_position("BTCUSDT")["positionAmt"])) > 0

    r = temp_pm.close_symbol_cleanup("BTCUSDT", "TP3_HIT")
    assert r["ok"] is True
    assert len(client.get_open_orders("BTCUSDT")) == 0
    assert abs(float(client.get_position("BTCUSDT")["positionAmt"])) < 1e-9
    assert temp_pm.store.get_open_position_by_symbol("BTCUSDT") is None


def test_close_position_market_alias(temp_pm: PositionManager):
    signal_row = {
        "id": 8,
        "symbol": "BTCUSDT",
        "timeframe": "1D",
        "side": "LONG",
        "entry_price": 50000.0,
        "stop_loss": 49000.0,
        "tp1": 51000.0,
        "tp2": None,
        "tp3": None,
    }
    temp_pm.open_from_signal(signal_row)
    assert temp_pm.close_position_market("BTCUSDT", "TIME_STOP_HIT")["ok"] is True
    assert temp_pm.store.get_open_position("BTCUSDT") is None


def test_entry_duplicate_response_reads_position_from_exchange():
    from execution.position_manager import _entry_duplicate_response

    c = FakeBinanceFuturesClient()
    c.seed_position("BTCUSDT", 0.02, 48000.0)
    out = _entry_duplicate_response(
        RuntimeError("duplicate order sent"),
        c,
        "BTCUSDT",
        "LONG",
        1.0,
        1.0,
    )
    assert out is not None
    assert float(out["executedQty"]) == pytest.approx(0.02)
    assert float(out["avgPrice"]) == pytest.approx(48000.0)
