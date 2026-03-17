"""Extended tests for analysis/trade_backtest.py to push coverage to 95%+."""
from __future__ import annotations

import pandas as pd
import pytest

from analysis.trade_backtest import (
    TradeSetup,
    _effective_entry_price,
    _is_long,
    _risk_per_unit,
    build_trade_setup_from_scenario,
    simulate_trade_from_setup,
)


def _candle(ts, o, h, l, c):
    return {"open_time": ts, "open": o, "high": h, "low": l, "close": c}


def _df(*candles):
    df = pd.DataFrame(list(candles))
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    return df


def _long(entry=100.0, stop=90.0, tp1=115.0, tp2=125.0, tp3=135.0):
    return TradeSetup(side="LONG", entry_price=entry, stop_loss=stop,
                     take_profit_1=tp1, take_profit_2=tp2, take_profit_3=tp3)


def _short(entry=100.0, stop=110.0, tp1=85.0, tp2=75.0, tp3=65.0):
    return TradeSetup(side="SHORT", entry_price=entry, stop_loss=stop,
                     take_profit_1=tp1, take_profit_2=tp2, take_profit_3=tp3)


# ---------- target_for ----------

def test_target_for_valid_labels():
    setup = _long(tp1=110.0, tp2=120.0, tp3=130.0)
    assert setup.target_for("TP1") == 110.0
    assert setup.target_for("TP2") == 120.0
    assert setup.target_for("TP3") == 130.0


def test_target_for_unknown_label_returns_none():
    setup = _long()
    assert setup.target_for("TP4") is None
    assert setup.target_for("") is None
    assert setup.target_for("INVALID") is None


# ---------- _risk_per_unit ----------

def test_risk_per_unit_long():
    setup = TradeSetup(side="LONG", entry_price=100.0, stop_loss=90.0)
    assert _risk_per_unit(setup) == 10.0


def test_risk_per_unit_short():
    setup = TradeSetup(side="SHORT", entry_price=100.0, stop_loss=110.0)
    assert _risk_per_unit(setup) == 10.0


# ---------- _effective_entry_price ----------

def test_effective_entry_price_long_no_slippage():
    setup = _long(entry=100.0)
    assert _effective_entry_price(setup, 0.0) == 100.0


def test_effective_entry_price_short_no_slippage():
    setup = _short(entry=100.0)
    assert _effective_entry_price(setup, 0.0) == 100.0


def test_effective_entry_price_long_with_slippage():
    setup = _long(entry=100.0)
    # LONG buys at higher price with slippage
    assert _effective_entry_price(setup, 0.01) == pytest.approx(101.0)


def test_effective_entry_price_short_with_slippage():
    setup = _short(entry=100.0)
    # SHORT sells at lower price with slippage
    assert _effective_entry_price(setup, 0.01) == pytest.approx(99.0)


# ---------- build_trade_setup_from_scenario ----------

def test_build_trade_setup_invalid_bias():
    class S:
        bias = "NEUTRAL"
        confirmation = 100.0
        stop_loss = 90.0
        targets = [110.0]
    assert build_trade_setup_from_scenario(S()) is None


def test_build_trade_setup_no_confirmation():
    class S:
        bias = "BULLISH"
        confirmation = None
        stop_loss = 90.0
        targets = [110.0]
    assert build_trade_setup_from_scenario(S()) is None


def test_build_trade_setup_no_stop_loss():
    class S:
        bias = "BULLISH"
        confirmation = 100.0
        stop_loss = None
        targets = [110.0]
    assert build_trade_setup_from_scenario(S()) is None


def test_build_trade_setup_short_from_bearish():
    class S:
        bias = "BEARISH"
        confirmation = 100.0
        stop_loss = 110.0
        targets = [85.0, 75.0]
    setup = build_trade_setup_from_scenario(S())
    assert setup is not None
    assert setup.side == "SHORT"
    assert setup.take_profit_1 == 85.0
    assert setup.take_profit_2 == 75.0
    assert setup.take_profit_3 is None


