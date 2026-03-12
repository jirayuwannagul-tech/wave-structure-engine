from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PriceConfirmation:
    state: str
    price: float
    confirmation: float | None
    invalidation: float | None
    message: str


def evaluate_price_confirmation(
    price: float,
    confirmation: float | None,
    invalidation: float | None,
    bias: str,
) -> PriceConfirmation:
    if confirmation is None and invalidation is None:
        return PriceConfirmation(
            state="unknown",
            price=price,
            confirmation=confirmation,
            invalidation=invalidation,
            message="no confirmation levels",
        )

    if bias == "BULLISH":
        if invalidation is not None and price < invalidation:
            return PriceConfirmation(
                state="below_invalidation",
                price=price,
                confirmation=confirmation,
                invalidation=invalidation,
                message="price is below bullish invalidation",
            )

        if confirmation is not None and price > confirmation:
            return PriceConfirmation(
                state="confirmed_breakout",
                price=price,
                confirmation=confirmation,
                invalidation=invalidation,
                message="bullish breakout confirmed",
            )

        return PriceConfirmation(
            state="inside_range",
            price=price,
            confirmation=confirmation,
            invalidation=invalidation,
            message="price is between invalidation and confirmation",
        )

    if bias == "BEARISH":
        if invalidation is not None and price > invalidation:
            return PriceConfirmation(
                state="above_invalidation",
                price=price,
                confirmation=confirmation,
                invalidation=invalidation,
                message="price is above bearish invalidation",
            )

        if confirmation is not None and price < confirmation:
            return PriceConfirmation(
                state="confirmed_breakdown",
                price=price,
                confirmation=confirmation,
                invalidation=invalidation,
                message="bearish breakdown confirmed",
            )

        return PriceConfirmation(
            state="inside_range",
            price=price,
            confirmation=confirmation,
            invalidation=invalidation,
            message="price is between confirmation and invalidation",
        )

    return PriceConfirmation(
        state="unknown",
        price=price,
        confirmation=confirmation,
        invalidation=invalidation,
        message="bias unknown",
    )


if __name__ == "__main__":
    print(evaluate_price_confirmation(
        price=69597.46,
        confirmation=74050.0,
        invalidation=65618.49,
        bias="BULLISH",
    ))