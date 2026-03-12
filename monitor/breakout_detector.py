from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BreakoutEvent:
    state: str
    level: float | None
    price: float
    bias: str
    message: str


def detect_breakout(
    price: float,
    confirmation_level: float | None,
    bias: str,
) -> BreakoutEvent:
    if confirmation_level is None:
        return BreakoutEvent(
            state="no_level",
            level=None,
            price=price,
            bias=bias,
            message="no confirmation level",
        )

    if bias == "BULLISH":
        if price > confirmation_level:
            return BreakoutEvent(
                state="bullish_breakout",
                level=confirmation_level,
                price=price,
                bias=bias,
                message="price broke above confirmation level",
            )
        return BreakoutEvent(
            state="no_breakout",
            level=confirmation_level,
            price=price,
            bias=bias,
            message="price has not broken bullish confirmation",
        )

    if bias == "BEARISH":
        if price < confirmation_level:
            return BreakoutEvent(
                state="bearish_breakdown",
                level=confirmation_level,
                price=price,
                bias=bias,
                message="price broke below confirmation level",
            )
        return BreakoutEvent(
            state="no_breakout",
            level=confirmation_level,
            price=price,
            bias=bias,
            message="price has not broken bearish confirmation",
        )

    return BreakoutEvent(
        state="unknown",
        level=confirmation_level,
        price=price,
        bias=bias,
        message="unknown bias",
    )


if __name__ == "__main__":
    print(detect_breakout(
        price=69597.46,
        confirmation_level=74050.0,
        bias="BULLISH",
    ))