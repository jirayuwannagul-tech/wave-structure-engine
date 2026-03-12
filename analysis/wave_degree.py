from __future__ import annotations

from dataclasses import dataclass
from typing import List

from analysis.swing_builder import SwingPoint


@dataclass
class DegreeSwing:
    index: int
    price: float
    type: str
    timestamp: object
    swing_size: float
    degree: str


def classify_wave_degrees(swings: List[SwingPoint]) -> List[DegreeSwing]:
    if len(swings) < 2:
        return []

    sizes = [abs(swings[i].price - swings[i - 1].price) for i in range(1, len(swings))]
    avg_size = sum(sizes) / len(sizes) if sizes else 0.0

    result: List[DegreeSwing] = []

    for i, swing in enumerate(swings):
        if i == 0:
            swing_size = 0.0
        else:
            swing_size = abs(swing.price - swings[i - 1].price)

        if avg_size == 0:
            degree = "unknown"
        elif swing_size < avg_size * 0.5:
            degree = "micro"
        elif swing_size < avg_size * 1.0:
            degree = "minor"
        elif swing_size < avg_size * 2.0:
            degree = "intermediate"
        else:
            degree = "major"

        result.append(
            DegreeSwing(
                index=swing.index,
                price=swing.price,
                type=swing.type,
                timestamp=swing.timestamp,
                swing_size=swing_size,
                degree=degree,
            )
        )

    return result


if __name__ == "__main__":
    import pandas as pd
    from analysis.pivot_detector import detect_pivots
    from analysis.swing_builder import build_swings

    df = pd.read_csv("data/BTCUSDT_1d.csv")
    df["open_time"] = pd.to_datetime(df["open_time"])

    pivots = detect_pivots(df)
    swings = build_swings(pivots)
    degree_swings = classify_wave_degrees(swings)

    for s in degree_swings[-10:]:
        print(s)