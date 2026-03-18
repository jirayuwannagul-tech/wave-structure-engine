import pytest

from execution.settings import load_execution_config


def test_load_execution_config_rejects_non_positive_tp_sum(monkeypatch):
    monkeypatch.setenv("BINANCE_TP1_SIZE_PCT", "0")
    monkeypatch.setenv("BINANCE_TP2_SIZE_PCT", "0")
    monkeypatch.setenv("BINANCE_TP3_SIZE_PCT", "0")
    monkeypatch.delenv("BINANCE_EXECUTION_ENABLED", raising=False)
    with pytest.raises(ValueError, match="positive"):
        load_execution_config()


def test_load_execution_config_normalizes_unequal_tp_sum(monkeypatch):
    monkeypatch.setenv("BINANCE_TP1_SIZE_PCT", "0.5")
    monkeypatch.setenv("BINANCE_TP2_SIZE_PCT", "0.5")
    monkeypatch.setenv("BINANCE_TP3_SIZE_PCT", "0")
    monkeypatch.delenv("BINANCE_EXECUTION_ENABLED", raising=False)
    cfg = load_execution_config()
    s = cfg.tp1_size_pct + cfg.tp2_size_pct + cfg.tp3_size_pct
    assert abs(s - 1.0) < 0.02
