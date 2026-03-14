from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from analysis.pivot_detector import Pivot


@dataclass
class ABCPattern:
    a: Pivot
    b: Pivot
    c: Pivot
    direction: str
    ab_length: float
    bc_length: float
    bc_vs_ab_ratio: float


@dataclass
class ImpulsePattern:
    p1: Pivot
    p2: Pivot
    p3: Pivot
    p4: Pivot
    p5: Pivot
    p6: Pivot
    direction: str

    wave1_length: float
    wave2_length: float
    wave3_length: float
    wave4_length: float
    wave5_length: float

    wave2_retrace_ratio: float
    wave4_retrace_ratio: float
    wave3_vs_wave1_ratio: float
    wave5_vs_wave1_ratio: float

    rule_wave2_not_beyond_wave1_origin: bool
    rule_wave3_not_shortest: bool
    rule_wave4_no_overlap_wave1: bool
    is_valid: bool
    is_wave3_extended: bool = False   # W3 > 1.618 × W1 (extended wave)
    is_wave5_extended: bool = False   # W5 > W1 × 1.0 (extended wave 5)
    wave5_truncated: bool = False     # W5 < W3 AND W5 < W1 (truncation)
    extension_wave: str = ""          # "W3", "W5", or "" (which wave is extended)


def _safe_ratio(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return a / b


def detect_latest_abc(pivots: List[Pivot]) -> Optional[ABCPattern]:
    if len(pivots) < 3:
        return None

    for i in range(len(pivots) - 3, -1, -1):
        p1, p2, p3 = pivots[i : i + 3]

        if p1.type == "H" and p2.type == "L" and p3.type == "H":
            if p2.price < p1.price and p3.price < p1.price:
                ab = abs(p2.price - p1.price)
                bc = abs(p3.price - p2.price)
                return ABCPattern(
                    a=p1,
                    b=p2,
                    c=p3,
                    direction="bearish",
                    ab_length=ab,
                    bc_length=bc,
                    bc_vs_ab_ratio=_safe_ratio(bc, ab),
                )

        if p1.type == "L" and p2.type == "H" and p3.type == "L":
            if p2.price > p1.price and p3.price > p1.price:
                ab = abs(p2.price - p1.price)
                bc = abs(p3.price - p2.price)
                return ABCPattern(
                    a=p1,
                    b=p2,
                    c=p3,
                    direction="bullish",
                    ab_length=ab,
                    bc_length=bc,
                    bc_vs_ab_ratio=_safe_ratio(bc, ab),
                )

    return None


def _is_bullish_impulse_structure(
    p1: Pivot, p2: Pivot, p3: Pivot, p4: Pivot, p5: Pivot, p6: Pivot
) -> bool:
    return (
        p2.price > p1.price
        and p3.price < p2.price
        and p4.price > p3.price
        and p5.price < p4.price
        and p6.price > p5.price
        and p4.price > p2.price
        and p6.price > p4.price
    )


def _is_bearish_impulse_structure(
    p1: Pivot, p2: Pivot, p3: Pivot, p4: Pivot, p5: Pivot, p6: Pivot
) -> bool:
    return (
        p2.price < p1.price
        and p3.price > p2.price
        and p4.price < p3.price
        and p5.price > p4.price
        and p6.price < p5.price
        and p4.price < p2.price
        and p6.price < p4.price
    )


def _build_bullish_impulse(
    p1: Pivot, p2: Pivot, p3: Pivot, p4: Pivot, p5: Pivot, p6: Pivot
) -> ImpulsePattern:
    wave1 = p2.price - p1.price
    wave2 = p2.price - p3.price
    wave3 = p4.price - p3.price
    wave4 = p4.price - p5.price
    wave5 = p6.price - p5.price

    rule1 = p3.price > p1.price
    rule2 = wave3 > 0 and wave3 > min(wave1, wave5)
    rule3 = p5.price > p2.price

    structure_ok = _is_bullish_impulse_structure(p1, p2, p3, p4, p5, p6)
    retracement_ok = (
        wave1 > 0
        and wave2 > 0
        and wave3 > 0
        and wave4 > 0
        and wave5 > 0
        and wave2 < wave1
        and wave4 < wave3
    )

    is_valid = structure_ok and retracement_ok and rule1 and rule2 and rule3

    is_wave3_extended = wave3 > wave1 * 1.618
    is_wave5_extended = wave5 > wave1 * 1.0 and not is_wave3_extended
    wave5_truncated = wave5 < wave3 and wave5 < wave1
    extension_wave = "W3" if is_wave3_extended else ("W5" if is_wave5_extended else "")

    return ImpulsePattern(
        p1=p1,
        p2=p2,
        p3=p3,
        p4=p4,
        p5=p5,
        p6=p6,
        direction="bullish",
        wave1_length=wave1,
        wave2_length=wave2,
        wave3_length=wave3,
        wave4_length=wave4,
        wave5_length=wave5,
        wave2_retrace_ratio=_safe_ratio(wave2, wave1),
        wave4_retrace_ratio=_safe_ratio(wave4, wave3),
        wave3_vs_wave1_ratio=_safe_ratio(wave3, wave1),
        wave5_vs_wave1_ratio=_safe_ratio(wave5, wave1),
        rule_wave2_not_beyond_wave1_origin=rule1,
        rule_wave3_not_shortest=rule2,
        rule_wave4_no_overlap_wave1=rule3,
        is_valid=is_valid,
        is_wave3_extended=is_wave3_extended,
        is_wave5_extended=is_wave5_extended,
        wave5_truncated=wave5_truncated,
        extension_wave=extension_wave,
    )


def _build_bearish_impulse(
    p1: Pivot, p2: Pivot, p3: Pivot, p4: Pivot, p5: Pivot, p6: Pivot
) -> ImpulsePattern:
    wave1 = p1.price - p2.price
    wave2 = p3.price - p2.price
    wave3 = p3.price - p4.price
    wave4 = p5.price - p4.price
    wave5 = p5.price - p6.price

    rule1 = p3.price < p1.price
    rule2 = wave3 > 0 and wave3 > min(wave1, wave5)
    rule3 = p5.price < p2.price

    wave5_completion_ok = p6.price < p4.price or wave5 >= wave1
    structure_ok = _is_bearish_impulse_structure(p1, p2, p3, p4, p5, p6) or (
        p2.price < p1.price
        and p3.price > p2.price
        and p4.price < p3.price
        and p5.price > p4.price
        and p6.price < p5.price
        and p4.price < p2.price
        and wave5_completion_ok
    )
    retracement_ok = (
        wave1 > 0
        and wave2 > 0
        and wave3 > 0
        and wave4 > 0
        and wave5 > 0
        and wave2 < wave1
        and wave4 < wave3
    )

    is_valid = structure_ok and retracement_ok and rule1 and rule2 and rule3

    is_wave3_extended = wave3 > wave1 * 1.618
    is_wave5_extended = wave5 > wave1 * 1.0 and not is_wave3_extended
    wave5_truncated = wave5 < wave3 and wave5 < wave1
    extension_wave = "W3" if is_wave3_extended else ("W5" if is_wave5_extended else "")

    return ImpulsePattern(
        p1=p1,
        p2=p2,
        p3=p3,
        p4=p4,
        p5=p5,
        p6=p6,
        direction="bearish",
        wave1_length=wave1,
        wave2_length=wave2,
        wave3_length=wave3,
        wave4_length=wave4,
        wave5_length=wave5,
        wave2_retrace_ratio=_safe_ratio(wave2, wave1),
        wave4_retrace_ratio=_safe_ratio(wave4, wave3),
        wave3_vs_wave1_ratio=_safe_ratio(wave3, wave1),
        wave5_vs_wave1_ratio=_safe_ratio(wave5, wave1),
        rule_wave2_not_beyond_wave1_origin=rule1,
        rule_wave3_not_shortest=rule2,
        rule_wave4_no_overlap_wave1=rule3,
        is_valid=is_valid,
        is_wave3_extended=is_wave3_extended,
        is_wave5_extended=is_wave5_extended,
        wave5_truncated=wave5_truncated,
        extension_wave=extension_wave,
    )


def detect_latest_impulse(pivots: List[Pivot]) -> Optional[ImpulsePattern]:
    if len(pivots) < 6:
        return None

    for i in range(len(pivots) - 6, -1, -1):
        p1, p2, p3, p4, p5, p6 = pivots[i : i + 6]
        types = [p.type for p in [p1, p2, p3, p4, p5, p6]]

        if types == ["L", "H", "L", "H", "L", "H"]:
            pattern = _build_bullish_impulse(p1, p2, p3, p4, p5, p6)
            if pattern.is_valid:
                return pattern

        if types == ["H", "L", "H", "L", "H", "L"]:
            pattern = _build_bearish_impulse(p1, p2, p3, p4, p5, p6)
            if pattern.is_valid:
                return pattern

    return None


if __name__ == "__main__":
    import pandas as pd
    from analysis.pivot_detector import detect_pivots

    df = pd.read_csv("data/BTCUSDT_1d.csv")
    df["open_time"] = pd.to_datetime(df["open_time"])

    pivots = detect_pivots(df)

    print("=== LAST 6 PIVOTS ===")
    for p in pivots[-6:]:
        print(p)

    print("\n=== IMPULSE ===")
    print(detect_latest_impulse(pivots))

    print("\n=== ABC ===")
    print(detect_latest_abc(pivots))
