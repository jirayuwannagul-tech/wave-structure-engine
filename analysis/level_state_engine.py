from __future__ import annotations


def detect_level_state(
    current_price: float,
    level_price: float,
    level_type: str,
    tolerance: float = 0.002,
) -> str | None:
    if level_price <= 0:
        return None

    diff = abs(current_price - level_price) / level_price

    if level_type == "support":
        if current_price < level_price:
            return "BREAK"
        if diff <= tolerance:
            return "NEAR"
        return None

    if level_type == "resistance":
        if current_price > level_price:
            return "BREAK"
        if diff <= tolerance:
            return "NEAR"
        return None

    return None