from __future__ import annotations

from dataclasses import dataclass, field
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
    w1_length: float = 0.0
    w2_length: float = 0.0
    w3_length: float = 0.0
    w4_length: float = 0.0
    is_contracting: bool = False  # True if each sub-wave is shorter than the one 2 ahead
    w3_vs_w1_ratio: float = 0.0   # for Fib scoring
    w4_vs_w2_ratio: float = 0.0   # W4 retracement relative to W2


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
                w1 = abs(p2.price - p1.price)
                w2 = abs(p3.price - p2.price)
                w3 = abs(p4.price - p3.price)
                w4 = abs(p5.price - p4.price)
                is_contracting = (w1 > w3) and (w2 > w4)
                w3_vs_w1_ratio = w3 / w1 if w1 > 0 else 0.0
                w4_vs_w2_ratio = w4 / w2 if w2 > 0 else 0.0
                return LeadingDiagonalPattern(
                    pattern_type="leading_diagonal",
                    direction="bullish",
                    p1=p1,
                    p2=p2,
                    p3=p3,
                    p4=p4,
                    p5=p5,
                    overlap_exists=overlap_exists,
                    w1_length=w1,
                    w2_length=w2,
                    w3_length=w3,
                    w4_length=w4,
                    is_contracting=is_contracting,
                    w3_vs_w1_ratio=w3_vs_w1_ratio,
                    w4_vs_w2_ratio=w4_vs_w2_ratio,
                )

        # bearish leading diagonal candidate
        if seq == ["H", "L", "H", "L", "H"]:
            overlap_exists = p4.price < p2.price or p5.price < p3.price

            if p2.price < p1.price and p3.price < p1.price:
                w1 = abs(p2.price - p1.price)
                w2 = abs(p3.price - p2.price)
                w3 = abs(p4.price - p3.price)
                w4 = abs(p5.price - p4.price)
                is_contracting = (w1 > w3) and (w2 > w4)
                w3_vs_w1_ratio = w3 / w1 if w1 > 0 else 0.0
                w4_vs_w2_ratio = w4 / w2 if w2 > 0 else 0.0
                return LeadingDiagonalPattern(
                    pattern_type="leading_diagonal",
                    direction="bearish",
                    p1=p1,
                    p2=p2,
                    p3=p3,
                    p4=p4,
                    p5=p5,
                    overlap_exists=overlap_exists,
                    w1_length=w1,
                    w2_length=w2,
                    w3_length=w3,
                    w4_length=w4,
                    is_contracting=is_contracting,
                    w3_vs_w1_ratio=w3_vs_w1_ratio,
                    w4_vs_w2_ratio=w4_vs_w2_ratio,
                )

    return None
