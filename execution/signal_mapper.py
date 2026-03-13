from __future__ import annotations

from execution.models import ExecutionConfig, OrderIntent


def calculate_order_quantity(
    entry_price: float,
    stop_loss: float,
    risk_amount_usdt: float,
) -> float:
    stop_distance = abs(float(entry_price) - float(stop_loss))
    if stop_distance <= 0:
        raise ValueError("Stop distance must be positive.")
    quantity = float(risk_amount_usdt) / stop_distance
    return round(quantity, 6)


def build_order_intent_from_signal(
    signal_row,
    *,
    account_equity_usdt: float,
    config: ExecutionConfig,
) -> OrderIntent:
    side = (signal_row["side"] or "").upper()
    if side not in {"LONG", "SHORT"}:
        raise ValueError("Signal side must be LONG or SHORT.")

    if side == "LONG" and not config.allow_long:
        raise ValueError("LONG execution is disabled by config.")
    if side == "SHORT" and not config.allow_short:
        raise ValueError("SHORT execution is disabled by config.")

    entry_price = float(signal_row["entry_price"])
    stop_loss = float(signal_row["stop_loss"])
    if side == "LONG" and stop_loss >= entry_price:
        raise ValueError("LONG signal requires stop loss below entry.")
    if side == "SHORT" and stop_loss <= entry_price:
        raise ValueError("SHORT signal requires stop loss above entry.")

    risk_amount_usdt = round(float(account_equity_usdt) * float(config.risk_per_trade), 4)
    quantity = calculate_order_quantity(entry_price, stop_loss, risk_amount_usdt)

    return OrderIntent(
        symbol=signal_row["symbol"],
        timeframe=signal_row["timeframe"],
        side=side,
        entry_price=entry_price,
        stop_loss=stop_loss,
        tp1=signal_row["tp1"],
        tp2=signal_row["tp2"],
        tp3=signal_row["tp3"],
        risk_amount_usdt=risk_amount_usdt,
        quantity=quantity,
        source_signal_id=signal_row["id"],
    )
