from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from analysis.swing_builder import SwingPoint


@dataclass
class RunningFlatPattern:
    pattern_type: str
    direction: str
    a: SwingPoint
    b: SwingPoint
    c: SwingPoint
    ab_length: float
    bc_length: float
    b_vs_a_ratio: float
    c_vs_a_ratio: float


def _safe_ratio(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return a / b


def detect_running_flat(swings: List[SwingPoint]) -> Optional[RunningFlatPattern]:
    if len(swings) < 3:
        return None

    for i in range(len(swings) - 3, -1, -1):
        a, b, c = swings[i : i + 3]

        # bullish running flat: L-H-L
        # C ไม่ลงต่ำกว่า A
        if [a.type, b.type, c.type] == ["L", "H", "L"]:
            ab = b.price - a.price
            bc = b.price - c.price

            if ab <= 0 or bc <= 0:
                continue

            # Running Flat: C < B (bc/ab < 1.0), C fails to reach A origin (c.price > a.price)
            b_vs_a_ratio = _safe_ratio(bc, ab)
            c_vs_a_ratio = b_vs_a_ratio

            if c.price > a.price and 0.0 < c_vs_a_ratio < 1.0:
                return RunningFlatPattern(
                    pattern_type="running_flat",
                    direction="bullish",
                    a=a,
                    b=b,
                    c=c,
                    ab_length=ab,
                    bc_length=bc,
                    b_vs_a_ratio=b_vs_a_ratio,
                    c_vs_a_ratio=c_vs_a_ratio,
                )

        # bearish running flat: H-L-H
        # C ไม่ขึ้นสูงกว่า A
        if [a.type, b.type, c.type] == ["H", "L", "H"]:
            ab = a.price - b.price
            bc = c.price - b.price

            if ab <= 0 or bc <= 0:
                continue

            # Running Flat bearish: C < B (bc/ab < 1.0), C fails to reach A origin
            b_vs_a_ratio = _safe_ratio(bc, ab)
            c_vs_a_ratio = b_vs_a_ratio

            if c.price < a.price and 0.0 < c_vs_a_ratio < 1.0:
                return RunningFlatPattern(
                    pattern_type="running_flat",
                    direction="bearish",
                    a=a,
                    b=b,
                    c=c,
                    ab_length=ab,
                    bc_length=bc,
                    b_vs_a_ratio=b_vs_a_ratio,
                    c_vs_a_ratio=c_vs_a_ratio,
                )

    return None