import json

import pytest

import main


def test_resolve_timeframes_defaults_to_all():
    assert main._resolve_timeframes(None) == ["1D", "1W", "4H"]


def test_resolve_timeframes_rejects_unknown_timeframe():
    with pytest.raises(ValueError):
        main._resolve_timeframes(["2H"])


def test_run_trade_backtest_prints_summary(monkeypatch, capsys):
    monkeypatch.setattr(
        "main.run_trade_backtest_suite",
        lambda **kwargs: {
            "TP1": {"summary": {"timeframe": kwargs["timeframe"], "fee_bps": 4.0}},
            "TP2": {"summary": {"timeframe": kwargs["timeframe"], "fee_bps": 4.0}},
            "TP3": {"summary": {"timeframe": kwargs["timeframe"], "fee_bps": 4.0}},
        },
    )

    main._run_trade_backtest(
        symbol="BTCUSDT",
        timeframes=["1D"],
        step=1,
        fee_bps=4.0,
        slippage_bps=2.0,
    )

    output = json.loads(capsys.readouterr().out)
    assert output["1D"]["TP1"]["fee_bps"] == 4.0


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
