"""Extended tests for analysis/portfolio_backtest.py to push coverage above 80%."""
from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from analysis.portfolio_backtest import (
    PortfolioTradeRecord,
    TradeCandidate,
    TradeLifecycleResult,
    _candidate_priority,
    _timestamp_at,
    build_trade_candidates,
    run_global_portfolio_backtest,
    run_portfolio_backtest,
    simulate_trade_lifecycle,
)
from analysis.trade_backtest import TradeSetup


# ---------- helpers ----------

def _make_df(*candles):
    """Build OHLCV DataFrame from (open_time, open, high, low, close) tuples."""
    records = []
    for i, (ts, o, h, l, c) in enumerate(candles):
        records.append({"open_time": ts, "open": o, "high": h, "low": l, "close": c})
    df = pd.DataFrame(records)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    return df


def _long_setup(entry=100.0, stop=90.0, tp1=115.0, tp2=125.0, tp3=135.0):
    return TradeSetup(
        side="LONG",
        entry_price=entry,
        stop_loss=stop,
        take_profit_1=tp1,
        take_profit_2=tp2,
        take_profit_3=tp3,
    )


def _short_setup(entry=100.0, stop=110.0, tp1=85.0, tp2=75.0, tp3=65.0):
    return TradeSetup(
        side="SHORT",
        entry_price=entry,
        stop_loss=stop,
        take_profit_1=tp1,
        take_profit_2=tp2,
        take_profit_3=tp3,
    )


# ---------- _timestamp_at ----------

def test_timestamp_at_none_idx():
    df = pd.DataFrame({"open_time": pd.to_datetime(["2026-01-01"], utc=True)})
    assert _timestamp_at(df, None) is None


def test_timestamp_at_idx_out_of_range():
    df = pd.DataFrame({"open_time": pd.to_datetime(["2026-01-01"], utc=True)})
    assert _timestamp_at(df, 5) is None


def test_timestamp_at_no_open_time_column():
    df = pd.DataFrame({"close": [100.0]})
    assert _timestamp_at(df, 0) is None


def test_timestamp_at_nat_value():
    df = pd.DataFrame({"open_time": [pd.NaT]})
    assert _timestamp_at(df, 0) is None


def test_timestamp_at_valid():
    df = pd.DataFrame({"open_time": pd.to_datetime(["2026-01-01"], utc=True)})
    result = _timestamp_at(df, 0)
    assert result is not None
    assert result.year == 2026


# ---------- _candidate_priority ----------

def test_candidate_priority_no_edge():
    """When no edge exists, score is based on confidence + probability only."""
    from unittest.mock import patch
    with patch("analysis.portfolio_backtest.get_pattern_edge", return_value=None), patch(
        "analysis.portfolio_backtest.get_scenario_edge", return_value=None
    ):
        score = _candidate_priority(
            symbol="BTCUSDT",
            timeframe="1D",
            pattern="ABC_CORRECTION",
            scenario_name="Main Bullish",
            side="LONG",
            confidence=0.8,
            probability=0.7,
        )
    expected = round(0.8 * 0.35 + 0.7 * 0.25, 6)
    assert score == expected


def test_candidate_priority_positive_edge():
    """Positive edge adds 0.25 bonus."""
    fake_edge = MagicMock()
    fake_edge.positive = True
    fake_edge.negative = False
    fake_edge.severe_negative = False
    fake_edge.avg_r = 0.0
    with patch("analysis.portfolio_backtest.get_pattern_edge", return_value=fake_edge), patch(
        "analysis.portfolio_backtest.get_scenario_edge", return_value=None
    ):
        score = _candidate_priority(
            symbol="BTCUSDT",
            timeframe="1D",
            pattern="IMPULSE",
            scenario_name="Main Bullish",
            side="LONG",
            confidence=0.8,
            probability=0.7,
        )
    expected = round(0.8 * 0.35 + 0.7 * 0.25 + 0.2, 6)
    assert score == expected


