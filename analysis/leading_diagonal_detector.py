from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from analysis.pivot_detector import Pivot


@dataclass
class LeadingDiagonalPattern:
    pattern_type: str
    direction: str
    p1: Pivot
    p2: Pivot
    p3: Pivot
    p4: Pivot
    p5: Pivot
    overlap_exists: bool


def detect_leading_diagonal(pivots: List[Pivot]) -> Optional[LeadingDiagonalPattern]:
    if len(pivots) < 5:
        return None

    for i in range(len(pivots) - 5, -1, -1):
        p1, p2, p3, p4, p5 = pivots[i : i + 5]
        seq = [p.type for p in [p1, p2, p3, p4, p5]]

        # bullish leading diagonal candidate
        if seq == ["L", "H", "L", "H", "L"]:
            overlap_exists = p4.price > p2.price or p5.price > p3.price

            if p2.price > p1.price and p3.price > p1.price:
                return LeadingDiagonalPattern(
                    pattern_type="leading_diagonal",
                    direction="bullish",
                    p1=p1,
                    p2=p2,
                    p3=p3,
                    p4=p4,
                    p5=p5,
                    overlap_exists=overlap_exists,
                )

        # bearish leading diagonal candidate
        if seq == ["H", "L", "H", "L", "H"]:
            overlap_exists = p4.price < p2.price or p5.price < p3.price

            if p2.price < p1.price and p3.price < p1.price:
                return LeadingDiagonalPattern(
                    pattern_type="leading_diagonal",
                    direction="bearish",
                    p1=p1,
                    p2=p2,
                    p3=p3,
                    p4=p4,
                    p5=p5,
                    overlap_exists=overlap_exists,
                )

    return None