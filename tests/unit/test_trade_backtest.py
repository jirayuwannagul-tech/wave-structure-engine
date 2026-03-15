import pandas as pd

from analysis.trade_backtest import (
    TradeSetup,
    build_trade_setup_from_scenario,
    simulate_trade_from_setup,
)
from scenarios.scenario_engine import Scenario


def test_build_trade_setup_from_bullish_scenario():
    scenario = Scenario(
        name="Main Bullish",
        condition="price holds above 100",
        interpretation="correction likely finished",
        target="move higher",
        bias="BULLISH",
        invalidation=95.0,
        confirmation=100.0,
        stop_loss=95.0,
        targets=[110.0, 120.0, 130.0],
    )

    setup = build_trade_setup_from_scenario(scenario)

    assert setup is not None
    assert setup.side == "LONG"
    assert setup.entry_price == 100.0
    assert setup.stop_loss == 95.0
    assert setup.take_profit_1 == 110.0
    assert setup.take_profit_2 == 120.0
    assert setup.take_profit_3 == 130.0


def test_simulate_trade_hits_tp1_for_long():
    df = pd.DataFrame(
        [
            {"open": 99.0, "high": 100.7, "low": 98.5, "close": 100.6},
            {"open": 100.0, "high": 111.0, "low": 99.5, "close": 110.0},
            {"open": 110.0, "high": 112.0, "low": 108.0, "close": 111.0},
        ]
    )
    setup = TradeSetup(
        side="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit_1=110.0,
        take_profit_2=120.0,
        take_profit_3=130.0,
    )

    result = simulate_trade_from_setup(df, setup, target_label="TP1")

    assert result.triggered is True
    assert result.outcome == "TP1"
    assert result.entry_index == 1
    assert result.exit_index == 1
    assert result.reward_r == 2.0
    assert result.net_pnl_per_unit == 10.0
    assert result.entry_price == 100.0


def test_simulate_trade_hits_stop_loss_for_short():
    df = pd.DataFrame(
        [
            {"open": 100.0, "high": 101.0, "low": 94.0, "close": 94.5},
            {"open": 95.0, "high": 101.0, "low": 94.5, "close": 100.5},
            {"open": 100.5, "high": 102.0, "low": 99.0, "close": 101.0},
        ]
    )
    setup = TradeSetup(
        side="SHORT",
        entry_price=95.0,
        stop_loss=100.0,
        take_profit_1=90.0,
        take_profit_2=85.0,
        take_profit_3=80.0,
    )

    result = simulate_trade_from_setup(df, setup, target_label="TP1")

    assert result.triggered is True
    assert result.outcome == "STOP_LOSS"
    assert result.entry_index == 1
    assert result.exit_index == 1
    assert result.reward_r == -1.0
    assert result.net_pnl_per_unit < 0
    assert result.entry_price == 95.0


def test_simulate_trade_returns_no_trigger_when_confirmation_never_breaks():
    df = pd.DataFrame(
        [
            {"open": 98.0, "high": 99.0, "low": 97.0, "close": 98.5},
            {"open": 98.5, "high": 99.5, "low": 97.5, "close": 99.0},
            {"open": 99.0, "high": 99.8, "low": 98.0, "close": 99.2},
        ]
    )
    setup = TradeSetup(
        side="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit_1=110.0,
        take_profit_2=120.0,
        take_profit_3=130.0,
    )

    result = simulate_trade_from_setup(df, setup, target_label="TP2")

    assert result.triggered is False
    assert result.outcome == "NO_TRIGGER"


def test_simulate_trade_applies_fee_and_slippage_to_reward():
    df = pd.DataFrame(
        [
            {"open": 99.0, "high": 100.7, "low": 98.5, "close": 100.6},
            {"open": 100.0, "high": 111.0, "low": 99.5, "close": 110.0},
            {"open": 110.0, "high": 112.0, "low": 108.0, "close": 111.0},
        ]
    )
    setup = TradeSetup(
        side="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit_1=110.0,
        take_profit_2=120.0,
        take_profit_3=130.0,
    )

    result = simulate_trade_from_setup(
        df,
        setup,
        target_label="TP1",
        fee_rate=0.001,
        slippage_rate=0.001,
    )

    assert result.triggered is True
    assert result.outcome == "TP1"
    assert result.reward_r < 2.0
    assert result.fee_paid_per_unit > 0
    assert result.net_pnl_per_unit < result.gross_pnl_per_unit


def test_simulate_trade_enters_on_next_candle_open():
    df = pd.DataFrame(
        [
            {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.6},
            {"open": 103.0, "high": 111.0, "low": 102.0, "close": 110.0},
            {"open": 110.0, "high": 112.0, "low": 108.0, "close": 111.0},
        ]
    )
    setup = TradeSetup(
        side="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit_1=110.0,
    )

    result = simulate_trade_from_setup(df, setup, target_label="TP1")

    assert result.triggered is True
    assert result.entry_index == 1
    assert result.entry_price == 103.0
    assert result.outcome == "TP1"


def test_simulate_trade_stops_out_if_entry_candle_gaps_beyond_stop():
    df = pd.DataFrame(
        [
            {"open": 98.0, "high": 101.0, "low": 97.0, "close": 100.6},
            {"open": 94.0, "high": 96.0, "low": 93.0, "close": 95.0},
            {"open": 95.0, "high": 97.0, "low": 94.0, "close": 96.0},
        ]
    )
    setup = TradeSetup(
        side="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit_1=110.0,
    )

    result = simulate_trade_from_setup(df, setup, target_label="TP1")

    assert result.triggered is True
    assert result.entry_index == 1
    assert result.exit_index == 1
    assert result.outcome == "STOP_LOSS"