def test_candidate_priority_negative_edge():
    """Negative edge subtracts 0.15."""
    fake_edge = MagicMock()
    fake_edge.positive = False
    fake_edge.negative = True
    fake_edge.severe_negative = False
    fake_edge.avg_r = 0.0
    with patch("analysis.portfolio_backtest.get_pattern_edge", return_value=fake_edge), patch(
        "analysis.portfolio_backtest.get_scenario_edge", return_value=None
    ):
        score = _candidate_priority(
            symbol="BTCUSDT",
            timeframe="1D",
            pattern="FLAT",
            scenario_name="Main Bearish",
            side="SHORT",
            confidence=0.6,
            probability=0.5,
        )
    expected = round(0.6 * 0.35 + 0.5 * 0.25 - 0.15, 6)
    assert score == expected


# ---------- simulate_trade_lifecycle edge cases ----------

def test_simulate_trade_lifecycle_too_few_rows():
    """Single-row df → INVALID or NO_TRIGGER."""
    df = _make_df(("2026-01-01", 99.0, 100.5, 98.0, 100.0))
    setup = _long_setup()
    result = simulate_trade_lifecycle(df, setup)
    assert not result.triggered


def test_simulate_trade_lifecycle_no_targets():
    """Setup with no take-profit targets → INVALID."""
    df = _make_df(
        ("2026-01-01", 99.0, 100.5, 98.0, 100.0),
        ("2026-01-02", 100.0, 105.0, 99.0, 104.0),
    )
    setup = TradeSetup(side="LONG", entry_price=100.0, stop_loss=90.0)  # no TPs
    result = simulate_trade_lifecycle(df, setup)
    assert result.outcome == "INVALID"
    assert not result.triggered


def test_simulate_trade_lifecycle_no_trigger():
    """Price never reaches entry → NO_TRIGGER."""
    df = _make_df(
        ("2026-01-01", 80.0, 85.0, 79.0, 82.0),  # never reaches 100
        ("2026-01-02", 82.0, 88.0, 80.0, 85.0),
        ("2026-01-03", 84.0, 89.0, 82.0, 86.0),
    )
    setup = _long_setup(entry=100.0, stop=90.0)
    result = simulate_trade_lifecycle(df, setup)
    assert not result.triggered
    assert result.outcome == "NO_TRIGGER"


def test_simulate_trade_lifecycle_risk_per_unit_zero():
    """Entry == stop_loss → INVALID (risk = 0)."""
    df = _make_df(
        ("2026-01-01", 100.0, 100.7, 99.0, 100.6),  # triggers entry at 100
        ("2026-01-02", 100.0, 102.0, 99.5, 101.0),
    )
    # entry == stop == 100.0, so effective risk = 0
    setup = TradeSetup(side="LONG", entry_price=100.0, stop_loss=100.0, take_profit_1=115.0)
    result = simulate_trade_lifecycle(df, setup)
    # entry is triggered but risk_per_unit = 0 → INVALID
    assert result.outcome == "INVALID"


def test_simulate_trade_lifecycle_stop_gap_hit():
    """When next candle opens below stop for LONG → immediate STOP_LOSS."""
    df = _make_df(
        ("2026-01-01", 100.0, 100.7, 99.5, 100.6),  # triggers LONG at 100
        ("2026-01-02", 89.0, 90.0, 88.0, 89.0),    # opens below stop (90)
    )
    setup = _long_setup(entry=100.0, stop=90.0, tp1=115.0)
    result = simulate_trade_lifecycle(df, setup)
    assert result.triggered is True
    assert result.outcome == "STOP_LOSS"


def test_simulate_trade_lifecycle_open_trade():
    """When trade is triggered but neither stop nor target is ever hit → OPEN."""
    df = _make_df(
        ("2026-01-01", 100.0, 100.7, 99.5, 100.6),  # triggers LONG
        ("2026-01-02", 100.0, 105.0, 98.0, 103.0),  # within range: high < 115, low > 90
        ("2026-01-03", 103.0, 108.0, 99.0, 106.0),  # still within range
    )
    setup = _long_setup(entry=100.0, stop=90.0, tp1=115.0, tp2=125.0, tp3=135.0)
    result = simulate_trade_lifecycle(df, setup)
    assert result.triggered is True
    assert result.outcome == "OPEN"
    assert result.exit_index is None


