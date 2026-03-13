from execution.execution_engine import ExecutionEngine
from execution.models import ExecutionConfig


def test_execution_engine_preview_signal():
    signal_row = {
        "id": 7,
        "symbol": "BTCUSDT",
        "timeframe": "4H",
        "side": "LONG",
        "entry_price": 70800.0,
        "stop_loss": 69205.91,
        "tp1": 72394.09,
        "tp2": 72827.6825,
        "tp3": 73379.2376,
    }
    engine = ExecutionEngine(
        config=ExecutionConfig(
            enabled=False,
            live_order_enabled=False,
            risk_per_trade=0.01,
            allow_long=True,
        )
    )

    preview = engine.preview_signal(signal_row, account_equity_usdt=1000.0)

    assert preview["mode"] == "preview"
    assert preview["intent"]["side"] == "LONG"
    assert preview["intent"]["source_signal_id"] == 7
    assert preview["entry_order"]["side"] == "BUY"
    assert preview["protection"]["tp1"] == 72394.09
    assert preview["exit_plan"] == [
        {"label": "TP1", "target_price": 72394.09, "size_pct": 0.4, "quantity": 0.002509},
        {"label": "TP2", "target_price": 72827.6825, "size_pct": 0.3, "quantity": 0.001882},
        {"label": "TP3", "target_price": 73379.2376, "size_pct": 0.3, "quantity": 0.001882},
    ]
