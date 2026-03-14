from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from analysis.swing_builder import SwingPoint


@dataclass
class FlatPattern:
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


def detect_flat(swings: List[SwingPoint]) -> Optional[FlatPattern]:
    if len(swings) < 3:
        return None

    for i in range(len(swings) - 3, -1, -1):
        a, b, c = swings[i : i + 3]

        # bullish flat: L-H-L
        if [a.type, b.type, c.type] == ["L", "H", "L"]:
            ab = b.price - a.price
            bc = b.price - c.price

            if ab <= 0 or bc <= 0:
                continue

            # Regular Flat: B retraces ≥ 90% of A (bc/ab ≥ 0.90), C stays ≥ A origin
            b_vs_a_ratio = _safe_ratio(bc, ab)
            c_vs_a_ratio = b_vs_a_ratio

            if b_vs_a_ratio >= 0.90 and c.price >= a.price and c_vs_a_ratio <= 1.05:
                return FlatPattern(
                    pattern_type="flat",
                    direction="bullish",
                    a=a,
                    b=b,
                    c=c,
                    ab_length=ab,
                    bc_length=bc,
                    b_vs_a_ratio=b_vs_a_ratio,
                    c_vs_a_ratio=c_vs_a_ratio,
                )

        # bearish flat: H-L-H
        if [a.type, b.type, c.type] == ["H", "L", "H"]:
            ab = a.price - b.price
            bc = c.price - b.price

            if ab <= 0 or bc <= 0:
                continue

            # Regular Flat bearish: B retraces ≥ 90% of A, C stays ≤ A origin
            b_vs_a_ratio = _safe_ratio(bc, ab)
            c_vs_a_ratio = b_vs_a_ratio

            if b_vs_a_ratio >= 0.90 and c.price <= a.price and c_vs_a_ratio <= 1.05:
                return FlatPattern(
                    pattern_type="flat",
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