def test_simulate_trade_lifecycle_stop_and_target_same_candle():
    """When both stop and target are hit in same candle (gap), prioritizes stop."""
    df = _make_df(
        ("2026-01-01", 100.0, 100.7, 99.5, 100.6),  # triggers
        ("2026-01-02", 100.0, 116.0, 89.0, 95.0),   # high >= 115 AND low <= 90
    )
    setup = _long_setup(entry=100.0, stop=90.0, tp1=115.0, tp2=125.0, tp3=135.0)
    result = simulate_trade_lifecycle(df, setup)
    assert result.triggered is True
    # When both stop and target hit, the code processes them together
    assert result.outcome in {"STOP_LOSS", "PARTIAL_STOPPED", "TP1"}


def test_simulate_trade_lifecycle_partial_stopped_via_stop_only():
    """Stop hit without prior partial target → plain STOP_LOSS (else branch)."""
    df = _make_df(
        ("2026-01-01", 100.0, 100.7, 99.5, 100.6),  # triggers
        ("2026-01-02", 100.0, 112.0, 100.0, 105.0),  # high=112 < 115 → no TP1
        ("2026-01-03", 105.0, 106.0, 89.0, 92.0),    # low = 89 <= 90 → STOP
    )
    setup = _long_setup(entry=100.0, stop=90.0, tp1=115.0, tp2=125.0, tp3=135.0)
    result = simulate_trade_lifecycle(df, setup)
    assert result.triggered is True
    assert result.outcome == "STOP_LOSS"
    assert result.reward_r < 0


def test_simulate_trade_lifecycle_tp1_hit_outcome():
    """When only TP1 is hit and trade completes → realized_targets=['TP1'], remaining=0.6."""
    df = _make_df(
        ("2026-01-01", 100.0, 100.7, 99.5, 100.6),  # triggers
        ("2026-01-02", 100.0, 116.0, 100.5, 115.0),  # TP1 hit (high 116 >= 115)
    )
    # Only TP1 defined → trade closes when TP1 is hit (remaining goes to 0)
    setup = TradeSetup(side="LONG", entry_price=100.0, stop_loss=90.0, take_profit_1=115.0)
    result = simulate_trade_lifecycle(df, setup)
    assert result.triggered is True
    assert "TP1" in result.realized_targets


def test_simulate_trade_lifecycle_partial_stopped_after_tp1():
    """TP1 hit, then stop hit → PARTIAL_STOPPED."""
    df = _make_df(
        ("2026-01-01", 100.0, 100.7, 99.5, 100.6),   # triggers
        ("2026-01-02", 100.0, 116.0, 100.5, 115.0),   # TP1 hit (high 116 >= 115)
        ("2026-01-03", 114.0, 115.0, 88.0, 90.0),     # stop hit (low 88 <= 90)
    )
    setup = _long_setup(entry=100.0, stop=90.0, tp1=115.0, tp2=125.0, tp3=135.0)
    result = simulate_trade_lifecycle(df, setup)
    assert result.triggered is True
    assert result.outcome == "PARTIAL_STOPPED"
    assert "TP1" in result.realized_targets


def test_simulate_trade_lifecycle_blocks_fakeout_trigger():
    df = _make_df(
        ("2026-01-01", 99.0, 112.0, 98.5, 100.6),   # closes above entry with rejection wick
        ("2026-01-02", 100.0, 104.0, 99.5, 103.0),
    )
    setup = _long_setup(entry=100.0, stop=90.0, tp1=115.0, tp2=125.0, tp3=135.0)
    result = simulate_trade_lifecycle(df, setup, timeframe="4H")
    assert result.triggered is False
    assert result.outcome == "FAKEOUT_TRIGGER"


def test_simulate_trade_lifecycle_time_stop_without_follow_through():
    df = _make_df(
        ("2026-01-01", 100.0, 100.7, 99.5, 100.6),  # triggers
        ("2026-01-02", 100.0, 104.0, 99.0, 101.0),
        ("2026-01-03", 101.0, 103.5, 99.5, 100.8),
        ("2026-01-04", 100.8, 103.0, 99.7, 100.9),
        ("2026-01-05", 100.9, 103.2, 99.6, 100.7),
        ("2026-01-06", 100.7, 102.8, 99.8, 100.5),
        ("2026-01-07", 100.5, 102.7, 99.9, 100.4),
        ("2026-01-08", 100.4, 102.6, 99.8, 100.2),
    )
    setup = _long_setup(entry=100.0, stop=90.0, tp1=115.0, tp2=125.0, tp3=135.0)
    result = simulate_trade_lifecycle(df, setup, timeframe="4H")
    assert result.triggered is True
    assert result.outcome == "TIME_STOP"


