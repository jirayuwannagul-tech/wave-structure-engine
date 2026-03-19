from __future__ import annotations

from dataclasses import dataclass

from analysis.wave_detector import ABCPattern, ImpulsePattern


@dataclass
class KeyLevels:
    structure_type: str
    support: float | None
    resistance: float | None
    invalidation: float | None
    confirmation: float | None
    wave_start: float | None
    wave_end: float | None
    b_level: float | None = None
    c_level: float | None = None


def _make_corrective_key_levels(
    structure_type: str,
    direction: str,
    start,
    middle,
    end,
) -> KeyLevels:
    direction = (direction or "").lower()
    low = min(float(middle.price), float(end.price))
    high = max(float(middle.price), float(end.price))

    if direction == "bullish":
        return KeyLevels(
            structure_type=structure_type,
            support=low,
            resistance=high,
            invalidation=low,
            confirmation=high,
            wave_start=start.price,
            wave_end=end.price,
            b_level=middle.price,
            c_level=end.price,
        )

    return KeyLevels(
        structure_type=structure_type,
        support=low,
        resistance=high,
        invalidation=high,
        confirmation=low,
        wave_start=start.price,
        wave_end=end.price,
        b_level=middle.price,
        c_level=end.price,
    )


def align_corrective_key_levels_to_bias(
    key_levels: KeyLevels | None,
    bias: str | None,
) -> KeyLevels | None:
    if key_levels is None:
        return None

    normalized_bias = (bias or "").upper()
    if normalized_bias not in {"BULLISH", "BEARISH"}:
        return key_levels

    anchors = [
        value
        for value in (
            key_levels.support,
            key_levels.resistance,
            key_levels.b_level,
            key_levels.c_level,
        )
        if value is not None
    ]
    if not anchors:
        return key_levels

    low = float(min(anchors))
    high = float(max(anchors))
    if normalized_bias == "BULLISH":
        return KeyLevels(
            structure_type=key_levels.structure_type,
            support=low,
            resistance=high,
            invalidation=low,
            confirmation=high,
            wave_start=key_levels.wave_start,
            wave_end=key_levels.wave_end,
            b_level=key_levels.b_level,
            c_level=key_levels.c_level,
        )

    return KeyLevels(
        structure_type=key_levels.structure_type,
        support=low,
        resistance=high,
        invalidation=high,
        confirmation=low,
        wave_start=key_levels.wave_start,
        wave_end=key_levels.wave_end,
        b_level=key_levels.b_level,
        c_level=key_levels.c_level,
    )


def extract_abc_key_levels(pattern: ABCPattern) -> KeyLevels:
    return _make_corrective_key_levels(
        structure_type="abc",
        direction=pattern.direction,
        start=pattern.a,
        middle=pattern.b,
        end=pattern.c,
    )


def extract_impulse_key_levels(pattern: ImpulsePattern) -> KeyLevels:
    direction = (pattern.direction or "").lower()

    if direction == "bullish":
        return KeyLevels(
            structure_type="impulse",
            support=pattern.p5.price,
            resistance=pattern.p6.price,
            invalidation=pattern.p1.price,
            confirmation=pattern.p6.price,
            wave_start=pattern.p1.price,
            wave_end=pattern.p6.price,
        )

    return KeyLevels(
        structure_type="impulse",
        support=pattern.p6.price,
        resistance=pattern.p5.price,
        invalidation=pattern.p1.price,
        confirmation=pattern.p6.price,
        wave_start=pattern.p1.price,
        wave_end=pattern.p6.price,
    )


def extract_flat_key_levels(pattern) -> KeyLevels:
    return _make_corrective_key_levels(
        structure_type=pattern.pattern_type,
        direction=pattern.direction,
        start=pattern.a,
        middle=pattern.b,
        end=pattern.c,
    )


def extract_wxy_key_levels(pattern) -> KeyLevels:
    return _make_corrective_key_levels(
        structure_type="wxy",
        direction=pattern.direction,
        start=pattern.w,
        middle=pattern.x,
        end=pattern.y,
    )


def extract_triangle_key_levels(pattern) -> KeyLevels:
    prices = [point.price for point in pattern.points]

    return KeyLevels(
        structure_type="triangle",
        support=min(prices),
        resistance=max(prices),
        invalidation=min(prices),
        confirmation=max(prices),
        wave_start=pattern.points[0].price,
        wave_end=pattern.points[-1].price,
    )


def extract_diagonal_key_levels(pattern) -> KeyLevels:
    points = [pattern.p1, pattern.p2, pattern.p3, pattern.p4, pattern.p5]
    prices = [point.price for point in points]
    direction = (pattern.direction or "").lower()

    if direction == "bullish":
        return KeyLevels(
            structure_type=pattern.pattern_type,
            support=min(prices),
            resistance=max(prices),
            invalidation=pattern.p1.price,
            confirmation=max(prices),
            wave_start=pattern.p1.price,
            wave_end=pattern.p5.price,
        )

    return KeyLevels(
        structure_type=pattern.pattern_type,
        support=min(prices),
        resistance=max(prices),
        invalidation=pattern.p1.price,
        confirmation=min(prices),
        wave_start=pattern.p1.price,
        wave_end=pattern.p5.price,
    )


def extract_pattern_key_levels(pattern_type: str, pattern) -> KeyLevels | None:
    pattern_type = (pattern_type or "").upper()

    if pattern is None:
        return None

    if pattern_type == "ABC_CORRECTION":
        return extract_abc_key_levels(pattern)

    if pattern_type == "IMPULSE":
        return extract_impulse_key_levels(pattern)

    if pattern_type in {"FLAT", "EXPANDED_FLAT", "RUNNING_FLAT"}:
        return extract_flat_key_levels(pattern)

    if pattern_type == "WXY":
        return extract_wxy_key_levels(pattern)

    if pattern_type in {
        "TRIANGLE",
        "CONTRACTING_TRIANGLE",
        "EXPANDING_TRIANGLE",
        "ASCENDING_BARRIER_TRIANGLE",
        "DESCENDING_BARRIER_TRIANGLE",
    }:
        return extract_triangle_key_levels(pattern)

    if pattern_type in {"ENDING_DIAGONAL", "LEADING_DIAGONAL"}:
        return extract_diagonal_key_levels(pattern)

    return None
