from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from analysis.swing_builder import SwingPoint


@dataclass
class TrianglePattern:
    pattern_type: str
    direction: str
    points: List[SwingPoint]
    upper_slope: float
    lower_slope: float


def _slope(p1: SwingPoint, p2: SwingPoint) -> float:
    dx = p2.index - p1.index
    if dx == 0:
        return 0.0
    return (p2.price - p1.price) / dx


def detect_contracting_triangle(swings: List[SwingPoint]) -> Optional[TrianglePattern]:
    if len(swings) < 5:
        return None

    for i in range(len(swings) - 5, -1, -1):
        pts = swings[i : i + 5]
        types = [p.type for p in pts]

        valid_seq = (
            types == ["H", "L", "H", "L", "H"]
            or types == ["L", "H", "L", "H", "L"]
        )
        if not valid_seq:
            continue

        highs = [p for p in pts if p.type == "H"]
        lows = [p for p in pts if p.type == "L"]

        if len(highs) < 2 or len(lows) < 2:
            continue

        # triangle แบบหดตัว: high ต่ำลง, low สูงขึ้น
        highs_desc = all(highs[j].price > highs[j + 1].price for j in range(len(highs) - 1))
        lows_asc = all(lows[j].price < lows[j + 1].price for j in range(len(lows) - 1))

        if not (highs_desc and lows_asc):
            continue

        upper_slope = _slope(highs[0], highs[-1])
        lower_slope = _slope(lows[0], lows[-1])

        return TrianglePattern(
            pattern_type="contracting_triangle",
            direction="neutral",
            points=pts,
            upper_slope=upper_slope,
            lower_slope=lower_slope,
        )

    return None