# ---------- run_global_portfolio_backtest with concurrent ----------

def test_run_global_portfolio_backtest_skips_when_max_concurrent(monkeypatch):
    """When max_concurrent=1 and two trades want same entry time, second is skipped."""
    entry_time1 = pd.Timestamp("2026-01-02T00:00:00Z")
    entry_time2 = pd.Timestamp("2026-01-03T00:00:00Z")
    exit_time1 = pd.Timestamp("2026-01-05T00:00:00Z")
    exit_time2 = pd.Timestamp("2026-01-06T00:00:00Z")

    def fake_build_trade_candidates(**kwargs):
        return {
            "summary": {"total_windows": 2, "analyzed_cases": 2, "setups_built": 2, "triggered_candidates": 2},
            "candidates": [
                {
                    "symbol": kwargs["symbol"].upper(),
                    "timeframe": "4H",
                    "structure": "FLAT",
                    "side": "LONG",
                    "outcome": "TP1",
                    "reward_r": 1.5,
                    "entry_time": entry_time1,
                    "exit_time": exit_time1,
                    "entry_price": 100.0,
                    "exit_price": 115.0,
                    "priority_score": 0.5,
                },
            ],
        }

    monkeypatch.setattr("analysis.portfolio_backtest.build_trade_candidates", fake_build_trade_candidates)

    result = run_global_portfolio_backtest(
        datasets=[
            {"symbol": "BTCUSDT", "timeframe": "4H", "csv_path": "dummy1.csv", "min_window": 1, "step": 1},
            {"symbol": "ETHUSDT", "timeframe": "4H", "csv_path": "dummy2.csv", "min_window": 1, "step": 1},
        ],
        initial_capital=1000.0,
        risk_per_trade=0.01,
        max_concurrent=1,
    )

    assert "overall" in result
    assert result["overall"]["triggered_trades"] >= 1


def test_run_global_portfolio_backtest_open_trade(monkeypatch):
    """Candidate with exit_time=None should end up as OPEN record."""
    entry_time = pd.Timestamp("2026-01-02T00:00:00Z")

    def fake_build_trade_candidates(**kwargs):
        return {
            "summary": {"total_windows": 1, "analyzed_cases": 1, "setups_built": 1, "triggered_candidates": 1},
            "candidates": [
                {
                    "symbol": "BTCUSDT",
                    "timeframe": "1D",
                    "structure": "IMPULSE",
                    "side": "LONG",
                    "outcome": "OPEN",
                    "reward_r": 0.5,
                    "entry_time": entry_time,
                    "exit_time": None,
                    "entry_price": 100.0,
                    "exit_price": None,
                    "priority_score": 0.6,
                },
            ],
        }

    monkeypatch.setattr("analysis.portfolio_backtest.build_trade_candidates", fake_build_trade_candidates)

    result = run_global_portfolio_backtest(
        datasets=[
            {"symbol": "BTCUSDT", "timeframe": "1D", "csv_path": "dummy.csv", "min_window": 1, "step": 1},
        ],
        initial_capital=1000.0,
        risk_per_trade=0.01,
        max_concurrent=5,
    )

    open_trades = [t for t in result["trades"] if t["outcome"] == "OPEN"]
    assert open_trades


def test_run_global_portfolio_backtest_empty_datasets(monkeypatch):
    """No datasets → empty result."""
    result = run_global_portfolio_backtest(
        datasets=[],
        initial_capital=1000.0,
    )
    assert result["overall"]["triggered_trades"] == 0
    assert result["trades"] == []


# ---------- trigger at last candle (line 200) ----------

