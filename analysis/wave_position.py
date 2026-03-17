from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from analysis.wave_detector import ABCPattern, ImpulsePattern

if TYPE_CHECKING:
    from analysis.inprogress_detector import InProgressWave

_CORRECTIVE_STRUCTURES = {
    "ABC_CORRECTION",
    "CORRECTION",
    "FLAT",
    "EXPANDED_FLAT",
    "RUNNING_FLAT",
    "WXY",
}
_TRIANGLE_STRUCTURES = {
    "TRIANGLE",
    "CONTRACTING_TRIANGLE",
    "EXPANDING_TRIANGLE",
    "ASCENDING_BARRIER_TRIANGLE",
    "DESCENDING_BARRIER_TRIANGLE",
}
_TREND_STRUCTURES = {
    "IMPULSE",
    "ENDING_DIAGONAL",
    "LEADING_DIAGONAL",
}
_GENERIC_STRUCTURES = {"UNKNOWN", "CORRECTION", "IMPULSE"}


@dataclass
class WavePosition:
    structure: str
    position: str     # e.g. IN_WAVE_3, IN_WAVE_4, WAVE_5_COMPLETE, WAVE_C_END
    bias: str
    confidence: str
    wave_number: str = ""         # current wave: "1"-"5" or "A","B","C"
    building_wave: bool = False   # True when actively forming a new wave


def describe_current_leg(position: WavePosition | None) -> str | None:
    """Return the wave number currently being formed or last completed."""
    if position is None:
        return None

    # If we know the specific wave number, use it directly
    if position.wave_number:
        return position.wave_number

    structure = (position.structure or "").upper()

    if structure in {"ABC_CORRECTION", "FLAT", "EXPANDED_FLAT", "RUNNING_FLAT"}:
        return "C"
    if structure == "WXY":
        return "Y"
    if structure in {
        "TRIANGLE", "CONTRACTING_TRIANGLE", "EXPANDING_TRIANGLE",
        "ASCENDING_BARRIER_TRIANGLE", "DESCENDING_BARRIER_TRIANGLE",
    }:
        return "E"
    if structure in {"IMPULSE", "ENDING_DIAGONAL", "LEADING_DIAGONAL"}:
        return "5"

    return None


def _build_abc_position(abc_pattern: ABCPattern) -> WavePosition:
    if abc_pattern.direction == "bullish":
        return WavePosition(
            structure="ABC_CORRECTION",
            position="WAVE_C_END",
            bias="BULLISH",
            confidence="medium",
        )
    return WavePosition(
        structure="ABC_CORRECTION",
        position="WAVE_C_END",
        bias="BEARISH",
        confidence="medium",
    )


def _build_impulse_position(impulse_pattern: ImpulsePattern) -> WavePosition:
    if impulse_pattern.direction == "bullish":
        return WavePosition(
            structure="IMPULSE",
            position="WAVE_5_COMPLETE",
            bias="BULLISH",
            confidence="medium",
        )
    return WavePosition(
        structure="IMPULSE",
        position="WAVE_5_COMPLETE",
        bias="BEARISH",
        confidence="medium",
    )


def _build_pattern_position(pattern_type: str, pattern) -> WavePosition:
    pattern_type = (pattern_type or "").upper()
    direction = (getattr(pattern, "direction", None) or "neutral").upper()

    if pattern_type == "ABC_CORRECTION":
        return _build_abc_position(pattern)

    if pattern_type == "IMPULSE":
        return _build_impulse_position(pattern)

    if pattern_type in {"FLAT", "EXPANDED_FLAT", "RUNNING_FLAT", "WXY"}:
        return WavePosition(
            structure=pattern_type,
            position="CORRECTION_COMPLETE",
            bias=direction,
            confidence="medium",
        )

    if pattern_type in {
        "TRIANGLE", "CONTRACTING_TRIANGLE", "EXPANDING_TRIANGLE",
        "ASCENDING_BARRIER_TRIANGLE", "DESCENDING_BARRIER_TRIANGLE",
    }:
        return WavePosition(
            structure=pattern_type,
            position="CONSOLIDATION_END",
            bias=direction,
            confidence="medium",
        )

    if pattern_type in {"ENDING_DIAGONAL", "LEADING_DIAGONAL"}:
        return WavePosition(
            structure=pattern_type,
            position="DIAGONAL_COMPLETE",
            bias=direction,
            confidence="medium",
        )

    return WavePosition(
        structure=pattern_type or "UNKNOWN",
        position="UNKNOWN",
        bias=direction,
        confidence="low",
    )


def _resolve_inprogress_structure(
    pattern_type: str | None,
    inprogress_structure: str | None,
) -> str:
    pattern_type = (pattern_type or "").upper()
    inprogress_structure = (inprogress_structure or "").upper()

    if not inprogress_structure:
        return pattern_type or "UNKNOWN"

    # Keep the richer parent structure whenever the in-progress detector only
    # knows the generic leg shape. This preserves pattern subtype context such
    # as EXPANDED_FLAT / RUNNING_FLAT / TRIANGLE while a sub-wave is building.
    if pattern_type and pattern_type not in _GENERIC_STRUCTURES and inprogress_structure in _GENERIC_STRUCTURES:
        return pattern_type

    if inprogress_structure == "CORRECTION":
        if pattern_type in _CORRECTIVE_STRUCTURES | _TRIANGLE_STRUCTURES:
            return pattern_type
        return inprogress_structure

    if inprogress_structure == "IMPULSE":
        if pattern_type in _TREND_STRUCTURES:
            return pattern_type
        return inprogress_structure

    return inprogress_structure


def detect_wave_position(
    pattern_type: str | None = None,
    pattern=None,
    abc_pattern: Optional[ABCPattern] = None,
    impulse_pattern: Optional[ImpulsePattern] = None,
    inprogress: Optional["InProgressWave"] = None,
) -> WavePosition:
    # Prefer in-progress wave: it gives the most current picture
    if inprogress is not None and inprogress.is_valid:
        bias = "BULLISH" if inprogress.direction == "bullish" else "BEARISH"
        conf = "high" if inprogress.completed_waves >= 3 else "medium"
        return WavePosition(
            structure=_resolve_inprogress_structure(pattern_type, inprogress.structure),
            position=f"IN_WAVE_{inprogress.wave_number}",
            bias=bias,
            confidence=conf,
            wave_number=inprogress.wave_number,
            building_wave=True,
        )

    if pattern is not None and pattern_type is not None:
        return _build_pattern_position(pattern_type, pattern)

    if impulse_pattern is not None:
        return _build_impulse_position(impulse_pattern)

    if abc_pattern is not None:
        return _build_abc_position(abc_pattern)

    return WavePosition(
        structure="UNKNOWN",
        position="UNKNOWN",
        bias="NEUTRAL",
        confidence="low",
    )


if __name__ == "__main__":
    import pandas as pd
    from analysis.pivot_detector import detect_pivots
    from analysis.wave_detector import detect_latest_abc, detect_latest_impulse

    df = pd.read_csv("data/BTCUSDT_1d.csv")
    df["open_time"] = pd.to_datetime(df["open_time"])

    pivots = detect_pivots(df)
    abc = detect_latest_abc(pivots)
    impulse = detect_latest_impulse(pivots)

    print(detect_wave_position(abc_pattern=abc, impulse_pattern=impulse))
