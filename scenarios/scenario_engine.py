from __future__ import annotations

from dataclasses import dataclass
from typing import List

from analysis.fibonacci_confluence import score_entry_vs_confluence
from analysis.future_projection import FutureProjection
from analysis.key_levels import KeyLevels
from analysis.wave_position import WavePosition
from storage.experience_store import get_pattern_edge, get_scenario_edge


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
    "CORRECTION",
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
TRIANGLE_STRUCTURES = {
    "TRIANGLE",
    "CONTRACTING_TRIANGLE",
    "EXPANDING_TRIANGLE",
    "ASCENDING_BARRIER_TRIANGLE",
    "DESCENDING_BARRIER_TRIANGLE",
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


def _preferred_level(*values: float | None) -> float | None:
    for value in values:
        if value is not None:
            return float(value)
    return None


def _aligned_targets_or_fallback(
    bias: str,
    confirmation: float | None,
    stop_loss: float | None,
    targets: list[float],
) -> list[float]:
    if confirmation is None or stop_loss is None:
        return []
    aligned_targets = _filter_targets(bias, float(confirmation), list(targets or []))
    if aligned_targets:
        return aligned_targets
    return _build_alternate_targets(bias, confirmation, stop_loss)


def _scenario_expected_rr(scenario: Scenario) -> float:
    if scenario.confirmation is None or scenario.stop_loss is None or not scenario.targets:
        return 0.0

    try:
        entry = float(scenario.confirmation)
        stop_loss = float(scenario.stop_loss)
        risk = abs(entry - stop_loss)
        if risk <= 0:
            return 0.0
        weights = (0.4, 0.3, 0.3)
        weighted = 0.0
        for idx, target in enumerate(scenario.targets[:3]):
            weighted += weights[idx] * (abs(float(target) - entry) / risk)
        return round(min(weighted, 3.0), 4)
    except (TypeError, ValueError):
        return 0.0


def _scenario_micro_risk_penalty(scenario: Scenario) -> float:
    if scenario.confirmation is None or scenario.stop_loss is None:
        return 0.0
    try:
        entry = float(scenario.confirmation)
        stop = float(scenario.stop_loss)
    except (TypeError, ValueError):
        return 0.0

    if entry <= 0:
        return 0.0

    risk_ratio = abs(entry - stop) / entry
    if risk_ratio < 0.001:
        return -1.25
    if risk_ratio < 0.003:
        return -0.65
    if risk_ratio < 0.006:
        return -0.25
    return 0.0


def _scenario_projection_alignment_score(scenario: Scenario, projection: FutureProjection | None) -> float:
    if projection is None:
        return 0.0
    expected = (projection.expected_direction or "").upper()
    bias = (scenario.bias or "").upper()

    if expected == "UP" and bias == "BULLISH":
        return 0.5
    if expected == "DOWN" and bias == "BEARISH":
        return 0.5
    return 0.0


def _scenario_confluence_score(scenario: Scenario, confluence_zones: list | None) -> float:
    if scenario.confirmation is None or not confluence_zones:
        return 0.0
    try:
        return float(score_entry_vs_confluence(float(scenario.confirmation), confluence_zones))
    except (TypeError, ValueError):
        return 0.0


def _scenario_primary_preference_score(scenario_name: str) -> float:
    if scenario_name.startswith("Main "):
        return 0.35
    if scenario_name.startswith("Alternate "):
        return -0.1
    return 0.0


def _experience_edge_score(edge, *, scale: float = 1.0) -> float:
    if edge is None:
        return 0.0

    sample_weight = max(0.35, min(int(edge.sample_count), 8) / 8.0)
    score = ((float(edge.avg_r) * 0.9) + ((float(edge.win_rate) - 0.5) * 1.2)) * sample_weight
    if edge.positive:
        score += 0.7
    if edge.negative:
        score -= 0.5
    if edge.severe_negative:
        score -= 0.9
    return round(score * scale, 6)


def _edge_has_history(edge, min_samples: int) -> bool:
    return bool(edge is not None and int(edge.sample_count) >= int(min_samples))


def _edge_is_positive_candidate(edge, *, min_samples: int, min_avg_r: float = 0.05) -> bool:
    return bool(
        _edge_has_history(edge, min_samples)
        and (float(edge.avg_r) >= float(min_avg_r) or bool(edge.positive))
    )


def _edge_is_prunable_negative(edge, *, min_samples: int, max_avg_r: float = -0.08) -> bool:
    return bool(
        _edge_has_history(edge, min_samples)
        and (
            float(edge.avg_r) <= float(max_avg_r)
            or bool(edge.negative)
            or bool(edge.severe_negative)
        )
    )


def prioritize_scenarios(
    *,
    symbol: str,
    timeframe: str,
    structure: str | None,
    projection: FutureProjection | None,
    scenarios: list[Scenario],
    confluence_zones: list | None = None,
) -> list[Scenario]:
    if not scenarios:
        return []

    ranked: list[dict] = []

    for idx, scenario in enumerate(scenarios):
        scenario_name = str(getattr(scenario, "name", "") or "")
        side = "LONG" if (scenario.bias or "").upper() == "BULLISH" else "SHORT"
        scenario_edge = get_scenario_edge(symbol, timeframe, structure, scenario_name, side)
        pattern_edge = get_pattern_edge(symbol, timeframe, structure, side)
        expected_rr = _scenario_expected_rr(scenario)
        projection_score = _scenario_projection_alignment_score(scenario, projection)
        confluence_score = _scenario_confluence_score(scenario, confluence_zones)
        scenario_edge_score = _experience_edge_score(scenario_edge, scale=1.0)
        pattern_edge_score = _experience_edge_score(pattern_edge, scale=0.45)
        score = (
            (expected_rr * 0.35)
            + (projection_score * 0.7)
            + (confluence_score * 0.5)
            + scenario_edge_score
            + pattern_edge_score
            + _scenario_primary_preference_score(scenario_name)
            + _scenario_micro_risk_penalty(scenario)
        )
        severe_negative = bool(scenario_edge and scenario_edge.severe_negative and expected_rr < 1.2)
        ranked.append(
            {
                "severe_negative": severe_negative,
                "score": round(score, 6),
                "expected_rr": expected_rr,
                "order": -idx,
                "scenario": scenario,
                "scenario_edge": scenario_edge,
                "pattern_edge": pattern_edge,
                "scenario_positive": _edge_is_positive_candidate(scenario_edge, min_samples=2, min_avg_r=0.02),
                "pattern_positive": _edge_is_positive_candidate(pattern_edge, min_samples=4, min_avg_r=0.05),
                "scenario_prunable": _edge_is_prunable_negative(scenario_edge, min_samples=3, max_avg_r=-0.08),
                "pattern_prunable": _edge_is_prunable_negative(pattern_edge, min_samples=5, max_avg_r=-0.08),
            }
        )

    ranked.sort(
        key=lambda item: (
            not item["severe_negative"],
            item["score"],
            item["expected_rr"],
            item["order"],
        ),
        reverse=True,
    )

    positive_ranked = [
        item for item in ranked
        if not item["severe_negative"]
        and (
            item["scenario_positive"]
            or (item["pattern_positive"] and not item["scenario_prunable"])
        )
    ]
    if positive_ranked:
        return [item["scenario"] for item in positive_ranked]

    neutral_ranked = [
        item for item in ranked
        if not item["severe_negative"]
        and not item["scenario_prunable"]
        and not item["pattern_prunable"]
    ]
    if neutral_ranked:
        return [item["scenario"] for item in neutral_ranked]

    historical_ranked = [
        item for item in ranked
        if _edge_has_history(item["scenario_edge"], 3) or _edge_has_history(item["pattern_edge"], 4)
    ]
    if historical_ranked:
        # We have enough evidence to know these variants are consistently weak.
        # Skip the trade instead of forcing a fallback that has already lost often.
        return []

    viable = [item["scenario"] for item in ranked if not item["severe_negative"]]
    if viable:
        return viable
    return [ranked[0]["scenario"]]


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


def _sorted_unique_levels(values, reverse: bool = False) -> list[float]:
    unique_levels: set[float] = set()
    for value in values:
        if value is None:
            continue
        try:
            unique_levels.add(round(float(value), 8))
        except (TypeError, ValueError):
            continue
    return sorted(unique_levels, reverse=reverse)


def _select_inprogress_confirmation(
    direction: str,
    current_price: float,
    wave_start: float | None,
    fib_values: list[float],
) -> float | None:
    if direction == "bullish":
        candidates = [value for value in fib_values if value > current_price]
        if wave_start is not None and wave_start > current_price:
            candidates.append(float(wave_start))
        return min(candidates) if candidates else None

    if direction == "bearish":
        candidates = [value for value in fib_values if value < current_price]
        if wave_start is not None and wave_start < current_price:
            candidates.append(float(wave_start))
        return max(candidates) if candidates else None

    return None


def _select_inprogress_stop(
    direction: str,
    confirmation: float,
    current_price: float,
    wave_start: float | None,
    invalidation: float | None,
    fib_values: list[float],
) -> float:
    if direction == "bullish":
        candidates = [value for value in fib_values if value < confirmation]
        for value in (current_price, wave_start, invalidation):
            if value is not None and float(value) < confirmation:
                candidates.append(float(value))
        return max(candidates) if candidates else round(confirmation * 0.97, 8)

    if direction == "bearish":
        candidates = [value for value in fib_values if value > confirmation]
        for value in (current_price, wave_start, invalidation):
            if value is not None and float(value) > confirmation:
                candidates.append(float(value))
        return min(candidates) if candidates else round(confirmation * 1.03, 8)

    return confirmation


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
        main_targets = _aligned_targets_or_fallback(
            "BULLISH",
            main_confirmation,
            projection.stop_loss,
            targets,
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
                targets=main_targets,
            )
        )
        alt_confirmation = _refine_entry_with_confluence(
            _preferred_level(key_levels.c_level, key_levels.support, key_levels.confirmation),
            "BEARISH",
            _czones,
        )
        alt_targets = _build_alternate_targets(
            "BEARISH",
            alt_confirmation,
            projection.confirmation,
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
                targets=alt_targets,
            )
        )
        return _sanitize_scenarios(scenarios, key_levels)

    if position.structure in CORRECTIVE_STRUCTURES and position.bias == "BEARISH":
        main_confirmation = _refine_entry_with_confluence(
            projection.confirmation, "BEARISH", _czones
        )
        main_targets = _aligned_targets_or_fallback(
            "BEARISH",
            main_confirmation,
            projection.stop_loss,
            targets,
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
                targets=main_targets,
            )
        )
        alt_confirmation = _refine_entry_with_confluence(
            _preferred_level(key_levels.c_level, key_levels.resistance, key_levels.confirmation),
            "BULLISH",
            _czones,
        )
        alt_targets = _build_alternate_targets(
            "BULLISH",
            alt_confirmation,
            projection.confirmation,
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
                targets=alt_targets,
            )
        )
        return _sanitize_scenarios(scenarios, key_levels)

    if position.structure in TREND_STRUCTURES and position.bias == "BULLISH":
        is_in_progress = bool(getattr(position, "building_wave", False))
        wave_number = str(getattr(position, "wave_number", "") or "").upper()
        if is_in_progress or wave_number in {"1", "3", "5", "A", "C"}:
            trend_confirmation = _refine_entry_with_confluence(
                projection.confirmation, "BULLISH", _czones
            )
            continuation_targets = _aligned_targets_or_fallback(
                "BULLISH",
                trend_confirmation,
                projection.stop_loss or key_levels.support,
                targets,
            )
            scenarios.append(
                Scenario(
                    name="Main Bullish",
                    condition=f"price breaks above {trend_confirmation}",
                    interpretation="bullish trend structure likely continues",
                    target=f"move toward {continuation_targets[0] if continuation_targets else projection.target_1}",
                    bias="BULLISH",
                    invalidation=projection.invalidation,
                    confirmation=trend_confirmation,
                    stop_loss=projection.stop_loss or key_levels.support,
                    targets=continuation_targets,
                )
            )
        trend_confirmation = _refine_entry_with_confluence(
            _preferred_level(key_levels.confirmation, projection.confirmation, key_levels.support),
            "BEARISH",
            _czones,
        )
        entry_val = float(trend_confirmation) if trend_confirmation else 0.0
        pullback_sl = _ensure_sl_direction("BEARISH", entry_val, projection.stop_loss or 0.0, key_levels)
        pullback_targets = _aligned_targets_or_fallback("BEARISH", trend_confirmation, pullback_sl, targets)
        if pullback_targets:
            scenarios.append(
                Scenario(
                    name="Main Corrective Pullback",
                    condition=f"price fails below/around {trend_confirmation}",
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
        is_in_progress = bool(getattr(position, "building_wave", False))
        wave_number = str(getattr(position, "wave_number", "") or "").upper()
        if is_in_progress or wave_number in {"1", "3", "5", "A", "C"}:
            trend_confirmation = _refine_entry_with_confluence(
                projection.confirmation, "BEARISH", _czones
            )
            continuation_targets = _aligned_targets_or_fallback(
                "BEARISH",
                trend_confirmation,
                projection.stop_loss or key_levels.resistance,
                targets,
            )
            scenarios.append(
                Scenario(
                    name="Main Bearish",
                    condition=f"price breaks below {trend_confirmation}",
                    interpretation="bearish trend structure likely continues",
                    target=f"move toward {continuation_targets[0] if continuation_targets else projection.target_1}",
                    bias="BEARISH",
                    invalidation=projection.invalidation,
                    confirmation=trend_confirmation,
                    stop_loss=projection.stop_loss or key_levels.resistance,
                    targets=continuation_targets,
                )
            )
        trend_confirmation = _refine_entry_with_confluence(
            _preferred_level(key_levels.confirmation, projection.confirmation, key_levels.resistance),
            "BULLISH",
            _czones,
        )
        entry_val = float(trend_confirmation) if trend_confirmation else 0.0
        rebound_sl = _ensure_sl_direction("BULLISH", entry_val, projection.stop_loss or 0.0, key_levels)
        rebound_targets = _aligned_targets_or_fallback("BULLISH", trend_confirmation, rebound_sl, targets)
        if rebound_targets:
            scenarios.append(
                Scenario(
                    name="Main Corrective Rebound",
                    condition=f"price rebounds from/above {trend_confirmation}",
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

    if position.structure in TRIANGLE_STRUCTURES:
        range_size = 0.0
        if key_levels.support is not None and key_levels.resistance is not None:
            range_size = key_levels.resistance - key_levels.support

        bullish_target = round((key_levels.resistance or 0.0) + (range_size * 1.0), 2)
        bearish_target = round((key_levels.support or 0.0) - (range_size * 1.0), 2)

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

    # Corrective or trend structures with NEUTRAL/unknown bias:
    # generate breakout scenarios from key_levels support/resistance
    if (
        position.structure in CORRECTIVE_STRUCTURES | TREND_STRUCTURES
        and position.bias not in {"BULLISH", "BEARISH"}
        and key_levels.support is not None
        and key_levels.resistance is not None
    ):
        range_size = key_levels.resistance - key_levels.support
        bull_target = round(key_levels.resistance + range_size * 0.618, 6)
        bear_target = round(key_levels.support - range_size * 0.618, 6)
        bull_conf = _refine_entry_with_confluence(key_levels.resistance, "BULLISH", _czones)
        bear_conf = _refine_entry_with_confluence(key_levels.support, "BEARISH", _czones)
        scenarios.append(
            Scenario(
                name="Bullish Breakout",
                condition=f"price closes above {bull_conf}",
                interpretation="structure resolves upward",
                target=f"move toward {bull_target}",
                bias="BULLISH",
                invalidation=key_levels.support,
                confirmation=bull_conf,
                stop_loss=key_levels.support,
                targets=[bull_target],
            )
        )
        scenarios.append(
            Scenario(
                name="Bearish Breakdown",
                condition=f"price closes below {bear_conf}",
                interpretation="structure resolves downward",
                target=f"move toward {bear_target}",
                bias="BEARISH",
                invalidation=key_levels.resistance,
                confirmation=bear_conf,
                stop_loss=key_levels.resistance,
                targets=[bear_target],
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

    if not fib:
        return []

    wave_start_f = float(wave_start) if wave_start is not None else None
    invalidation_f = float(invalidation) if invalidation is not None else None
    fib_values = _sorted_unique_levels(fib.values())
    if not fib_values:
        return []

    if direction == "bullish":
        bias = "BULLISH"
    elif direction == "bearish":
        bias = "BEARISH"
    else:
        return []

    confirmation = _select_inprogress_confirmation(
        direction=direction,
        current_price=float(current_price),
        wave_start=wave_start_f,
        fib_values=fib_values,
    )
    if confirmation is None:
        return []

    stop_loss = _select_inprogress_stop(
        direction=direction,
        confirmation=float(confirmation),
        current_price=float(current_price),
        wave_start=wave_start_f,
        invalidation=invalidation_f,
        fib_values=fib_values,
    )

    if bias == "BULLISH":
        targets = [value for value in fib_values if value > confirmation]
    else:
        targets = sorted([value for value in fib_values if value < confirmation], reverse=True)

    if not targets:
        targets = _build_alternate_targets(bias, confirmation, stop_loss)
    if not targets:
        return []

    scenario_invalidation = invalidation_f if invalidation_f is not None else float(stop_loss)
    if bias == "BULLISH" and scenario_invalidation >= confirmation:
        scenario_invalidation = float(stop_loss)
    if bias == "BEARISH" and scenario_invalidation <= confirmation:
        scenario_invalidation = float(stop_loss)

    scenarios = []
    try:
        s = Scenario(
            name=f"InProgress Wave {wave_number}",
            condition=(
                f"price confirms above {confirmation:.2f}"
                if bias == "BULLISH"
                else f"price confirms below {confirmation:.2f}"
            ),
            interpretation=f"Early entry: wave {wave_number} is building and still has directional room",
            target=f"{targets[0]:.2f}",
            bias=bias,
            invalidation=float(scenario_invalidation),
            confirmation=float(confirmation),
            stop_loss=float(stop_loss),
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
