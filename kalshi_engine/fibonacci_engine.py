from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


FIB_LEVELS = [0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.272, 1.618, 2.0, 2.618]


@dataclass
class FibonacciMeasurement:
    start_price: float
    end_price: float
    direction: str
    levels: Dict[float, float]


def measure_retracement(start_price: float, end_price: float) -> FibonacciMeasurement:
    move = end_price - start_price
    direction = "up" if move >= 0 else "down"

    levels: Dict[float, float] = {}

    if direction == "up":
        for level in FIB_LEVELS:
            levels[level] = end_price - (abs(move) * level)
    else:
        for level in FIB_LEVELS:
            levels[level] = end_price + (abs(move) * level)

    return FibonacciMeasurement(
        start_price=start_price,
        end_price=end_price,
        direction=direction,
        levels=levels,
    )


def measure_extension(start_price: float, end_price: float, anchor_price: float) -> FibonacciMeasurement:
    move = end_price - start_price
    direction = "up" if move >= 0 else "down"

    levels: Dict[float, float] = {}

    if direction == "up":
        for level in FIB_LEVELS:
            levels[level] = anchor_price + (abs(move) * level)
    else:
        for level in FIB_LEVELS:
            levels[level] = anchor_price - (abs(move) * level)

    return FibonacciMeasurement(
        start_price=start_price,
        end_price=end_price,
        direction=direction,
        levels=levels,
    )


if __name__ == "__main__":
    retracement = measure_retracement(63030.0, 74050.0)
    extension = measure_extension(63030.0, 74050.0, 65618.49)

    print("RETRACEMENT")
    for k, v in retracement.levels.items():
        print(k, round(v, 2))

    print("\nEXTENSION")
    for k, v in extension.levels.items():
        print(k, round(v, 2))