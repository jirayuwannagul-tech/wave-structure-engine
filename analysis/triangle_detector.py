from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from analysis.swing_builder import SwingPoint


@dataclass
class TrianglePattern:
    pattern_type: str
    direction: str
    points: List[SwingPoint]
    upper_slope: float
    lower_slope: float
    triangle_subtype: str = field(default="contracting")


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
            triangle_subtype="contracting",
        )

    return None


def detect_expanding_triangle(swings: List[SwingPoint]) -> Optional[TrianglePattern]:
    """Expanding triangle: each segment larger than previous, boundaries diverge.

    Upper boundary rises (upper_slope > 0), lower boundary falls (lower_slope < 0).
    Valid in Wave 4 or Wave B positions.
    """
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

        # Expanding: highs go HIGHER, lows go LOWER
        highs_asc = all(highs[j].price < highs[j + 1].price for j in range(len(highs) - 1))
        lows_desc = all(lows[j].price > lows[j + 1].price for j in range(len(lows) - 1))

        if not (highs_asc and lows_desc):
            continue

        # Each segment must be larger than the previous
        segment_lengths = [abs(pts[j + 1].price - pts[j].price) for j in range(len(pts) - 1)]
        all_expanding = all(
            segment_lengths[k] < segment_lengths[k + 1]
            for k in range(len(segment_lengths) - 1)
        )
        if not all_expanding:
            continue

        upper_slope = _slope(highs[0], highs[-1])
        lower_slope = _slope(lows[0], lows[-1])

        return TrianglePattern(
            pattern_type="expanding_triangle",
            direction="neutral",
            points=pts,
            upper_slope=upper_slope,
            lower_slope=lower_slope,
            triangle_subtype="expanding",
        )

    return None


_BARRIER_FLAT_TOL = 0.003  # 0.3% normalised slope = "flat boundary"


def detect_barrier_triangle(swings: List[SwingPoint]) -> Optional[TrianglePattern]:
    """Barrier (ascending or descending) triangle.

    Ascending barrier: upper boundary is flat, lower boundary converges upward.
    Descending barrier: lower boundary is flat, upper boundary converges downward.
    Valid in Wave 4 or Wave B positions.
    """
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

        avg_price = sum(p.price for p in pts) / len(pts)
        if avg_price == 0:
            continue

        upper_slope = _slope(highs[0], highs[-1])
        lower_slope = _slope(lows[0], lows[-1])

        upper_slope_pct = upper_slope / avg_price
        lower_slope_pct = lower_slope / avg_price

        upper_flat = abs(upper_slope_pct) < _BARRIER_FLAT_TOL
        lower_flat = abs(lower_slope_pct) < _BARRIER_FLAT_TOL

        # Ascending barrier: flat upper + lows rising toward it
        if upper_flat and lower_slope_pct > _BARRIER_FLAT_TOL:
            lows_asc = all(lows[j].price < lows[j + 1].price for j in range(len(lows) - 1))
            if lows_asc:
                return TrianglePattern(
                    pattern_type="ascending_barrier_triangle",
                    direction="neutral",
                    points=pts,
                    upper_slope=upper_slope,
                    lower_slope=lower_slope,
                    triangle_subtype="ascending_barrier",
                )

        # Descending barrier: flat lower + highs falling toward it
        if lower_flat and upper_slope_pct < -_BARRIER_FLAT_TOL:
            highs_desc = all(
                highs[j].price > highs[j + 1].price for j in range(len(highs) - 1)
            )
            if highs_desc:
                return TrianglePattern(
                    pattern_type="descending_barrier_triangle",
                    direction="neutral",
                    points=pts,
                    upper_slope=upper_slope,
                    lower_slope=lower_slope,
                    triangle_subtype="descending_barrier",
                )

    return None
