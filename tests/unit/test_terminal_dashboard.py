from types import SimpleNamespace

from services.terminal_dashboard import _build_signals, render_terminal_dashboard


def test_render_terminal_dashboard_shows_read_only_sections():
    output = render_terminal_dashboard(
        {
            "exchange": "binance futures",
            "symbol": "BTCUSDT",
            "monitored_symbols": ["BTCUSDT", "ETHUSDT"],
            "connection": "ok",
            "current_price": 71320,
            "orchestrator": "active",
            "news_monitor": "active",
            "wallet": "125.4",
            "available": "98.1",
            "upnl": "4.72",
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "side": "LONG",
                    "qty": 0.005,
                    "entry": 70800,
                    "mark": 71320,
                    "pnl": 2.6,
                }
            ],
            "signals": [
                {"symbol": "BTCUSDT", "timeframe": "1D", "bias": "BEARISH", "entry": 63030, "sl": 74050, "tp1": 52010},
                {"symbol": "ETHUSDT", "timeframe": "4H", "bias": "BULLISH", "entry": 70800, "sl": 69205.91, "tp1": 72394.09},
            ],
        }
    )

    assert "Elliott Wave Terminal" in output
    assert "$ system status" in output
    assert "$ balance" in output
    assert "$ positions" in output
    assert "$ signals" in output
    assert "symbol        BTCUSDT" in output
    assert "monitored     BTCUSDT, ETHUSDT" in output
    assert "price         71,320" in output
    assert "BTCUSDT LONG" in output
    assert "BTCUSDT  1D  bearish" in output
    assert "ETHUSDT  4H  bullish" in output


def test_render_terminal_dashboard_handles_no_positions():
    output = render_terminal_dashboard(
        {
            "exchange": "binance futures",
            "symbol": "BTCUSDT",
            "monitored_symbols": ["BTCUSDT"],
            "connection": "auth error",
            "current_price": None,
            "orchestrator": "n/a",
            "news_monitor": "n/a",
            "wallet": "-",
            "available": "-",
            "upnl": "-",
            "positions": [],
            "signals": [],
        }
    )

    assert "connection    auth error" in output
    assert "no open positions" in output


def test_build_signals_falls_back_to_all_scenarios_and_wave_summary():
    runtimes = [
        SimpleNamespace(
            symbol="BTCUSDT",
            analyses=[
                {
                    "timeframe": "4H",
                    "current_price": 71800.0,
                    "scenarios": [],
                    "all_scenarios": [
                        SimpleNamespace(
                            bias="BULLISH",
                            confirmation=70800.0,
                            invalidation=69205.91,
                            stop_loss=69205.91,
                            targets=[],
                        )
                    ],
                    "wave_summary": {
                        "bias": "BULLISH",
                        "confirm": 70800.0,
                        "stop_loss": 69205.91,
                    },
                }
            ],
        )
    ]

    signals = _build_signals(runtimes)

    assert signals == [
        {
            "symbol": "BTCUSDT",
            "timeframe": "4H",
            "bias": "BULLISH",
            "entry": 70800.0,
            "sl": 69205.91,
            "tp1": 72394.09,
        }
    ]


def test_build_signals_prefers_valid_wave_summary_over_invalid_selected_scenario():
    runtimes = [
        SimpleNamespace(
            symbol="BNBUSDT",
            analyses=[
                {
                    "timeframe": "1D",
                    "current_price": 665.0,
                    "scenarios": [
                        SimpleNamespace(
                            name="Main Corrective Pullback",
                            bias="BEARISH",
                            confirmation=666.16,
                            invalidation=607.86,
                            stop_loss=666.16,
                            targets=[600.51796, 595.98204, 592.75308],
                        )
                    ],
                    "wave_summary": {
                        "bias": "BULLISH",
                        "confirm": 666.16,
                        "stop_loss": 607.86,
                        "targets": [666.16, 686.14, 706.13],
                    },
                }
            ],
        )
    ]

    signals = _build_signals(runtimes)

    assert signals == [
        {
            "symbol": "BNBUSDT",
            "timeframe": "1D",
            "bias": "BULLISH",
            "entry": 666.16,
            "sl": 607.86,
            "tp1": 666.16,
        }
    ]
