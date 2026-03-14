from __future__ import annotations

from dataclasses import asdict, dataclass

from analysis.inprogress_detector import InProgressWave
from analysis.pivot_detector import Pivot
from analysis.wave_detector import detect_latest_impulse


@dataclass
class WaveSequenceLeg:
    label: str
    structure: str
    direction: str
    start_index: int
    end_index: int
    start_price: float
    end_price: float
    start_time: object
    end_time: object


@dataclass
class WaveSequencePattern:
    structure: str
    direction: str
    start_index: int
    end_index: int
    labels: list[str]


def _serialize_leg(leg: WaveSequenceLeg | None) -> dict | None:
    if leg is None:
        return None
    payload = asdict(leg)
    payload["start_time"] = str(leg.start_time)
    payload["end_time"] = str(leg.end_time)
    return payload


def _match_impulse(window: list[Pivot]) -> tuple[str, list[WaveSequenceLeg], WaveSequencePattern] | None:
    if len(window) < 6:
        return None

    pattern = detect_latest_impulse(window[:6])
    if pattern is None:
        return None

    pivots = window[:6]
    labels = ["1", "2", "3", "4", "5"]
    legs: list[WaveSequenceLeg] = []
    for label, start, end in zip(labels, pivots, pivots[1:]):
        direction = "bullish" if end.price > start.price else "bearish"
        legs.append(
            WaveSequenceLeg(
                label=label,
                structure="IMPULSE",
                direction=direction,
                start_index=start.index,
                end_index=end.index,
                start_price=start.price,
                end_price=end.price,
                start_time=start.timestamp,
                end_time=end.timestamp,
            )
        )

    return (
        pattern.direction,
        legs,
        WaveSequencePattern(
            structure="IMPULSE",
            direction=pattern.direction,
            start_index=pivots[0].index,
            end_index=pivots[-1].index,
            labels=labels,
        ),
    )


def _match_anchored_abc(window: list[Pivot]) -> tuple[str, list[WaveSequenceLeg], WaveSequencePattern] | None:
    if len(window) < 4:
        return None

    p0, p1, p2, p3 = window[:4]
    types = [p.type for p in (p0, p1, p2, p3)]

    if types == ["H", "L", "H", "L"]:
        wave_a = p0.price - p1.price
        wave_b = p2.price - p1.price
        wave_c = p2.price - p3.price
        if (
            wave_a > 0
            and wave_b > 0
            and wave_c > 0
            and p2.price < p0.price
            and p3.price < p2.price
        ):
            legs = [
                WaveSequenceLeg("A", "ABC_CORRECTION", "bearish", p0.index, p1.index, p0.price, p1.price, p0.timestamp, p1.timestamp),
                WaveSequenceLeg("B", "ABC_CORRECTION", "bullish", p1.index, p2.index, p1.price, p2.price, p1.timestamp, p2.timestamp),
                WaveSequenceLeg("C", "ABC_CORRECTION", "bearish", p2.index, p3.index, p2.price, p3.price, p2.timestamp, p3.timestamp),
            ]
            return (
                "bearish",
                legs,
                WaveSequencePattern(
                    structure="ABC_CORRECTION",
                    direction="bearish",
                    start_index=p0.index,
                    end_index=p3.index,
                    labels=["A", "B", "C"],
                ),
            )

    if types == ["L", "H", "L", "H"]:
        wave_a = p1.price - p0.price
        wave_b = p1.price - p2.price
        wave_c = p3.price - p2.price
        if (
            wave_a > 0
            and wave_b > 0
            and wave_c > 0
            and p2.price > p0.price
            and p3.price > p2.price
        ):
            legs = [
                WaveSequenceLeg("A", "ABC_CORRECTION", "bullish", p0.index, p1.index, p0.price, p1.price, p0.timestamp, p1.timestamp),
                WaveSequenceLeg("B", "ABC_CORRECTION", "bearish", p1.index, p2.index, p1.price, p2.price, p1.timestamp, p2.timestamp),
                WaveSequenceLeg("C", "ABC_CORRECTION", "bullish", p2.index, p3.index, p2.price, p3.price, p2.timestamp, p3.timestamp),
            ]
            return (
                "bullish",
                legs,
                WaveSequencePattern(
                    structure="ABC_CORRECTION",
                    direction="bullish",
                    start_index=p0.index,
                    end_index=p3.index,
                    labels=["A", "B", "C"],
                ),
            )

    return None


def _current_leg_from_inprogress(inprogress: InProgressWave | None) -> dict | None:
    if inprogress is None or not inprogress.is_valid:
        return None

    return {
        "label": inprogress.wave_number,
        "structure": inprogress.structure,
        "direction": inprogress.current_wave_direction,
        "completed_waves": inprogress.completed_waves,
        "start_index": inprogress.last_pivot.index,
        "start_price": inprogress.current_wave_start,
        "start_time": str(inprogress.last_pivot.timestamp),
        "invalidation": inprogress.invalidation,
        "confidence": inprogress.confidence,
        "position": f"IN_WAVE_{inprogress.wave_number}",
        "building": True,
    }


def build_wave_sequence(
    pivots: list[Pivot],
    inprogress: InProgressWave | None = None,
) -> dict:
    ordered_pivots = sorted(pivots, key=lambda pivot: (pivot.index, pivot.timestamp))
    completed_legs: list[WaveSequenceLeg] = []
    patterns: list[WaveSequencePattern] = []

    cursor = 0
    while cursor < len(ordered_pivots):
        remaining = ordered_pivots[cursor:]
        impulse_match = _match_impulse(remaining)
        if impulse_match is not None:
            _, legs, pattern = impulse_match
            completed_legs.extend(legs)
            patterns.append(pattern)
            cursor += 5
            continue

        abc_match = _match_anchored_abc(remaining)
        if abc_match is not None:
            _, legs, pattern = abc_match
            completed_legs.extend(legs)
            patterns.append(pattern)
            cursor += 3
            continue

        cursor += 1

    current_leg = _current_leg_from_inprogress(inprogress)
    last_completed_leg = completed_legs[-1] if completed_legs else None

    return {
        "completed_legs": [_serialize_leg(leg) for leg in completed_legs],
        "patterns": [asdict(pattern) for pattern in patterns],
        "current_leg": current_leg,
        "last_completed_leg": _serialize_leg(last_completed_leg),
        "pattern_count": len(patterns),
    }
