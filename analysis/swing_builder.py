from __future__ import annotations

from dataclasses import dataclass
from typing import List

from analysis.pivot_detector import Pivot


@dataclass
class SwingPoint:
    index: int
    price: float
    type: str
    timestamp: object


def build_swings(pivots: List[Pivot]) -> List[SwingPoint]:
    if not pivots:
        return []

    swings: List[SwingPoint] = []

    for pivot in pivots:
        current = SwingPoint(
            index=pivot.index,
            price=float(pivot.price),
            type=pivot.type,
            timestamp=pivot.timestamp,
        )

        if not swings:
            swings.append(current)
            continue

        last = swings[-1]

        if current.type != last.type:
            swings.append(current)
            continue

        if current.type == "H" and current.price >= last.price:
            swings[-1] = current
        elif current.type == "L" and current.price <= last.price:
            swings[-1] = current

    return swings


if __name__ == "__main__":
    import pandas as pd
    from analysis.pivot_detector import detect_pivots

    df = pd.read_csv("data/BTCUSDT_1d.csv")
    df["open_time"] = pd.to_datetime(df["open_time"])

    pivots = detect_pivots(df)
    swings = build_swings(pivots)

    for s in swings[-10:]:
        print(s)