from __future__ import annotations

from dataclasses import dataclass
from typing import List

from analysis.fibonacci_confluence import score_entry_vs_confluence
from analysis.future_projection import FutureProjection
from analysis.key_levels import KeyLevels
from analysis.wave_position import WavePosition


@dataclass
class Scenario:
    name: str
    condition: str
    interpretation: str
    target: str
    bias: str
    invalidation: float | None
    confirmation: float | None
    stop_loss: float | None
    targets: list[float]


def _build_targets(projection: FutureProjection) -> list[float]:
    raw = [projection.target_1, projection.target_2, projection.target_3]
    targets: list[float] = []

    for x in raw:
        if x is None:
            continue
        if not targets or x != targets[-1]:
            targets.append(x)

    return targets


def _build_alternate_targets(
    bias: str,
    confirmation: float | None,
    stop_loss: float | None,
) -> list[float]:
    if confirmation is None or stop_loss is None:
        return []

    entry = float(confirmation)
    stop = float(stop_loss)
    risk = abs(entry - stop)
    if risk <= 0:
        return []

    if bias == "BULLISH":
        raw_targets = [
            entry + (risk * 1.0),
            entry + (risk * 1.272),
            entry + (risk * 1.618),
        ]
    elif bias == "BEARISH":
        raw_targets = [
            entry - (risk * 1.0),
            entry - (risk * 1.272),
            entry - (risk * 1.618),
        ]
    else:
        return []

    return [round(target, 4) for target in raw_targets]


def _refine_entry_with_confluence(
    confirmation: float,
    bias: str,
    confluence_zones: list,
    tolerance: float = 0.015,
) -> float:
    """Find the best confluence zone near the confirmation level for entry.

    Looks for a confluence zone within *tolerance* of the raw confirmation price.
    If a qualifying zone is found (strength >= 0.3), its center price is used as
    the refined entry instead of the original fixed level.
    """
    if not confluence_zones or not confirmation:
        return confirmation

    best_zone = None
    best_score = 0.0
    for zone in confluence_zones:
        zone_price = zone.center
        dist = abs(zone_price - confirmation) / confirmation
        if dist <= tolerance and zone.strength > best_score:
            best_zone = zone
            best_score = zone.strength

    if best_zone and best_score >= 0.3:
        return best_zone.center
    return confirmation


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


def _ensure_sl_direction(bias: str, entry: float, sl: float, key_levels: "KeyLevels") -> float:
    """Return a geometrically valid SL for the given bias.

    If the provided SL is already on the correct side it is returned unchanged.
    Otherwise a replacement is derived from key_levels (resistance / support)
    or a fixed percentage buffer.
    """
    if bias == "BULLISH" and sl < entry:
        return sl  # already correct — below entry for LONG
    if bias == "BEARISH" and sl > entry:
        return sl  # already correct — above entry for SHORT

    if bias == "BULLISH":
        # Need SL *below* entry
        alt = getattr(key_levels, "support", None)
        if alt is not None:
            try:
                alt_f = float(alt)
                if alt_f < entry:
                    return round(alt_f * 0.995, 6)
            except (TypeError, ValueError):
                pass
        return round(entry * 0.97, 6)

    # BEARISH — need SL *above* entry
    alt = getattr(key_levels, "resistance", None)
    if alt is not None:
        try:
            alt_f = float(alt)
            if alt_f > entry:
                return round(alt_f * 1.005, 6)
        except (TypeError, ValueError):
            pass
    return round(entry * 1.03, 6)


def _filter_targets(bias: str, entry: float, targets: list[float]) -> list[float]:
    """Keep only targets that are on the correct side of entry."""
    if bias == "BULLISH":
        return [t for t in targets if t > entry]
    if bias == "BEARISH":
        return [t for t in targets if t < entry]
    return targets


def _sanitize_scenarios(scenarios: list, key_levels: "KeyLevels") -> list:
    """Final safety pass: fix SL direction and filter wrong-side targets.

    Ensures every returned scenario is geometrically valid:
    - BULLISH: SL < entry, targets > entry
    - BEARISH: SL > entry, targets < entry
    Scenarios where no valid targets remain are dropped.
    """
    valid = []
    for sc in scenarios:
        if sc.confirmation is None or sc.stop_loss is None:
            continue
        try:
            entry = float(sc.confirmation)
        except (TypeError, ValueError):
            continue
        bias = str(sc.bias).upper()
        sc.stop_loss = _ensure_sl_direction(bias, entry, float(sc.stop_loss or 0), key_levels)
        sc.targets = _filter_targets(bias, entry, sc.targets or [])
        if sc.targets:
            valid.append(sc)
    return valid


