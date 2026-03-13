from __future__ import annotations


def calculate_rr(
    side: str | None,
    entry_price: float | None,
    stop_loss: float | None,
    target_price: float | None,
) -> float | None:
    if side is None or entry_price is None or stop_loss is None or target_price is None:
        return None

    side = side.upper()
    if side == "BULLISH":
        side = "LONG"
    elif side == "BEARISH":
        side = "SHORT"
    entry = float(entry_price)
    stop = float(stop_loss)
    target = float(target_price)

    if side == "LONG":
        risk = entry - stop
        reward = target - entry
    elif side == "SHORT":
        risk = stop - entry
        reward = entry - target
    else:
        return None

    if risk <= 0 or reward <= 0:
        return None

    return round(reward / risk, 3)


def calculate_rr_levels(
    side: str | None,
    entry_price: float | None,
    stop_loss: float | None,
    tp1: float | None,
    tp2: float | None,
    tp3: float | None,
) -> dict[str, float | None]:
    return {
        "rr_tp1": calculate_rr(side, entry_price, stop_loss, tp1),
        "rr_tp2": calculate_rr(side, entry_price, stop_loss, tp2),
        "rr_tp3": calculate_rr(side, entry_price, stop_loss, tp3),
    }