# ---------- simulate_trade_from_setup edge cases ----------

def test_simulate_no_tp_returns_invalid():
    """When setup has no TPs for the requested target_label → INVALID."""
    df = _df(
        _candle("2026-01-01", 99.0, 100.5, 98.0, 100.0),
        _candle("2026-01-02", 100.0, 110.0, 99.0, 108.0),
    )
    setup = TradeSetup(side="LONG", entry_price=100.0, stop_loss=90.0)  # no TPs
    result = simulate_trade_from_setup(df, setup, target_label="TP1")
    assert result.outcome == "INVALID"
    assert not result.triggered


def test_simulate_df_too_short():
    """Single-row df → NO_TRIGGER."""
    df = _df(_candle("2026-01-01", 99.0, 101.0, 98.0, 100.0))
    setup = _long()
    result = simulate_trade_from_setup(df, setup)
    assert result.outcome == "NO_TRIGGER"
    assert not result.triggered


def test_simulate_no_trigger():
    """Price never reaches entry → NO_TRIGGER."""
    df = _df(
        _candle("2026-01-01", 80.0, 85.0, 79.0, 82.0),
        _candle("2026-01-02", 82.0, 88.0, 80.0, 85.0),
    )
    setup = _long(entry=100.0, stop=90.0)
    result = simulate_trade_from_setup(df, setup)
    assert result.outcome == "NO_TRIGGER"
    assert not result.triggered


def test_simulate_risk_zero_returns_invalid():
    """Entry price == stop_loss → risk=0 → INVALID."""
    df = _df(
        _candle("2026-01-01", 100.0, 100.7, 99.5, 100.6),  # trigger
        _candle("2026-01-02", 100.0, 102.0, 99.5, 101.0),
    )
    setup = TradeSetup(side="LONG", entry_price=100.0, stop_loss=100.0, take_profit_1=115.0)
    result = simulate_trade_from_setup(df, setup)
    assert result.outcome == "INVALID"


def test_simulate_stop_gap_at_open():
    """Entry candle's open is below stop for LONG → immediate STOP_LOSS."""
    df = _df(
        _candle("2026-01-01", 100.0, 100.7, 99.5, 100.6),  # trigger
        _candle("2026-01-02", 89.0, 90.0, 88.0, 89.0),      # open below stop
    )
    setup = _long(entry=100.0, stop=90.0)
    result = simulate_trade_from_setup(df, setup)
    assert result.triggered
    assert result.outcome == "STOP_LOSS"


def test_simulate_target_gap_at_open_blocks_overextended_entry():
    """If the next candle opens far beyond the planned entry, the system skips chasing it."""
    df = _df(
        _candle("2026-01-01", 100.0, 100.7, 99.5, 100.6),  # trigger
        _candle("2026-01-02", 116.0, 120.0, 115.0, 118.0),  # open above TP1=115
    )
    setup = _long(entry=100.0, stop=90.0, tp1=115.0)
    result = simulate_trade_from_setup(df, setup, target_label="TP1")
    assert result.triggered is False
    assert result.outcome == "OVEREXTENDED_ENTRY"
    assert result.entry_index is None


def test_simulate_stop_and_target_same_candle():
    """Both stop and target hit in same candle → STOP_LOSS (conservative)."""
    df = _df(
        _candle("2026-01-01", 100.0, 100.7, 99.5, 100.6),  # trigger
        _candle("2026-01-02", 100.0, 116.0, 88.0, 102.0),  # high>=115 AND low<=90
    )
    setup = _long(entry=100.0, stop=90.0, tp1=115.0)
    result = simulate_trade_from_setup(df, setup, target_label="TP1")
    assert result.triggered
    assert result.outcome == "STOP_LOSS"


