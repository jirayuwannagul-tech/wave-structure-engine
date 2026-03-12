from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from analysis.swing_builder import SwingPoint


@dataclass
class CorrectivePattern:
    pattern_type: str
    direction: str
    a: SwingPoint
    b: SwingPoint
    c: SwingPoint
    ab_length: float
    bc_length: float
    bc_vs_ab_ratio: float


def _safe_ratio(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return a / b


def detect_latest_correction(swings: List[SwingPoint]) -> Optional[CorrectivePattern]:
    if len(swings) < 3:
        return None

    for i in range(len(swings) - 3, -1, -1):
        a, b, c = swings[i : i + 3]

        if [a.type, b.type, c.type] == ["L", "H", "L"]:
            ab = b.price - a.price
            bc = b.price - c.price

            if ab > 0 and bc > 0 and c.price > a.price:
                ratio = _safe_ratio(bc, ab)
                pattern_type = "flat" if ratio < 0.5 else "zigzag"

                return CorrectivePattern(
                    pattern_type=pattern_type,
                    direction="bullish",
                    a=a,
                    b=b,
                    c=c,
                    ab_length=ab,
                    bc_length=bc,
                    bc_vs_ab_ratio=ratio,
                )

        if [a.type, b.type, c.type] == ["H", "L", "H"]:
            ab = a.price - b.price
            bc = c.price - b.price

            if ab > 0 and bc > 0 and c.price < a.price:
                ratio = _safe_ratio(bc, ab)
                pattern_type = "flat" if ratio < 0.5 else "zigzag"

                return CorrectivePattern(
                    pattern_type=pattern_type,
                    direction="bearish",
                    a=a,
                    b=b,
                    c=c,
                    ab_length=ab,
                    bc_length=bc,
                    bc_vs_ab_ratio=ratio,
                )

    return None


def detect_zigzag(swings: List[SwingPoint]) -> Optional[CorrectivePattern]:
    pattern = detect_latest_correction(swings)
    if pattern is None:
        return None
    if pattern.pattern_type != "zigzag":
        return None
    return pattern


if __name__ == "__main__":
    import pandas as pd
    from analysis.pivot_detector import detect_pivots
    from analysis.swing_builder import build_swings

    df = pd.read_csv("data/BTCUSDT_1d.csv")
    df["open_time"] = pd.to_datetime(df["open_time"])

    pivots = detect_pivots(df)
    swings = build_swings(pivots)

    print(detect_latest_correction(swings))
    print(detect_zigzag(swings))