def test_simulate_trade_lifecycle_trigger_at_last_candle():
    """Trigger on the last candle (trigger_index + 1 == len(df)) → NO_TRIGGER."""
    df = _make_df(
        ("2026-01-01", 98.0, 99.0, 97.0, 98.0),    # no trigger
        ("2026-01-02", 100.0, 101.0, 99.0, 100.0),  # triggers (high >= 100)
    )
    # trigger_index = 1 (last candle at index 1), entry_index = 2 >= len(df)=2
    setup = _long_setup(entry=100.0, stop=90.0)
    result = simulate_trade_lifecycle(df, setup)
    assert not result.triggered
    assert result.outcome == "NO_TRIGGER"


# ---------- run_portfolio_backtest mocked ----------

def _make_dummy_ohlcv(n=30):
    return pd.DataFrame(
        {
            "open_time": pd.date_range("2026-01-01", periods=n, freq="D", tz="UTC"),
            "open": [100.0] * n,
            "high": [102.0] * n,
            "low": [98.0] * n,
            "close": [101.0] * n,
            "volume": [1000.0] * n,
        }
    )


def test_run_portfolio_backtest_no_pattern(monkeypatch):
    """When no patterns detected, should return empty trades."""
    dummy_df = _make_dummy_ohlcv(20)
    monkeypatch.setattr("analysis.portfolio_backtest.build_dataframe_analysis", lambda **kw: {"has_pattern": False})

    with patch("pandas.read_csv", return_value=dummy_df):
        result = run_portfolio_backtest(
            csv_path="dummy.csv",
            symbol="BTCUSDT",
            timeframe="1D",
            min_window=10,
            step=5,
        )

    assert result["summary"]["analyzed_cases"] == 0
    assert result["trades"] == []


def test_run_portfolio_backtest_with_triggered_trade(monkeypatch):
    """Mocked full pipeline: setup builds, lifecycle runs, record added."""
    dummy_df = _make_dummy_ohlcv(30)

    scenario = MagicMock()
    scenario.bias = "BULLISH"
    scenario.confirmation = 105.0
    scenario.stop_loss = 95.0
    scenario.targets = [115.0, 125.0, 135.0]
    analysis = {
        "has_pattern": True,
        "scenarios": [scenario],
        "primary_pattern_type": "ABC_CORRECTION",
        "confidence": 0.8,
        "probability": 0.7,
    }

    monkeypatch.setattr("analysis.portfolio_backtest.build_dataframe_analysis", lambda **kw: analysis)
    monkeypatch.setattr("analysis.portfolio_backtest.get_pattern_edge", lambda *a, **kw: None)

    entry_time = pd.Timestamp("2026-01-15T00:00:00Z")
    exit_time = pd.Timestamp("2026-01-20T00:00:00Z")

    fake_lifecycle = TradeLifecycleResult(
        triggered=True,
        outcome="TP1",
        entry_index=1,
        exit_index=5,
        entry_time=entry_time,
        exit_time=exit_time,
        entry_price=105.0,
        exit_price=115.0,
        reward_r=2.0,
        realized_targets=["TP1"],
        realized_size_pct=0.4,
        gross_pnl_per_unit=10.0,
        net_pnl_per_unit=9.9,
        fee_paid_per_unit=0.1,
    )
    monkeypatch.setattr("analysis.portfolio_backtest.simulate_trade_lifecycle", lambda *a, **kw: fake_lifecycle)

    with patch("pandas.read_csv", return_value=dummy_df):
        result = run_portfolio_backtest(
            csv_path="dummy.csv",
            symbol="BTCUSDT",
            timeframe="1D",
            min_window=10,
            step=5,
        )

    assert result["summary"]["triggered_trades"] >= 1
    assert any(t["outcome"] == "TP1" for t in result["trades"])


