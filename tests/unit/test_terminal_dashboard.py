from services.terminal_dashboard import render_terminal_dashboard


def test_render_terminal_dashboard_shows_read_only_sections():
    output = render_terminal_dashboard(
        {
            "exchange": "binance futures",
            "symbol": "BTCUSDT",
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
                {"timeframe": "1D", "bias": "BEARISH", "entry": 63030, "sl": 74050, "tp1": 52010},
                {"timeframe": "4H", "bias": "BULLISH", "entry": 70800, "sl": 69205.91, "tp1": 72394.09},
            ],
        }
    )

    assert "Elliott Wave Terminal" in output
    assert "$ system status" in output
    assert "$ balance" in output
    assert "$ positions" in output
    assert "$ signals" in output
    assert "symbol        BTCUSDT" in output
    assert "price         71,320" in output
    assert "BTCUSDT LONG" in output
    assert "1D  bearish" in output
    assert "4H  bullish" in output


def test_render_terminal_dashboard_handles_no_positions():
    output = render_terminal_dashboard(
        {
            "exchange": "binance futures",
            "symbol": "BTCUSDT",
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
