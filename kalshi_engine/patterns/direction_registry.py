from __future__ import annotations


def get_direction(pattern_direction: str | None) -> str:
    d = (pattern_direction or "").lower()

    if d in ("bullish", "up"):
        return "BULLISH"

    if d in ("bearish", "down"):
        return "BEARISH"

    return "NEUTRAL"


def is_bullish(direction: str) -> bool:
    return direction.upper() == "BULLISH"


def is_bearish(direction: str) -> bool:
    return direction.upper() == "BEARISH"