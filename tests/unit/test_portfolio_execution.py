"""Portfolio caps, hedge multi-leg, close_for_signal."""

import os
import tempfile

import pytest

from execution.exchange_info import clear_exchange_info_cache
from execution.fake_binance_client import FakeBinanceFuturesClient
from execution.models import ExecutionConfig
from execution.position_manager import PositionManager
from storage.position_store import PositionStore


def _base_cfg(**kw):
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
        **kw,
    )


@pytest.fixture
def tmp_env():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["WAVE_DB_PATH"] = path
    store = PositionStore(db_path=path)
    client = FakeBinanceFuturesClient()
    clear_exchange_info_cache(client)
    try:
        yield store, client, path
    finally:
        os.unlink(path)


def _sig(sid: int, symbol: str, side: str = "LONG"):
    if symbol == "BTCUSDT":
        if side.upper() == "SHORT":
            ep, sl, tp = 50000.0, 51000.0, 49000.0
        else:
            ep, sl, tp = 50000.0, 49000.0, 51000.0
    elif side.upper() == "SHORT":
        ep, sl, tp = 3000.0, 3100.0, 2900.0
    else:
        ep, sl, tp = 3000.0, 2900.0, 3100.0
    return {
        "id": sid,
        "symbol": symbol,
        "timeframe": "1D",
        "side": side,
        "entry_price": ep,
        "stop_loss": sl,
        "tp1": tp,
        "tp2": None,
        "tp3": None,
        "signal_hash": f"h{sid}",
    }


def test_portfolio_max_open_positions_skips(tmp_env):
    store, client, _ = tmp_env
    cfg = _base_cfg(portfolio_max_open_positions=1)
    pm = PositionManager(client, cfg, store)
    assert pm.open_from_signal(_sig(1, "BTCUSDT"))["ok"] is True
    out = pm.open_from_signal(_sig(2, "ETHUSDT"))
    assert out.get("skipped") == "portfolio_max_open_positions"


def test_portfolio_max_risk_fraction_skips(tmp_env):
    store, client, _ = tmp_env
    store.create_position(
        symbol="BTCUSDT",
        side="LONG",
        source_signal_id=999,
        signal_hash="x",
        quantity=1.0,
        entry_price=50000.0,
        entry_order_id=None,
        stop_loss_price=49900.0,
        recovered=0,
    )
    cfg = _base_cfg(portfolio_max_risk_fraction=0.001)
    pm = PositionManager(client, cfg, store)
    out = pm.open_from_signal(_sig(1, "ETHUSDT"))
    assert out.get("skipped") == "portfolio_max_risk_fraction"


def test_hedge_long_and_short_same_symbol(tmp_env):
    store, client, _ = tmp_env
    cfg = _base_cfg(hedge_position_mode=True)
    pm = PositionManager(client, cfg, store)
    assert pm.open_from_signal(_sig(10, "BTCUSDT", "LONG"))["ok"] is True
    assert pm.open_from_signal(_sig(11, "BTCUSDT", "SHORT"))["ok"] is True
    assert store.count_open_positions() == 2


def test_close_for_signal_closes_matching_row(tmp_env):
    store, client, _ = tmp_env
    pm = PositionManager(client, _base_cfg(), store)
    row = _sig(21, "BTCUSDT")
    assert pm.open_from_signal(row)["ok"] is True
    assert pm.close_for_signal(row, "TP3_HIT")["ok"] is True
    assert store.get_open_position_by_signal(21) is None


def test_second_long_same_symbol_hedge_still_blocked(tmp_env):
    store, client, _ = tmp_env
    cfg = _base_cfg(hedge_position_mode=True)
    pm = PositionManager(client, cfg, store)
    assert pm.open_from_signal(_sig(30, "BTCUSDT", "LONG"))["ok"] is True
    out = pm.open_from_signal(_sig(31, "BTCUSDT", "LONG"))
    assert out.get("skipped") == "symbol_leg_already_open"