def generate_scenarios(
    position: WavePosition,
    key_levels: KeyLevels,
    projection: FutureProjection,
    confluence_zones: list | None = None,
) -> List[Scenario]:
    scenarios: List[Scenario] = []
    targets = _build_targets(projection)
    _czones = confluence_zones or []

    if position.structure in CORRECTIVE_STRUCTURES and position.bias == "BULLISH":
        main_confirmation = _refine_entry_with_confluence(
            projection.confirmation, "BULLISH", _czones
        )
        scenarios.append(
            Scenario(
                name="Main Bullish",
                condition=f"price breaks above {main_confirmation}",
                interpretation="correction likely finished",
                target=f"move toward {projection.target_1} then {projection.target_2}",
                bias="BULLISH",
                invalidation=projection.invalidation,
                confirmation=main_confirmation,
                stop_loss=projection.stop_loss,
                targets=targets,
            )
        )
        alt_confirmation = _refine_entry_with_confluence(
            key_levels.c_level, "BEARISH", _czones
        )
        scenarios.append(
            Scenario(
                name="Alternate Bearish",
                condition=f"price stays below {alt_confirmation}",
                interpretation="bullish count weakens, correction may continue",
                target="look for lower low structure",
                bias="BEARISH",
                invalidation=projection.confirmation,
                confirmation=alt_confirmation,
                stop_loss=projection.confirmation,
                targets=_build_alternate_targets(
                    "BEARISH",
                    alt_confirmation,
                    projection.confirmation,
                ),
            )
        )
        return _sanitize_scenarios(scenarios, key_levels)

    if position.structure in CORRECTIVE_STRUCTURES and position.bias == "BEARISH":
        main_confirmation = _refine_entry_with_confluence(
            projection.confirmation, "BEARISH", _czones
        )
        scenarios.append(
            Scenario(
                name="Main Bearish",
                condition=f"price breaks below {main_confirmation}",
                interpretation="correction likely finished",
                target=f"move toward {projection.target_1} then {projection.target_2}",
                bias="BEARISH",
                invalidation=projection.invalidation,
                confirmation=main_confirmation,
                stop_loss=projection.stop_loss,
                targets=targets,
            )
        )
        alt_confirmation = _refine_entry_with_confluence(
            key_levels.c_level, "BULLISH", _czones
        )
        scenarios.append(
            Scenario(
                name="Alternate Bullish",
                condition=f"price breaks above {alt_confirmation}",
                interpretation="bearish count weakens, upside continuation possible",
                target="look for higher high structure",
                bias="BULLISH",
                invalidation=projection.confirmation,
                confirmation=alt_confirmation,
                stop_loss=projection.confirmation,
                targets=_build_alternate_targets(
                    "BULLISH",
                    alt_confirmation,
                    projection.confirmation,
                ),
            )
        )
        return _sanitize_scenarios(scenarios, key_levels)

    if position.structure in TREND_STRUCTURES and position.bias == "BULLISH":
        trend_confirmation = _refine_entry_with_confluence(
            projection.confirmation, "BEARISH", _czones
        )
        entry_val = float(trend_confirmation) if trend_confirmation else 0.0
        pullback_sl = _ensure_sl_direction("BEARISH", entry_val, projection.stop_loss or 0.0, key_levels)
        pullback_targets = _filter_targets("BEARISH", entry_val, targets)
        if pullback_targets:
            scenarios.append(
                Scenario(
                    name="Main Corrective Pullback",
                    condition=f"price fails below/around {key_levels.confirmation}",
                    interpretation="completed bullish impulse may enter correction",
                    target=f"pullback toward {pullback_targets[0]}",
                    bias="BEARISH",
                    invalidation=projection.invalidation,
                    confirmation=trend_confirmation,
                    stop_loss=pullback_sl,
                    targets=pullback_targets,
                )
            )
        return _sanitize_scenarios(scenarios, key_levels)

    if position.structure in TREND_STRUCTURES and position.bias == "BEARISH":
        trend_confirmation = _refine_entry_with_confluence(
            projection.confirmation, "BULLISH", _czones
        )
        entry_val = float(trend_confirmation) if trend_confirmation else 0.0
        rebound_sl = _ensure_sl_direction("BULLISH", entry_val, projection.stop_loss or 0.0, key_levels)
        rebound_targets = _filter_targets("BULLISH", entry_val, targets)
        if rebound_targets:
            scenarios.append(
                Scenario(
                    name="Main Corrective Rebound",
                    condition=f"price rebounds from/above {key_levels.support}",
                    interpretation="completed bearish impulse may enter correction",
                    target=f"rebound toward {rebound_targets[0]}",
                    bias="BULLISH",
                    invalidation=projection.invalidation,
                    confirmation=trend_confirmation,
                    stop_loss=rebound_sl,
                    targets=rebound_targets,
                )
            )
        return _sanitize_scenarios(scenarios, key_levels)

    if position.structure == "TRIANGLE":
        range_size = 0.0
        if key_levels.support is not None and key_levels.resistance is not None:
            range_size = key_levels.resistance - key_levels.support

        bullish_target = round((key_levels.resistance or 0.0) + (range_size * 0.618), 2)
        bearish_target = round((key_levels.support or 0.0) - (range_size * 0.618), 2)

        bull_confirmation = _refine_entry_with_confluence(
            key_levels.resistance, "BULLISH", _czones
        )
        bear_confirmation = _refine_entry_with_confluence(
            key_levels.support, "BEARISH", _czones
        )

        scenarios.append(
            Scenario(
                name="Bullish Breakout",
                condition=f"price breaks above {bull_confirmation}",
                interpretation="triangle resolves upward",
                target=f"move toward {bullish_target}",
                bias="BULLISH",
                invalidation=key_levels.support,
                confirmation=bull_confirmation,
                stop_loss=key_levels.support,
                targets=[bullish_target],
            )
        )
        scenarios.append(
            Scenario(
                name="Bearish Breakdown",
                condition=f"price breaks below {bear_confirmation}",
                interpretation="triangle resolves downward",
                target=f"move toward {bearish_target}",
                bias="BEARISH",
                invalidation=key_levels.resistance,
                confirmation=bear_confirmation,
                stop_loss=key_levels.resistance,
                targets=[bearish_target],
            )
        )
        return _sanitize_scenarios(scenarios, key_levels)

    scenarios.append(
        Scenario(
            name="Unknown",
            condition="structure unclear",
            interpretation="no strong scenario yet",
            target="wait for confirmation",
            bias="NEUTRAL",
            invalidation=None,
            confirmation=None,
            stop_loss=None,
            targets=[],
        )
    )
    return _sanitize_scenarios(scenarios, key_levels)


