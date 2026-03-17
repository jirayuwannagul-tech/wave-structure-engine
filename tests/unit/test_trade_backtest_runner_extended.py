"""Extended tests for analysis/trade_backtest_runner.py to push coverage above 80%."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from analysis.trade_backtest import TradeSetup
from analysis.trade_backtest_runner import (
    TradeBacktestSummary,
    _summarize_results,
    run_trade_backtest,
    run_trade_backtest_suite,
)


# ---------- _summarize_results ----------

def _make_result(outcome: str, reward_r: float) -> dict:
    return {"outcome": outcome, "reward_r": reward_r}


def test_summarize_results_basic():
    results = [
        _make_result("TP1", 2.0),
        _make_result("STOP_LOSS", -1.0),
        _make_result("NO_TRIGGER", 0.0),
        _make_result("INVALID", 0.0),
        _make_result("OPEN", 0.5),
    ]
    summary = _summarize_results("1D", "TP1", 0.001, 0.0005, 10, 5, 3, results)
    assert isinstance(summary, TradeBacktestSummary)
    assert summary.tp_hits == 1
    assert summary.stop_losses == 1
    assert summary.no_trigger_trades == 1
    assert summary.invalid_setups == 1
    assert summary.open_trades == 1
    assert summary.triggered_trades == 3  # TP1 + STOP_LOSS + OPEN
    assert summary.win_rate == 0.5  # 1 / 2 closed
    assert summary.timeframe == "1D"
    assert summary.target_label == "TP1"


def test_summarize_results_empty_results():
    summary = _summarize_results("4H", "TP1", 0.0, 0.0, 5, 0, 0, [])
    assert summary.win_rate == 0.0
    assert summary.expectancy_r == 0.0
    assert summary.avg_r == 0.0
    assert summary.tp_hits == 0


def test_summarize_results_all_wins():
    results = [_make_result("TP1", 2.0), _make_result("TP1", 3.0)]
    summary = _summarize_results("1D", "TP1", 0.0, 0.0, 5, 2, 2, results)
    assert summary.win_rate == 1.0
    assert summary.expectancy_r == 2.5


def test_summarize_results_all_stops():
    results = [_make_result("STOP_LOSS", -1.0), _make_result("STOP_LOSS", -1.0)]
    summary = _summarize_results("1D", "TP1", 0.0, 0.0, 5, 2, 2, results)
    assert summary.win_rate == 0.0
    assert summary.stop_losses == 2
    assert summary.tp_hits == 0


def test_summarize_results_fee_bps_converted():
    summary = _summarize_results("1D", "TP1", 0.001, 0.0005, 5, 1, 1, [])
    assert summary.fee_bps == 10.0
    assert summary.slippage_bps == 5.0


def test_summarize_results_open_trades_contribute_to_triggered():
    results = [_make_result("TP1", 2.0), _make_result("OPEN", 0.3)]
    summary = _summarize_results("4H", "TP1", 0.0, 0.0, 5, 2, 2, results)
    assert summary.triggered_trades == 2  # TP1 + OPEN
    assert summary.open_trades == 1


def test_summarize_results_counts_time_stop_as_triggered_closed_trade():
    results = [_make_result("TIME_STOP", 0.15), _make_result("OVEREXTENDED_ENTRY", 0.0)]
    summary = _summarize_results("4H", "TP1", 0.0, 0.0, 5, 2, 2, results)
    assert summary.triggered_trades == 1
    assert summary.no_trigger_trades == 1
    assert summary.stop_losses == 1


# ---------- run_trade_backtest mocked ----------

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


def _fake_analysis_no_pattern():
    return {"has_pattern": False}


def _fake_analysis_with_pattern():
    scenario = MagicMock()
    scenario.bias = "BULLISH"
    scenario.confirmation = 105.0
    scenario.stop_loss = 95.0
    scenario.targets = [115.0, 125.0, 135.0]
    return {
        "has_pattern": True,
        "scenarios": [scenario],
        "primary_pattern_type": "ABC_CORRECTION",
    }


def test_run_trade_backtest_no_pattern(monkeypatch):
    """When build_dataframe_analysis returns no pattern, trades should be empty."""
    dummy_df = _make_dummy_ohlcv(30)
    monkeypatch.setattr("analysis.trade_backtest_runner.build_dataframe_analysis", lambda **kwargs: _fake_analysis_no_pattern())

    with patch("pandas.read_csv", return_value=dummy_df):
        result = run_trade_backtest("dummy.csv", "1D", min_window=10, step=5)

    assert result["summary"]["total_windows"] > 0
    assert result["summary"]["analyzed_cases"] == 0
    assert result["trades"] == []


def test_run_trade_backtest_with_invalid_setup(monkeypatch):
    """When build_trade_setup_from_scenario returns None, should record INVALID."""
    dummy_df = _make_dummy_ohlcv(30)
    monkeypatch.setattr("analysis.trade_backtest_runner.build_dataframe_analysis", lambda **kwargs: _fake_analysis_with_pattern())
    monkeypatch.setattr("analysis.trade_backtest_runner.build_trade_setup_from_scenario", lambda s: None)

    with patch("pandas.read_csv", return_value=dummy_df):
        result = run_trade_backtest("dummy.csv", "1D", min_window=10, step=5)

    invalid_trades = [t for t in result["trades"] if t["outcome"] == "INVALID"]
    assert invalid_trades


def test_run_trade_backtest_with_valid_setup(monkeypatch):
    """When everything is valid, simulate_trade should be called and results recorded."""
    dummy_df = _make_dummy_ohlcv(30)
    monkeypatch.setattr("analysis.trade_backtest_runner.build_dataframe_analysis", lambda **kwargs: _fake_analysis_with_pattern())

    from analysis.trade_backtest import TradeBacktestResult
    fake_trade_result = TradeBacktestResult(
        triggered=True,
        outcome="TP1",
        target_label="TP1",
        entry_index=1,
        exit_index=2,
        entry_price=105.0,
        exit_price=115.0,
        reward_r=2.0,
    )
    monkeypatch.setattr("analysis.trade_backtest_runner.simulate_trade_from_setup", lambda *args, **kwargs: fake_trade_result)

    with patch("pandas.read_csv", return_value=dummy_df):
        result = run_trade_backtest("dummy.csv", "1D", min_window=10, step=5, target_label="TP1")

    assert result["summary"]["analyzed_cases"] > 0
    tp_trades = [t for t in result["trades"] if t["outcome"] == "TP1"]
    assert tp_trades


def test_run_trade_backtest_no_scenarios(monkeypatch):
    """When has_pattern=True but no scenarios, skip without error."""
    dummy_df = _make_dummy_ohlcv(30)
    analysis = {"has_pattern": True, "scenarios": [], "primary_pattern_type": "FLAT"}
    monkeypatch.setattr("analysis.trade_backtest_runner.build_dataframe_analysis", lambda **kwargs: analysis)

    with patch("pandas.read_csv", return_value=dummy_df):
        result = run_trade_backtest("dummy.csv", "1D", min_window=10, step=5)

    assert result["summary"]["setups_built"] == 0
    assert result["trades"] == []


def test_run_trade_backtest_prefers_execution_scenarios(monkeypatch):
    dummy_df = _make_dummy_ohlcv(30)
    display_scenario = MagicMock(name="display")
    exec_scenario = MagicMock(name="exec")
    analysis = {
        "has_pattern": True,
        "scenarios": [display_scenario],
        "execution_scenarios": [exec_scenario],
        "primary_pattern_type": "FLAT",
    }
    used = {}

    monkeypatch.setattr("analysis.trade_backtest_runner.build_dataframe_analysis", lambda **kwargs: analysis)

    def fake_setup(scenario):
        used["scenario"] = scenario
        return TradeSetup(
            side="SHORT",
            entry_price=100.0,
            stop_loss=110.0,
            take_profit_1=90.0,
        )

    monkeypatch.setattr("analysis.trade_backtest_runner.build_trade_setup_from_scenario", fake_setup)
    monkeypatch.setattr(
        "analysis.trade_backtest_runner.simulate_trade_from_setup",
        lambda *args, **kwargs: type(
            "Result",
            (),
            {
                "outcome": "TP1",
                "reward_r": 1.0,
                "entry_index": 1,
                "exit_index": 2,
                "entry_price": 100.0,
                "exit_price": 90.0,
                "gross_pnl_per_unit": 10.0,
                "net_pnl_per_unit": 9.9,
                "fee_paid_per_unit": 0.1,
            },
        )(),
    )

    with patch("pandas.read_csv", return_value=dummy_df):
        run_trade_backtest("dummy.csv", "1D", min_window=10, step=5)

    assert used["scenario"] is exec_scenario


def test_run_trade_backtest_returns_dict_structure():
    """Smoke test: run_trade_backtest always returns the right shape."""
    dummy_df = _make_dummy_ohlcv(15)
    with (
        patch("pandas.read_csv", return_value=dummy_df),
        patch("analysis.trade_backtest_runner.build_dataframe_analysis", return_value={"has_pattern": False}),
    ):
        result = run_trade_backtest("dummy.csv", "4H", min_window=5, step=2)

    assert "summary" in result
    assert "trades" in result
    assert "total_windows" in result["summary"]


# ---------- run_trade_backtest_suite ----------

def test_run_trade_backtest_with_higher_timeframe(monkeypatch):
    """Pass higher_timeframe_csv_path to cover lines 109-111 and 140-151."""
    dummy_4h = _make_dummy_ohlcv(30)
    dummy_1d = _make_dummy_ohlcv(20)

    # Return different df depending on argument position
    csv_call_count = [0]
    def fake_read_csv(path, *args, **kwargs):
        csv_call_count[0] += 1
        if csv_call_count[0] == 1:
            return dummy_4h.copy()
        return dummy_1d.copy()

    monkeypatch.setattr("analysis.trade_backtest_runner.build_dataframe_analysis",
                        lambda **kwargs: {"has_pattern": False})

    with patch("pandas.read_csv", side_effect=fake_read_csv):
        result = run_trade_backtest(
            "dummy_4h.csv",
            "4H",
            min_window=10,
            step=5,
            higher_timeframe_csv_path="dummy_1d.csv",
            higher_timeframe_min_window=5,
        )

    assert "summary" in result
    # Both CSV paths were read
    assert csv_call_count[0] >= 2


def test_run_trade_backtest_suite_calls_all_targets(monkeypatch):
    """run_trade_backtest_suite should call run_trade_backtest for TP1, TP2, TP3."""
    dummy_df = _make_dummy_ohlcv(15)
    called_labels = []

    def fake_run_backtest(csv_path, timeframe, min_window, **kwargs):
        called_labels.append(kwargs.get("target_label"))
        return {"summary": {"total_windows": 0}, "trades": []}

    monkeypatch.setattr("analysis.trade_backtest_runner.run_trade_backtest", fake_run_backtest)

    result = run_trade_backtest_suite("dummy.csv", "1D", min_window=10)

    assert set(called_labels) == {"TP1", "TP2", "TP3"}
    assert "TP1" in result
    assert "TP2" in result
    assert "TP3" in result


def test_run_trade_backtest_with_parent_timeframe_csv(monkeypatch):
    """Pass parent_timeframe_csv_path to cover lines 122-124."""
    dummy_main = _make_dummy_ohlcv(30)
    dummy_weekly = _make_dummy_ohlcv(20)

    csv_call_count = [0]
    def fake_read_csv(path, *args, **kwargs):
        csv_call_count[0] += 1
        if csv_call_count[0] == 1:
            return dummy_main.copy()
        return dummy_weekly.copy()

    monkeypatch.setattr("analysis.trade_backtest_runner.build_dataframe_analysis",
                        lambda **kwargs: {"has_pattern": False})

    with patch("pandas.read_csv", side_effect=fake_read_csv):
        result = run_trade_backtest(
            "dummy_1d.csv",
            "1D",
            min_window=10,
            step=5,
            parent_timeframe_csv_path="dummy_weekly.csv",
            parent_timeframe_min_window=5,
        )

    assert "summary" in result
    assert csv_call_count[0] >= 2
