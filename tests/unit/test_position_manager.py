import os
import tempfile
from dataclasses import replace

import pytest

from execution.execution_health import read_execution_health, record_execution_health
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


def test_signal_price_long_skips_already_crossed_entry(temp_pm: PositionManager):
    client = temp_pm.client
    client.seed_mark_price("BTCUSDT", 52000.0)
    pm = PositionManager(client, replace(temp_pm.config, entry_style="signal_price"), temp_pm.store)
    signal_row = {
        "id": 99,
        "symbol": "BTCUSDT",
        "timeframe": "1D",
        "side": "LONG",
        "entry_price": 50000.0,
        "stop_loss": 49000.0,
        "tp1": 51000.0,
        "tp2": 52000.0,
        "tp3": 53000.0,
        "signal_hash": "h99",
    }
    out = pm.open_from_signal(signal_row)
    assert out["ok"] is True
    assert out["skipped"] == "signal_not_actionable:already_crossed_for_signal_price"


def test_signal_price_long_uses_stop_when_mark_below_entry(temp_pm: PositionManager):
    client = temp_pm.client
    client.seed_mark_price("BTCUSDT", 48000.0)
    pm = PositionManager(client, replace(temp_pm.config, entry_style="signal_price"), temp_pm.store)
    signal_row = {
        "id": 100,
        "symbol": "BTCUSDT",
        "timeframe": "1D",
        "side": "LONG",
        "entry_price": 50000.0,
        "stop_loss": 47000.0,
        "tp1": 51000.0,
        "tp2": 52000.0,
        "tp3": 53000.0,
        "signal_hash": "h100",
    }
    out = pm.open_from_signal(signal_row)
    assert out["ok"] is True
    with pm.store._connect() as conn:
        row = conn.execute(
            """
            SELECT order_type FROM exchange_position_orders
            WHERE order_kind='ENTRY' AND position_id=?
            """,
            (out["position_id"],),
        ).fetchone()
    assert row is not None
    assert row[0] == "STOP_MARKET"


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


def test_open_from_signal_places_sl_when_foreign_stop_wrong_exit_side(temp_pm: PositionManager):
    """Reduce-only STOP on book must match exit side; wrong side must not skip SL."""
    c = temp_pm.client
    c._orders.append(
        {
            "orderId": 99001,
            "symbol": "BTCUSDT",
            "type": "STOP_MARKET",
            "side": "BUY",
            "stopPrice": "40000",
            "origQty": "0.1",
            "reduceOnly": True,
            "status": "NEW",
            "clientOrderId": "ALIEN_SL",
        }
    )
    signal_row = {
        "id": 4242,
        "symbol": "BTCUSDT",
        "timeframe": "1D",
        "side": "LONG",
        "entry_price": 50000.0,
        "stop_loss": 49000.0,
        "tp1": 51000.0,
        "tp2": None,
        "tp3": None,
        "signal_hash": "h4242",
    }
    out = temp_pm.open_from_signal(signal_row)
    assert out["ok"] is True
    sl_sell = [
        o
        for o in c.get_open_orders("BTCUSDT")
        if o.get("type") == "STOP_MARKET" and str(o.get("side") or "").upper() == "SELL"
    ]
    assert len(sl_sell) >= 1


def test_ensure_protection_places_sl_and_tp_after_backfill_from_signals():
    import sqlite3

    from storage.wave_repository import WaveRepository

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = PositionStore(db_path=path)
    WaveRepository(db_path=path)
    client = FakeBinanceFuturesClient()
    cfg = _cfg()
    pm = PositionManager(client, cfg, store)
    try:
        client.seed_position("BTCUSDT", 0.1, 50000.0)
        store.create_position(
            symbol="BTCUSDT",
            side="LONG",
            source_signal_id=None,
            signal_hash=None,
            quantity=0.1,
            entry_price=50000.0,
            entry_order_id=None,
            stop_loss_price=49000.0,
            recovered=1,
        )
        with sqlite3.connect(path) as conn:
            conn.execute(
                """
                INSERT INTO signals (
                    created_at, updated_at, symbol, timeframe, side, status,
                    signal_hash, entry_price, stop_loss, tp1, tp2, tp3
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "2025-01-01T00:00:00+00:00",
                    "2025-01-01T00:00:00+00:00",
                    "BTCUSDT",
                    "1D",
                    "LONG",
                    "ACTIVE",
                    "sig77",
                    50000.0,
                    49000.0,
                    51000.0,
                    52000.0,
                    53000.0,
                ),
            )
            conn.commit()
        out = pm.ensure_protection("BTCUSDT")
        assert out["ok"] is True
        row = store.get_open_position_by_symbol("BTCUSDT")
        assert row is not None
        assert row["tp1_price"] is not None
        tps = [
            o
            for o in client.get_open_orders("BTCUSDT")
            if o.get("type") == "TAKE_PROFIT_MARKET"
            and str(o.get("side") or "").upper() == "SELL"
        ]
        assert len(tps) >= 1
    finally:
        os.unlink(path)


def test_close_for_signal_cancels_pending_entry_without_symbol_cleanup():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = PositionStore(db_path=path)
    client = FakeBinanceFuturesClient()
    pm = PositionManager(client, _cfg(), store)
    try:
        client._orders.append(
            {
                "orderId": 777,
                "symbol": "BTCUSDT",
                "type": "LIMIT",
                "side": "BUY",
                "origQty": "0.1",
                "reduceOnly": False,
                "status": "NEW",
                "clientOrderId": "E123EN",
            }
        )
        record_execution_health(
            "execution:pending_entry:123",
            {
                "order_id": 777,
                "symbol": "BTCUSDT",
                "client_order_id": "E123EN",
                "order_type": "LIMIT",
                "status": "NEW",
            },
            db_path=path,
        )

        out = pm.close_for_signal({"id": 123, "symbol": "BTCUSDT"}, "ENTRY_SKIPPED")

        assert out["ok"] is True
        assert out["pending_entry_canceled"] is True
        assert client.get_open_orders("BTCUSDT") == []
        assert read_execution_health("execution:pending_entry:123", db_path=path) is None
    finally:
        os.unlink(path)
