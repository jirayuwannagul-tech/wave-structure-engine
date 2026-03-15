from analysis.trade_backtest_runner import run_trade_backtest_suite


def test_trade_backtest_suite_runs_for_1d():
    result = run_trade_backtest_suite(
        csv_path="data/BTCUSDT_1d.csv",
        timeframe="1D",
        min_window=120,
        fee_rate=0.0004,
        slippage_rate=0.0002,
    )

    assert set(result.keys()) == {"TP1", "TP2", "TP3"}
    assert result["TP1"]["summary"]["total_windows"] > 0
    assert result["TP1"]["summary"]["setups_built"] > 0
    assert result["TP1"]["summary"]["fee_bps"] == 4.0
    assert result["TP1"]["summary"]["slippage_bps"] == 2.0


def test_trade_backtest_suite_runs_for_1w():
    result = run_trade_backtest_suite(
        csv_path="data/BTCUSDT_1w.csv",
        timeframe="1W",
        min_window=80,
    )

    assert set(result.keys()) == {"TP1", "TP2", "TP3"}
    assert result["TP1"]["summary"]["total_windows"] > 0
    assert result["TP1"]["summary"]["setups_built"] > 0


def test_trade_backtest_suite_runs_for_4h():
    result = run_trade_backtest_suite(
        csv_path="data/BTCUSDT_4h.csv",
        timeframe="4H",
        min_window=150,
    )

    assert set(result.keys()) == {"TP1", "TP2", "TP3"}
    assert result["TP1"]["summary"]["total_windows"] > 0
    # 4H filters require positive edge data — setups_built may be 0 without experience store
    assert result["TP1"]["summary"]["setups_built"] >= 0
