from execution.models import ExecutionConfig
from execution.signal_mapper import build_order_intent_from_signal


def test_build_order_intent_from_short_signal():
    signal_row = {
        "id": 4,
        "symbol": "BTCUSDT",
        "timeframe": "1D",
        "side": "SHORT",
        "entry_price": 63030.0,
        "stop_loss": 74050.0,
        "tp1": 52010.0,
        "tp2": 49012.56,
        "tp3": 45199.64,
    }
    config = ExecutionConfig(risk_per_trade=0.01, allow_short=True)

    intent = build_order_intent_from_signal(
        signal_row,
        account_equity_usdt=1000.0,
        config=config,
    )

    assert intent.symbol == "BTCUSDT"
    assert intent.side == "SHORT"
    assert intent.risk_amount_usdt == 10.0
    assert intent.quantity > 0
    assert intent.source_signal_id == 4