def test_simulate_open_trade():
    """No stop or target hit → OPEN."""
    df = _df(
        _candle("2026-01-01", 100.0, 100.7, 99.5, 100.6),  # trigger
        _candle("2026-01-02", 100.0, 105.0, 98.0, 103.0),  # safe range
        _candle("2026-01-03", 103.0, 108.0, 99.0, 106.0),  # still safe
    )
    setup = _long(entry=100.0, stop=90.0, tp1=115.0)
    result = simulate_trade_from_setup(df, setup, target_label="TP1")
    assert result.triggered
    assert result.outcome == "OPEN"


def test_simulate_trade_blocks_fakeout_trigger():
    df = _df(
        _candle("2026-01-01", 99.0, 112.0, 98.5, 100.6),  # closes through entry with long upper wick
        _candle("2026-01-02", 100.1, 104.0, 99.8, 103.0),
    )
    setup = _long(entry=100.0, stop=90.0, tp1=115.0)
    result = simulate_trade_from_setup(df, setup, target_label="TP1", timeframe="4H")
    assert result.triggered is False
    assert result.outcome == "FAKEOUT_TRIGGER"


def test_simulate_trade_time_stop():
    df = _df(
        _candle("2026-01-01", 99.0, 100.8, 98.5, 100.6),  # trigger
        _candle("2026-01-02", 100.0, 104.0, 99.0, 101.0),
        _candle("2026-01-03", 101.0, 103.5, 99.5, 100.8),
        _candle("2026-01-04", 100.8, 103.0, 99.7, 100.9),
        _candle("2026-01-05", 100.9, 103.2, 99.6, 100.7),
        _candle("2026-01-06", 100.7, 102.8, 99.8, 100.5),
        _candle("2026-01-07", 100.5, 102.7, 99.9, 100.4),
        _candle("2026-01-08", 100.4, 102.6, 99.8, 100.2),
    )
    setup = _long(entry=100.0, stop=90.0, tp1=115.0)
    result = simulate_trade_from_setup(df, setup, target_label="TP1", timeframe="4H")
    assert result.triggered is True
    assert result.outcome == "TIME_STOP"
    assert result.exit_index == 7


def test_simulate_trigger_at_last_candle_no_entry():
    """Trigger on last candle → entry_index >= len(df) → NO_TRIGGER."""
    df = _df(
        _candle("2026-01-01", 98.0, 99.0, 97.0, 98.0),    # no trigger
        _candle("2026-01-02", 100.0, 101.0, 99.0, 100.0),  # trigger at index 1 (last)
    )
    setup = _long(entry=100.0, stop=90.0)
    result = simulate_trade_from_setup(df, setup)
    assert result.outcome == "NO_TRIGGER"
    assert not result.triggered


def test_simulate_short_stop_loss():
    """SHORT trade hits stop → STOP_LOSS."""
    df = _df(
        _candle("2026-01-01", 100.0, 100.0, 99.3, 99.4),  # trigger (close <= 100*0.994)
        _candle("2026-01-02", 100.0, 112.0, 99.5, 111.0),  # high >= 110 → stop
    )
    setup = _short(entry=100.0, stop=110.0, tp1=85.0)
    result = simulate_trade_from_setup(df, setup, target_label="TP1")
    assert result.triggered
    assert result.outcome == "STOP_LOSS"


def test_simulate_short_tp_hit():
    """SHORT trade hits TP1."""
    df = _df(
        _candle("2026-01-01", 100.0, 100.0, 99.3, 99.4),  # trigger (close <= 100*0.994)
        _candle("2026-01-02", 100.0, 102.0, 84.0, 85.0),   # low <= 85 → TP1
    )
    setup = _short(entry=100.0, stop=110.0, tp1=85.0)
    result = simulate_trade_from_setup(df, setup, target_label="TP1")
    assert result.triggered
    assert result.outcome == "TP1"
    assert result.reward_r > 0