def generate_inprogress_scenarios(inprogress, current_price: float) -> list:
    """Generate early-entry scenarios from an in-progress wave structure."""
    if not inprogress or not getattr(inprogress, "is_valid", False):
        return []

    fib = getattr(inprogress, "fib_targets", {}) or {}
    invalidation = getattr(inprogress, "invalidation", None)
    wave_start = getattr(inprogress, "current_wave_start", None)
    direction = getattr(inprogress, "current_wave_direction", None)
    wave_number = getattr(inprogress, "wave_number", "?")

    if not fib or invalidation is None or wave_start is None:
        return []

    fib_values = sorted(fib.values())
    if not fib_values:
        return []

    tp1 = fib_values[0]
    tp2 = fib_values[1] if len(fib_values) > 1 else None
    tp3 = fib_values[2] if len(fib_values) > 2 else None
    targets = [t for t in [tp1, tp2, tp3] if t is not None]

    if direction == "bullish":
        bias = "BULLISH"
        # Only valid if tp1 is above current price (still room to go)
        if tp1 <= current_price:
            return []
    elif direction == "bearish":
        bias = "BEARISH"
        # Only valid if tp1 is below current price
        if tp1 >= current_price:
            return []
    else:
        return []

    # Use the Scenario dataclass - read the existing Scenario class first to match fields
    scenarios = []
    try:
        s = Scenario(
            name=f"InProgress Wave {wave_number}",
            condition=f"Wave {wave_number} building from {wave_start:.2f}",
            interpretation=f"Early entry: wave {wave_number} in progress, targeting fib levels",
            target=f"{tp1:.2f}",
            bias=bias,
            invalidation=float(invalidation),
            confirmation=float(wave_start),
            stop_loss=float(invalidation),
            targets=[float(t) for t in targets],
        )
        scenarios.append(s)
    except Exception:
        pass

    return scenarios


if __name__ == "__main__":
    import pandas as pd
    from analysis.future_projection import project_next_wave
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
        projection = project_next_wave(position, key_levels)
        scenarios = generate_scenarios(position, key_levels, projection)
        for s in scenarios:
            print(s)