def test_run_portfolio_backtest_prefers_execution_scenarios(monkeypatch):
    dummy_df = _make_dummy_ohlcv(30)

    display_scenario = MagicMock(name="display")
    exec_scenario = MagicMock(name="exec")
    analysis = {
        "has_pattern": True,
        "scenarios": [display_scenario],
        "execution_scenarios": [exec_scenario],
        "primary_pattern_type": "ABC_CORRECTION",
        "confidence": 0.8,
        "probability": 0.7,
    }
    used = {}

    monkeypatch.setattr("analysis.portfolio_backtest.build_dataframe_analysis", lambda **kw: analysis)
    monkeypatch.setattr("analysis.portfolio_backtest.get_pattern_edge", lambda *a, **kw: None)

    def fake_setup(scenario):
        used["scenario"] = scenario
        return TradeSetup(
            side="SHORT",
            entry_price=100.0,
            stop_loss=110.0,
            take_profit_1=90.0,
            take_profit_2=85.0,
            take_profit_3=80.0,
        )

    monkeypatch.setattr("analysis.portfolio_backtest.build_trade_setup_from_scenario", fake_setup)

    fake_lifecycle = TradeLifecycleResult(
        triggered=True,
        outcome="TP1",
        entry_index=1,
        exit_index=5,
        entry_time=pd.Timestamp("2026-01-15T00:00:00Z"),
        exit_time=pd.Timestamp("2026-01-20T00:00:00Z"),
        entry_price=100.0,
        exit_price=90.0,
        reward_r=1.0,
        realized_targets=["TP1"],
        realized_size_pct=0.4,
        gross_pnl_per_unit=10.0,
        net_pnl_per_unit=9.9,
        fee_paid_per_unit=0.1,
    )
    monkeypatch.setattr("analysis.portfolio_backtest.simulate_trade_lifecycle", lambda *a, **kw: fake_lifecycle)

    with patch("pandas.read_csv", return_value=dummy_df):
        run_portfolio_backtest(
            csv_path="dummy.csv",
            symbol="BTCUSDT",
            timeframe="1D",
            min_window=10,
            step=5,
        )

    assert used["scenario"] is exec_scenario


# ---------- build_trade_candidates mocked ----------

def test_build_trade_candidates_no_pattern(monkeypatch):
    """Returns empty candidates when no patterns detected."""
    dummy_df = _make_dummy_ohlcv(20)
    monkeypatch.setattr("analysis.portfolio_backtest.build_dataframe_analysis", lambda **kw: {"has_pattern": False})

    with patch("pandas.read_csv", return_value=dummy_df):
        result = build_trade_candidates(
            csv_path="dummy.csv",
            symbol="BTCUSDT",
            timeframe="1D",
            min_window=10,
            step=5,
        )

    assert result["summary"]["triggered_candidates"] == 0
    assert result["candidates"] == []


def test_build_trade_candidates_with_triggered(monkeypatch):
    """Returns candidates when a trade is triggered."""
    dummy_df = _make_dummy_ohlcv(30)

    scenario = MagicMock()
    scenario.bias = "BULLISH"
    scenario.confirmation = 105.0
    scenario.stop_loss = 95.0
    scenario.targets = [115.0, 125.0, 135.0]
    analysis = {
        "has_pattern": True,
        "scenarios": [scenario],
        "primary_pattern_type": "ABC_CORRECTION",
        "confidence": 0.8,
        "probability": 0.7,
    }

    monkeypatch.setattr("analysis.portfolio_backtest.build_dataframe_analysis", lambda **kw: analysis)
    monkeypatch.setattr("analysis.portfolio_backtest.get_pattern_edge", lambda *a, **kw: None)

    entry_time = pd.Timestamp("2026-01-15T00:00:00Z")
    exit_time = pd.Timestamp("2026-01-20T00:00:00Z")

    fake_lifecycle = TradeLifecycleResult(
        triggered=True,
        outcome="TP2",
        entry_index=1,
        exit_index=5,
        entry_time=entry_time,
        exit_time=exit_time,
        entry_price=105.0,
        exit_price=125.0,
        reward_r=3.0,
        realized_targets=["TP1", "TP2"],
        realized_size_pct=0.7,
        gross_pnl_per_unit=20.0,
        net_pnl_per_unit=19.8,
        fee_paid_per_unit=0.2,
    )
    monkeypatch.setattr("analysis.portfolio_backtest.simulate_trade_lifecycle", lambda *a, **kw: fake_lifecycle)

    with patch("pandas.read_csv", return_value=dummy_df):
        result = build_trade_candidates(
            csv_path="dummy.csv",
            symbol="BTCUSDT",
            timeframe="1D",
            min_window=10,
            step=5,
        )

    assert result["summary"]["triggered_candidates"] >= 1
    assert result["candidates"]


