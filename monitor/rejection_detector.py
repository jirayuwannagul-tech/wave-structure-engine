from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RejectionEvent:
    state: str
    level: float | None
    price: float
    bias: str
    message: str


def detect_rejection(
    price: float,
    invalidation_level: float | None,
    bias: str,
    tolerance: float = 0.003,
) -> RejectionEvent:
    if invalidation_level is None:
        return RejectionEvent(
            state="no_level",
            level=None,
            price=price,
            bias=bias,
            message="no invalidation level",
        )

    distance_pct = abs(price - invalidation_level) / invalidation_level

    if bias == "BULLISH":
        if price > invalidation_level and distance_pct <= tolerance:
            return RejectionEvent(
                state="bullish_rejection",
                level=invalidation_level,
                price=price,
                bias=bias,
                message="price is holding above bullish invalidation",
            )
        return RejectionEvent(
            state="no_rejection",
            level=invalidation_level,
            price=price,
            bias=bias,
            message="no bullish rejection detected",
        )

    if bias == "BEARISH":
        if price < invalidation_level and distance_pct <= tolerance:
            return RejectionEvent(
                state="bearish_rejection",
                level=invalidation_level,
                price=price,
                bias=bias,
                message="price is holding below bearish invalidation",
            )
        return RejectionEvent(
            state="no_rejection",
            level=invalidation_level,
            price=price,
            bias=bias,
            message="no bearish rejection detected",
        )

    return RejectionEvent(
        state="unknown",
        level=invalidation_level,
        price=price,
        bias=bias,
        message="unknown bias",
    )


if __name__ == "__main__":
    result = detect_rejection(
        price=69597.46,
        invalidation_level=65618.49,
        bias="BULLISH",
    )
    print(result)