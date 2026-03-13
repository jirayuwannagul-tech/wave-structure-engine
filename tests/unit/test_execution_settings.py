from execution.settings import load_execution_config


def test_load_execution_config_from_env(monkeypatch):
    monkeypatch.setenv("BINANCE_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("BINANCE_LIVE_ORDER_ENABLED", "false")
    monkeypatch.setenv("BINANCE_USE_TESTNET", "true")
    monkeypatch.setenv("BINANCE_FUTURES_API_KEY", "key")
    monkeypatch.setenv("BINANCE_FUTURES_API_SECRET", "secret")
    monkeypatch.setenv("BINANCE_RISK_PER_TRADE", "0.02")
    monkeypatch.setenv("BINANCE_DEFAULT_LEVERAGE", "5")
    monkeypatch.setenv("BINANCE_MARGIN_TYPE", "cross")
    monkeypatch.setenv("BINANCE_TP1_SIZE_PCT", "0.4")
    monkeypatch.setenv("BINANCE_TP2_SIZE_PCT", "0.3")
    monkeypatch.setenv("BINANCE_TP3_SIZE_PCT", "0.3")

    config = load_execution_config()

    assert config.enabled is True
    assert config.live_order_enabled is False
    assert config.use_testnet is True
    assert config.api_key == "key"
    assert config.api_secret == "secret"
    assert config.risk_per_trade == 0.02
    assert config.leverage == 5
    assert config.margin_type == "CROSS"
    assert config.tp1_size_pct == 0.4
    assert config.tp2_size_pct == 0.3
    assert config.tp3_size_pct == 0.3
    assert config.tp_allocation_total == 1.0
