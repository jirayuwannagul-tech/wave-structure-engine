import pandas as pd

from analysis.portfolio_backtest import TradeCandidate, run_global_portfolio_backtest, simulate_trade_lifecycle
from analysis.trade_backtest import TradeSetup


def test_simulate_trade_lifecycle_hits_all_targets_in_order():
    df = pd.DataFrame(
        [
            {"open_time": "2026-01-01", "open": 99.0, "high": 100.7, "low": 98.5, "close": 100.6},
            {"open_time": "2026-01-02", "open": 100.0, "high": 131.0, "low": 99.5, "close": 130.0},
            {"open_time": "2026-01-03", "open": 130.0, "high": 132.0, "low": 128.0, "close": 131.0},
        ]
    )
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    setup = TradeSetup(
        side="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit_1=110.0,
        take_profit_2=120.0,
        take_profit_3=130.0,
    )

    result = simulate_trade_lifecycle(df, setup)

    assert result.triggered is True
    assert result.outcome == "TP3_HIT"
    assert result.realized_targets == ["TP1", "TP2", "TP3"]
    assert result.realized_size_pct == 1.0
    assert result.reward_r > 1.0


def test_simulate_trade_lifecycle_partial_targets_then_stop():
    df = pd.DataFrame(
        [
            {"open_time": "2026-01-01", "open": 99.0, "high": 100.7, "low": 98.5, "close": 100.6},
            {"open_time": "2026-01-02", "open": 100.0, "high": 111.0, "low": 99.5, "close": 110.0},
            {"open_time": "2026-01-03", "open": 109.0, "high": 109.5, "low": 94.0, "close": 95.0},
        ]
    )
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    setup = TradeSetup(
        side="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit_1=110.0,
        take_profit_2=120.0,
        take_profit_3=130.0,
    )

    result = simulate_trade_lifecycle(df, setup)

    assert result.triggered is True
    assert result.outcome == "PARTIAL_STOPPED"
    assert result.realized_targets == ["TP1"]
    assert 0 < result.realized_size_pct < 1.0


def test_run_global_portfolio_backtest_prefers_higher_priority_same_timestamp(monkeypatch):
    entry_time = pd.Timestamp("2026-01-02T00:00:00Z")
    exit_time = pd.Timestamp("2026-01-03T00:00:00Z")

    def fake_build_trade_candidates(**kwargs):
        symbol = kwargs["symbol"]
        if symbol == "BTCUSDT":
            candidates = [
                TradeCandidate(
                    symbol="BTCUSDT",
                    timeframe="4H",
                    structure="ABC_CORRECTION",
                    scenario_name="Main Bearish",
                    side="LONG",
                    outcome="STOP_LOSS",
                    reward_r=-1.0,
                    entry_time=entry_time,
                    exit_time=exit_time,
                    entry_price=100.0,
                    exit_price=95.0,
                    priority_score=0.20,
                )
            ]
        else:
            candidates = [
                TradeCandidate(
                    symbol="ETHUSDT",
                    timeframe="4H",
                    structure="ABC_CORRECTION",
                    scenario_name="Main Bullish",
                    side="LONG",
                    outcome="TP1",
                    reward_r=1.0,
                    entry_time=entry_time,
                    exit_time=exit_time,
                    entry_price=100.0,
                    exit_price=110.0,
                    priority_score=0.80,
                )
            ]
        return {
            "summary": {
                "total_windows": 1,
                "analyzed_cases": 1,
                "setups_built": 1,
                "triggered_candidates": 1,
            },
            "candidates": [candidate.__dict__ for candidate in candidates],
        }

    monkeypatch.setattr("analysis.portfolio_backtest.build_trade_candidates", fake_build_trade_candidates)

    result = run_global_portfolio_backtest(
        datasets=[
            {"symbol": "BTCUSDT", "timeframe": "4H", "csv_path": "unused", "min_window": 1, "step": 1},
            {"symbol": "ETHUSDT", "timeframe": "4H", "csv_path": "unused", "min_window": 1, "step": 1},
        ],
        initial_capital=1000.0,
        risk_per_trade=0.02,
        max_concurrent=1,
    )

    assert result["overall"]["triggered_trades"] == 1
    assert result["trades"][0]["symbol"] == "ETHUSDT"