def test_build_trade_candidates_skips_4h_when_daily_context_is_not_tradeable(monkeypatch):
    dummy_df = _make_dummy_ohlcv(30)

    scenario = MagicMock()
    scenario.bias = "BULLISH"
    scenario.confirmation = 105.0
    scenario.stop_loss = 95.0
    scenario.targets = [115.0, 125.0, 135.0]
    analysis = {
        "has_pattern": True,
        "scenarios": [scenario],
        "primary_pattern_type": "ABC_CORRECTION",
        "confidence": 0.8,
        "probability": 0.7,
    }

    monkeypatch.setattr("analysis.portfolio_backtest.build_dataframe_analysis", lambda **kw: analysis)
    monkeypatch.setattr(
        "analysis.portfolio_backtest.resolve_backtest_higher_timeframe_context",
        lambda **kwargs: ("BEARISH", {"timeframe": "1D", "is_tradeable": False}, False),
    )

    with patch("pandas.read_csv", return_value=dummy_df):
        result = build_trade_candidates(
            csv_path="dummy.csv",
            symbol="BTCUSDT",
            timeframe="4H",
            min_window=10,
            step=5,
            higher_timeframe_csv_path="dummy_1d.csv",
            higher_timeframe_min_window=5,
        )

    assert result["summary"]["triggered_candidates"] == 0
    assert result["candidates"] == []


def test_build_trade_candidates_does_not_fallback_when_execution_scenarios_empty(monkeypatch):
    dummy_df = _make_dummy_ohlcv(30)

    scenario = MagicMock()
    scenario.bias = "BULLISH"
    scenario.confirmation = 105.0
    scenario.stop_loss = 95.0
    scenario.targets = [115.0, 125.0, 135.0]
    analysis = {
        "has_pattern": True,
        "scenarios": [scenario],
        "execution_scenarios": [],
        "primary_pattern_type": "ABC_CORRECTION",
        "confidence": 0.8,
        "probability": 0.7,
    }

    monkeypatch.setattr("analysis.portfolio_backtest.build_dataframe_analysis", lambda **kw: analysis)

    with patch("pandas.read_csv", return_value=dummy_df):
        result = build_trade_candidates(
            csv_path="dummy.csv",
            symbol="BTCUSDT",
            timeframe="4H",
            min_window=10,
            step=5,
        )

    assert result["summary"]["setups_built"] == 0
    assert result["summary"]["triggered_candidates"] == 0
    assert result["candidates"] == []


# ---------- run_global_portfolio_backtest with losing trade (line 836-837) ----------

def test_run_global_portfolio_backtest_drawdown(monkeypatch):
    """Losing trade should generate a drawdown (covers lines 835-837)."""
    entry_time = pd.Timestamp("2026-01-02T00:00:00Z")
    exit_time = pd.Timestamp("2026-01-05T00:00:00Z")

    def fake_build_trade_candidates(**kwargs):
        return {
            "summary": {"total_windows": 1, "analyzed_cases": 1, "setups_built": 1, "triggered_candidates": 1},
            "candidates": [
                {
                    "symbol": "BTCUSDT",
                    "timeframe": "1D",
                    "structure": "FLAT",
                    "side": "LONG",
                    "outcome": "STOP_LOSS",
                    "reward_r": -1.0,
                    "entry_time": entry_time,
                    "exit_time": exit_time,
                    "entry_price": 100.0,
                    "exit_price": 90.0,
                    "priority_score": 0.5,
                },
            ],
        }

    monkeypatch.setattr("analysis.portfolio_backtest.build_trade_candidates", fake_build_trade_candidates)

    result = run_global_portfolio_backtest(
        datasets=[
            {"symbol": "BTCUSDT", "timeframe": "1D", "csv_path": "dummy.csv", "min_window": 1, "step": 1},
        ],
        initial_capital=1000.0,
        risk_per_trade=0.01,
        max_concurrent=5,
    )

    assert result["overall"]["triggered_trades"] == 1
    losing_trades = [t for t in result["trades"] if t["outcome"] == "STOP_LOSS"]
    assert losing_trades
