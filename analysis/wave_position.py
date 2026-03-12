from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from analysis.wave_detector import ABCPattern, ImpulsePattern


@dataclass
class WavePosition:
    structure: str
    position: str
    bias: str
    confidence: str


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

    if pattern_type == "TRIANGLE":
        return WavePosition(
            structure="TRIANGLE",
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


def detect_wave_position(
    pattern_type: str | None = None,
    pattern=None,
    abc_pattern: Optional[ABCPattern] = None,
    impulse_pattern: Optional[ImpulsePattern] = None,
) -> WavePosition:
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
