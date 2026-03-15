from __future__ import annotations

from dataclasses import dataclass

from analysis.fibonacci_engine import measure_extension, measure_retracement
from analysis.key_levels import KeyLevels
from analysis.wave_position import WavePosition


@dataclass
class FutureProjection:
    expected_structure: str
    expected_direction: str
    target_1: float | None
    target_2: float | None
    target_3: float | None
    invalidation: float | None
    confirmation: float | None
    stop_loss: float | None
    message: str


CORRECTIVE_STRUCTURES = {
    "ABC_CORRECTION",
    "FLAT",
    "EXPANDED_FLAT",
    "RUNNING_FLAT",
    "WXY",
}
TREND_STRUCTURES = {
    "IMPULSE",
    "ENDING_DIAGONAL",
    "LEADING_DIAGONAL",
}


def project_next_wave(position: WavePosition, key_levels: KeyLevels) -> FutureProjection:
    if position.structure in CORRECTIVE_STRUCTURES and position.bias == "BULLISH":
        extension = measure_extension(
            key_levels.wave_end or 0.0,
            key_levels.confirmation or 0.0,
            key_levels.confirmation or 0.0,
        )
        # Phase 3: TP1 at 0.618x (easier hit, boosts WR), TP2 at 1.0x, TP3 at 1.272x
        t1 = extension.levels.get(0.618, key_levels.confirmation)
        t2 = extension.levels.get(1.0, key_levels.confirmation)
        t3 = extension.levels.get(1.272, key_levels.confirmation)

        return FutureProjection(
            expected_structure="NEW_BULLISH_IMPULSE",
            expected_direction="UP",
            target_1=t1,
            target_2=t2,
            target_3=t3,
            invalidation=key_levels.invalidation,
            confirmation=key_levels.confirmation,
            stop_loss=key_levels.invalidation,
            message="if price breaks above confirmation, bullish continuation becomes more likely",
        )

    if position.structure in CORRECTIVE_STRUCTURES and position.bias == "BEARISH":
        extension = measure_extension(
            key_levels.wave_end or 0.0,
            key_levels.confirmation or 0.0,
            key_levels.confirmation or 0.0,
        )
        # Phase 3: TP1 at 0.618x (easier hit, boosts WR), TP2 at 1.0x, TP3 at 1.272x
        t1 = extension.levels.get(0.618, key_levels.support)
        t2 = extension.levels.get(1.0, key_levels.support)
        t3 = extension.levels.get(1.272, key_levels.support)

        return FutureProjection(
            expected_structure="NEW_BEARISH_IMPULSE",
            expected_direction="DOWN",
            target_1=t1,
            target_2=t2,
            target_3=t3,
            invalidation=key_levels.invalidation,
            confirmation=key_levels.confirmation,
            stop_loss=key_levels.invalidation,
            message="if price breaks below confirmation, bearish continuation becomes more likely",
        )

    if position.structure in TREND_STRUCTURES and position.bias == "BULLISH":
        retracement = measure_retracement(
            key_levels.wave_start or 0.0,
            key_levels.wave_end or 0.0,
        )
        t1 = retracement.levels.get(0.382, key_levels.support)
        t2 = retracement.levels.get(0.618, key_levels.wave_start)
        t3 = retracement.levels.get(0.786, key_levels.wave_start)

        return FutureProjection(
            expected_structure="ABC_CORRECTION",
            expected_direction="DOWN",
            target_1=t1,
            target_2=t2,
            target_3=t3,
            invalidation=key_levels.invalidation,
            confirmation=key_levels.confirmation,
            stop_loss=key_levels.confirmation,
            message="after completed bullish impulse, corrective pullback is likely",
        )

    if position.structure in TREND_STRUCTURES and position.bias == "BEARISH":
        retracement = measure_retracement(
            key_levels.wave_start or 0.0,
            key_levels.wave_end or 0.0,
        )
        t1 = retracement.levels.get(0.382, key_levels.resistance)
        t2 = retracement.levels.get(0.618, key_levels.wave_start)
        t3 = retracement.levels.get(0.786, key_levels.wave_start)

        return FutureProjection(
            expected_structure="ABC_CORRECTION",
            expected_direction="UP",
            target_1=t1,
            target_2=t2,
            target_3=t3,
            invalidation=key_levels.invalidation,
            confirmation=key_levels.confirmation,
            stop_loss=key_levels.support,
            message="after completed bearish impulse, corrective rebound is likely",
        )

    if position.structure == "TRIANGLE":
        return FutureProjection(
            expected_structure="BREAKOUT",
            expected_direction="NEUTRAL",
            target_1=key_levels.resistance,
            target_2=key_levels.support,
            target_3=None,
            invalidation=key_levels.invalidation,
            confirmation=key_levels.confirmation,
            stop_loss=None,
            message="triangle usually resolves with a breakout from the range",
        )

    return FutureProjection(
        expected_structure="UNKNOWN",
        expected_direction="NEUTRAL",
        target_1=None,
        target_2=None,
        target_3=None,
        invalidation=None,
        confirmation=None,
        stop_loss=None,
        message="structure is currently ambiguous",
    )


if __name__ == "__main__":
    import pandas as pd
    from analysis.key_levels import extract_abc_key_levels
    from analysis.pivot_detector import detect_pivots
    from analysis.wave_detector import detect_latest_abc, detect_latest_impulse
    from analysis.wave_position import detect_wave_position

    df = pd.read_csv("data/BTCUSDT_1d.csv")
    df["open_time"] = pd.to_datetime(df["open_time"])

    pivots = detect_pivots(df)
    abc = detect_latest_abc(pivots)
    impulse = detect_latest_impulse(pivots)
    position = detect_wave_position(abc_pattern=abc, impulse_pattern=impulse)

    if abc is not None:
        key_levels = extract_abc_key_levels(abc)
        print(project_next_wave(position, key_levels))
