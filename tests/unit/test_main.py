import json

import pytest

import main


def test_resolve_timeframes_defaults_to_all():
    assert main._resolve_timeframes(None) == ["1D", "1W", "4H"]


def test_resolve_symbols_prefers_symbols_list():
    assert main._resolve_symbols("BTCUSDT", ["BTCUSDT", "ethusdt", "BTCUSDT"]) == ["BTCUSDT", "ETHUSDT"]


def test_dataset_path_uses_symbol_and_timeframe():
    assert main._dataset_path("ETHUSDT", "4H") == "data/ETHUSDT_4h.csv"


def test_resolve_timeframes_rejects_unknown_timeframe():
    with pytest.raises(ValueError):
        main._resolve_timeframes(["2H"])


def test_run_trade_backtest_prints_summary(monkeypatch, capsys):
    monkeypatch.setattr("main._resolve_backtest_dataset", lambda **kwargs: "data/BTCUSDT_1d.csv")
    monkeypatch.setattr(
        "main.run_trade_backtest_suite",
        lambda **kwargs: {
            "TP1": {"summary": {"timeframe": kwargs["timeframe"], "fee_bps": 4.0}},
            "TP2": {"summary": {"timeframe": kwargs["timeframe"], "fee_bps": 4.0}},
            "TP3": {"summary": {"timeframe": kwargs["timeframe"], "fee_bps": 4.0}},
        },
    )

    main._run_trade_backtest(
        symbols=["BTCUSDT"],
        timeframes=["1D"],
        step=1,
        fee_bps=4.0,
        slippage_bps=2.0,
    )

    output = json.loads(capsys.readouterr().out)
    assert output["BTCUSDT"]["1D"]["TP1"]["fee_bps"] == 4.0


def test_resolve_backtest_dataset_fetches_when_missing(monkeypatch):
    monkeypatch.setattr("main.os.path.exists", lambda path: False)
    monkeypatch.setattr(
        "main._fetch_backtest_dataset",
        lambda symbol, timeframe, limit=500, years=None: f"data/{symbol}_{timeframe}.csv",
    )

    assert main._resolve_backtest_dataset("DOGEUSDT", "4H") == "data/DOGEUSDT_4H.csv"


def test_terminal_dashboard_command_routes_to_dashboard(monkeypatch):
    captured = {}

    def fake_run_terminal_dashboard(symbol: str, watch: bool, refresh_seconds: float):
        captured["symbol"] = symbol
        captured["watch"] = watch
        captured["refresh_seconds"] = refresh_seconds

    monkeypatch.setattr("main.run_terminal_dashboard", fake_run_terminal_dashboard)

    parser = main.build_parser()
    args = parser.parse_args(["terminal-dashboard", "--symbol", "BTCUSDT", "--watch", "--refresh-seconds", "3"])

    if args.command == "terminal-dashboard":
        main.run_terminal_dashboard(
            symbol=args.symbol,
            watch=args.watch,
            refresh_seconds=args.refresh_seconds,
        )

    assert captured == {"symbol": "BTCUSDT", "watch": True, "refresh_seconds": 3.0}


def test_web_dashboard_command_routes_to_server(monkeypatch):
    captured = {}

    def fake_run_web_dashboard(symbol: str, host: str, port: int, refresh_seconds: float):
        captured["symbol"] = symbol
        captured["host"] = host
        captured["port"] = port
        captured["refresh_seconds"] = refresh_seconds

    monkeypatch.setattr("main.run_web_dashboard", fake_run_web_dashboard)

    parser = main.build_parser()
    args = parser.parse_args(
        ["web-dashboard", "--symbol", "BTCUSDT", "--host", "0.0.0.0", "--port", "8080", "--refresh-seconds", "2"]
    )

    if args.command == "web-dashboard":
        main.run_web_dashboard(
            symbol=args.symbol,
            host=args.host,
            port=args.port,
            refresh_seconds=args.refresh_seconds,
        )

    assert captured == {"symbol": "BTCUSDT", "host": "0.0.0.0", "port": 8080, "refresh_seconds": 2.0}


def test_run_portfolio_backtest_prints_summary(monkeypatch, capsys):
    monkeypatch.setattr("main._resolve_backtest_dataset", lambda **kwargs: "data/BTCUSDT_4h.csv")
    monkeypatch.setattr(
        "main.load_execution_config",
        lambda: type(
            "Cfg",
            (),
            {
                "tp1_size_pct": 0.4,
                "tp2_size_pct": 0.3,
                "tp3_size_pct": 0.3,
                "risk_per_trade": 0.1,
            },
        )(),
    )
    monkeypatch.setattr(
        "main.run_portfolio_backtest",
        lambda **kwargs: {"summary": {"timeframe": kwargs["timeframe"], "final_equity_usdt": 1200.0}},
    )

    main._run_portfolio_backtest(
        symbols=["BTCUSDT"],
        timeframes=["4H"],
        step=10,
        fee_bps=4.0,
        slippage_bps=2.0,
        initial_capital=1000.0,
    )

    output = json.loads(capsys.readouterr().out)
    assert output["BTCUSDT"]["4H"]["final_equity_usdt"] == 1200.0


def test_run_global_portfolio_backtest_prints_summary(monkeypatch, capsys):
    monkeypatch.setattr("main._resolve_backtest_dataset", lambda **kwargs: "data/BTCUSDT_4h.csv")
    monkeypatch.setattr(
        "main.load_execution_config",
        lambda: type(
            "Cfg",
            (),
            {
                "tp1_size_pct": 0.4,
                "tp2_size_pct": 0.3,
                "tp3_size_pct": 0.3,
                "risk_per_trade": 0.1,
            },
        )(),
    )
    monkeypatch.setattr(
        "main.run_global_portfolio_backtest",
        lambda **kwargs: {"overall": {"final_equity_usdt": 1111.0}},
    )

    main._run_global_portfolio_backtest(
        symbols=["BTCUSDT"],
        timeframes=["4H"],
        step=10,
        fee_bps=4.0,
        slippage_bps=2.0,
        initial_capital=1000.0,
    )

    output = json.loads(capsys.readouterr().out)
    assert output["overall"]["final_equity_usdt"] == 1111.0


def test_refresh_experience_store_prints_summary(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("main._resolve_backtest_dataset", lambda **kwargs: "data/BTCUSDT_4h.csv")
    monkeypatch.setattr(
        "main.load_execution_config",
        lambda: type(
            "Cfg",
            (),
            {
                "tp1_size_pct": 0.4,
                "tp2_size_pct": 0.3,
                "tp3_size_pct": 0.3,
            },
        )(),
    )
    monkeypatch.setattr(
        "main.build_trade_candidates",
        lambda **kwargs: {
            "summary": {"triggered_candidates": 2},
            "candidates": [
                {
                    "symbol": "BTCUSDT",
                    "timeframe": kwargs["timeframe"],
                    "structure": "ABC_CORRECTION",
                    "side": "LONG",
                    "reward_r": 1.0,
                },
                {
                    "symbol": "BTCUSDT",
                    "timeframe": kwargs["timeframe"],
                    "structure": "ABC_CORRECTION",
                    "side": "LONG",
                    "reward_r": -0.5,
                },
            ],
        },
    )
    monkeypatch.setattr("main.save_experience_store", lambda payload: tmp_path / "experience_store.json")

    main._refresh_experience_store(
        symbols=["BTCUSDT"],
        timeframes=["4H"],
        step=10,
        fee_bps=4.0,
        slippage_bps=2.0,
    )

    output = json.loads(capsys.readouterr().out)
    assert output["record_count"] == 2
    assert output["pattern_edges"] == 1
