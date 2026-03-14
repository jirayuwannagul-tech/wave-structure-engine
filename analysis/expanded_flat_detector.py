from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from analysis.swing_builder import SwingPoint


@dataclass
class ExpandedFlatPattern:
    pattern_type: str
    direction: str
    a: SwingPoint
    b: SwingPoint
    c: SwingPoint
    ab_length: float
    bc_length: float
    b_extension_ratio: float
    c_extension_ratio: float


def _safe_ratio(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return a / b


def detect_expanded_flat(swings: List[SwingPoint]) -> Optional[ExpandedFlatPattern]:
    if len(swings) < 3:
        return None

    for i in range(len(swings) - 3, -1, -1):
        a, b, c = swings[i : i + 3]

        # bullish expanded flat: L-H-L
        # เงื่อนไข:
        # - B ทำ high
        # - C ลงต่ำกว่า A (expanded)
        if [a.type, b.type, c.type] == ["L", "H", "L"]:
            ab = b.price - a.price
            bc = b.price - c.price

            if ab <= 0 or bc <= 0:
                continue

            # Expanded Flat: B must retrace ≥ 100% of A (bc/ab ≥ 1.00), C extends beyond A
            b_extension_ratio = _safe_ratio(bc, ab)
            c_extension_ratio = b_extension_ratio

            if b_extension_ratio >= 1.00 and c.price < a.price and c_extension_ratio > 1.0:
                return ExpandedFlatPattern(
                    pattern_type="expanded_flat",
                    direction="bullish",
                    a=a,
                    b=b,
                    c=c,
                    ab_length=ab,
                    bc_length=bc,
                    b_extension_ratio=b_extension_ratio,
                    c_extension_ratio=c_extension_ratio,
                )

        # bearish expanded flat: H-L-H
        # เงื่อนไข:
        # - B ทำ low
        # - C ขึ้นสูงกว่า A (expanded)
        if [a.type, b.type, c.type] == ["H", "L", "H"]:
            ab = a.price - b.price
            bc = c.price - b.price

            if ab <= 0 or bc <= 0:
                continue

            # Expanded Flat bearish: B must retrace ≥ 100% of A, C extends beyond A
            b_extension_ratio = _safe_ratio(bc, ab)
            c_extension_ratio = b_extension_ratio

            if b_extension_ratio >= 1.00 and c.price > a.price and c_extension_ratio > 1.0:
                return ExpandedFlatPattern(
                    pattern_type="expanded_flat",
                    direction="bearish",
                    a=a,
                    b=b,
                    c=c,
                    ab_length=ab,
                    bc_length=bc,
                    b_extension_ratio=b_extension_ratio,
                    c_extension_ratio=c_extension_ratio,
                )

    return None