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


def _compute_tighter_sl(
    bias: str,
    structural_sl: float,
    entry_price: float,
    recent_pivots: list,
    atr: float = 0.0,
) -> float:
    """Return tighter SL from most recent swing, bounded by structural invalidation."""
    buffer = atr * 0.3 if atr > 0 else 0.0
    if bias == "BULLISH":
        # Find the highest recent swing LOW below entry
        candidates = [p.price for p in (recent_pivots or [])
                      if getattr(p, "type", "") == "L" and p.price < entry_price]
        if not candidates:
            return structural_sl
        recent_low = max(candidates)
        candidate_sl = recent_low - buffer
        # Must be tighter (higher) than structural SL and below entry
        return max(candidate_sl, structural_sl) if candidate_sl < entry_price else structural_sl
    elif bias == "BEARISH":
        # Find the lowest recent swing HIGH above entry
        candidates = [p.price for p in (recent_pivots or [])
                      if getattr(p, "type", "") == "H" and p.price > entry_price]
        if not candidates:
            return structural_sl
        recent_high = min(candidates)
        candidate_sl = recent_high + buffer
        # Must be tighter (lower) than structural SL and above entry
        return min(candidate_sl, structural_sl) if candidate_sl > entry_price else structural_sl
    return structural_sl


def project_next_wave(
    position: WavePosition,
    key_levels: KeyLevels,
    recent_pivots=None,
    atr: float = 0.0,
) -> FutureProjection:
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

        entry_ref = key_levels.confirmation or key_levels.support or key_levels.resistance
        if entry_ref and recent_pivots:
            stop_loss = _compute_tighter_sl(
                bias="BULLISH",
                structural_sl=float(key_levels.invalidation),
                entry_price=float(entry_ref),
                recent_pivots=recent_pivots,
                atr=atr,
            )
        else:
            stop_loss = float(key_levels.invalidation) if key_levels.invalidation else 0.0

        return FutureProjection(
            expected_structure="NEW_BULLISH_IMPULSE",
            expected_direction="UP",
            target_1=t1,
            target_2=t2,
            target_3=t3,
            invalidation=key_levels.invalidation,
            confirmation=key_levels.confirmation,
            stop_loss=stop_loss,
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

        entry_ref = key_levels.confirmation or key_levels.support or key_levels.resistance
        if entry_ref and recent_pivots:
            stop_loss = _compute_tighter_sl(
                bias="BEARISH",
                structural_sl=float(key_levels.invalidation),
                entry_price=float(entry_ref),
                recent_pivots=recent_pivots,
                atr=atr,
            )
        else:
            stop_loss = float(key_levels.invalidation) if key_levels.invalidation else 0.0

        return FutureProjection(
            expected_structure="NEW_BEARISH_IMPULSE",
            expected_direction="DOWN",
            target_1=t1,
            target_2=t2,
            target_3=t3,
            invalidation=key_levels.invalidation,
            confirmation=key_levels.confirmation,
            stop_loss=stop_loss,
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

        entry_ref = key_levels.confirmation or key_levels.support or key_levels.resistance
        if entry_ref and recent_pivots:
            stop_loss = _compute_tighter_sl(
                bias="BULLISH",
                structural_sl=float(key_levels.invalidation),
                entry_price=float(entry_ref),
                recent_pivots=recent_pivots,
                atr=atr,
            )
        else:
            stop_loss = key_levels.confirmation

        return FutureProjection(
            expected_structure="ABC_CORRECTION",
            expected_direction="DOWN",
            target_1=t1,
            target_2=t2,
            target_3=t3,
            invalidation=key_levels.invalidation,
            confirmation=key_levels.confirmation,
            stop_loss=stop_loss,
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

        entry_ref = key_levels.confirmation or key_levels.support or key_levels.resistance
        if entry_ref and recent_pivots:
            stop_loss = _compute_tighter_sl(
                bias="BEARISH",
                structural_sl=float(key_levels.invalidation),
                entry_price=float(entry_ref),
                recent_pivots=recent_pivots,
                atr=atr,
            )
        else:
            stop_loss = key_levels.support

        return FutureProjection(
            expected_structure="ABC_CORRECTION",
            expected_direction="UP",
            target_1=t1,
            target_2=t2,
            target_3=t3,
            invalidation=key_levels.invalidation,
            confirmation=key_levels.confirmation,
            stop_loss=stop_loss,
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
