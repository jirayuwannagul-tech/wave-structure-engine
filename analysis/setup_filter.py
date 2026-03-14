from __future__ import annotations

from dataclasses import dataclass, replace

from analysis.wave_position import describe_current_leg

from storage.experience_store import get_pattern_edge


MIN_MAIN_CONFIDENCE = 0.72
MIN_ALTERNATE_CONFIDENCE = 0.84
MIN_ALTERNATE_PROBABILITY = 0.52

CORRECTIVE_PATTERNS = {
    "ABC_CORRECTION",
    "EXPANDED_FLAT",
    "RUNNING_FLAT",
    "WXY",
    "TRIANGLE",
    "CONTRACTING_TRIANGLE",
    "EXPANDING_TRIANGLE",
    "ASCENDING_BARRIER_TRIANGLE",
    "DESCENDING_BARRIER_TRIANGLE",
}

IMPULSE_LIKE_PATTERNS = {
    "IMPULSE",
    "LEADING_DIAGONAL",
    "ENDING_DIAGONAL",
}


@dataclass
class TradeFilterDecision:
    scenario_count_before: int
    scenario_count_after: int
    higher_timeframe_bias: str | None
    regime_blocked: bool
    ambiguous_blocked: bool
    notes: list[str]


def extract_trade_bias(analysis: dict | None) -> str | None:
    if not analysis:
        return None

    scenarios = analysis.get("scenarios") or []
    if scenarios:
        bias = getattr(scenarios[0], "bias", None)
        if bias:
            return str(bias).upper()

    position = analysis.get("position")
    if position is not None:
        bias = getattr(position, "bias", None)
        if bias:
            return str(bias).upper()

    wave_summary = analysis.get("wave_summary") or {}
    bias = wave_summary.get("bias")
    if bias:
        return str(bias).upper()

    return None


def build_higher_timeframe_context(analysis: dict | None) -> dict | None:
    if not analysis:
        return None

    position = analysis.get("position")
    wave_summary = analysis.get("wave_summary") or {}
    wave_sequence = analysis.get("wave_sequence") or {}
    current_leg = wave_sequence.get("current_leg") or {}
    last_completed_leg = wave_sequence.get("last_completed_leg") or {}
    return {
        "timeframe": str(analysis.get("timeframe") or "").upper() or None,
        "bias": extract_trade_bias(analysis),
        "wave_number": (
            current_leg.get("label")
            or getattr(position, "wave_number", None)
            or last_completed_leg.get("label")
            or wave_summary.get("wave_number")
            or wave_summary.get("current_wave")
        ),
        "structure": (
            current_leg.get("structure")
            or getattr(position, "structure", None)
            or last_completed_leg.get("structure")
            or analysis.get("primary_pattern_type")
        ),
        "position": current_leg.get("position") or getattr(position, "position", None),
        "wave_sequence": {
            "current_leg": current_leg or None,
            "last_completed_leg": last_completed_leg or None,
            "pattern_count": wave_sequence.get("pattern_count", 0),
        },
    }


def _trend_state(analysis: dict) -> str:
    trend = analysis.get("trend")
    return (getattr(trend, "state", None) or "SIDEWAY").upper()


def _indicator_context(analysis: dict) -> dict:
    return analysis.get("indicator_context") or {}


def _scenario_bias(scenario) -> str | None:
    bias = getattr(scenario, "bias", None)
    return None if bias is None else str(bias).upper()


def _scenario_name(scenario) -> str:
    return str(getattr(scenario, "name", "") or "")


def _trend_aligned(bias: str | None, trend_state: str) -> bool:
    if bias == "BULLISH":
        return trend_state in {"UPTREND", "BROKEN_UP"}
    if bias == "BEARISH":
        return trend_state in {"DOWNTREND", "BROKEN_DOWN"}
    return False


def _is_alternate(scenario, index: int) -> bool:
    name = _scenario_name(scenario).upper()
    return index > 0 or "ALTERNATE" in name


def _pattern_family(pattern: str | None) -> str:
    normalized = str(pattern or "").upper()
    if normalized in IMPULSE_LIKE_PATTERNS:
        return "IMPULSE"
    if normalized in CORRECTIVE_PATTERNS:
        return "CORRECTIVE"
    return "UNKNOWN"


def _normalize_higher_timeframe_context(
    higher_timeframe_bias: str | None,
    htf_wave_number: str | None,
    higher_timeframe_context: dict | None,
) -> dict | None:
    context = dict(higher_timeframe_context or {})
    if higher_timeframe_bias and not context.get("bias"):
        context["bias"] = higher_timeframe_bias
    if htf_wave_number and not context.get("wave_number"):
        context["wave_number"] = htf_wave_number
    return context or None


def _higher_timeframe_phase(context: dict | None) -> str | None:
    if not context:
        return None

    wave_number = str(context.get("wave_number") or "").upper()
    position = str(context.get("position") or "").upper()
    structure = str(context.get("structure") or "").upper()

    if wave_number == "5" and "COMPLETE" in position:
        return "POST_IMPULSE_CORRECTION"
    if wave_number in {"1", "3", "5"}:
        return "IMPULSE"
    if wave_number in {"2", "4", "A", "B", "C", "W", "X", "Y", "Z"}:
        return "CORRECTION"
    if structure in CORRECTIVE_PATTERNS:
        return "CORRECTION"
    if structure in IMPULSE_LIKE_PATTERNS:
        return "IMPULSE"
    return None


def _passes_structure_gate(
    analysis: dict,
    scenario,
    confidence: float,
    higher_timeframe_context: dict | None,
) -> tuple[bool, str | None]:
    if not higher_timeframe_context:
        return True, None

    htf_bias = str(higher_timeframe_context.get("bias") or "").upper() or None
    lower_bias = _scenario_bias(scenario)
    if not htf_bias or not lower_bias or lower_bias == htf_bias:
        return True, None

    pattern_family = _pattern_family(analysis.get("primary_pattern_type"))
    phase = _higher_timeframe_phase(higher_timeframe_context)
    timeframe = str(analysis.get("timeframe") or "").upper()

    if pattern_family != "CORRECTIVE":
        return False, "counter-trend non-corrective against higher timeframe structure"

    threshold = 0.90
    if phase == "IMPULSE":
        threshold = 0.88
    elif phase == "POST_IMPULSE_CORRECTION":
        threshold = 0.92

    if timeframe == "4H":
        threshold += 0.02

    if confidence < threshold:
        return False, "counter-trend correction confidence too low for higher timeframe structure"

    return True, None


def derive_wave_hierarchy(
    analysis: dict,
    higher_timeframe_bias: str | None = None,
    htf_wave_number: str | None = None,
    higher_timeframe_context: dict | None = None,
) -> dict | None:
    normalized_htf_context = _normalize_higher_timeframe_context(
        higher_timeframe_bias=higher_timeframe_bias,
        htf_wave_number=htf_wave_number,
        higher_timeframe_context=higher_timeframe_context,
    )
    if not normalized_htf_context:
        return None

    position = analysis.get("position")
    indicator_context = _indicator_context(analysis)
    child_bias = extract_trade_bias(analysis)
    wave_sequence = analysis.get("wave_sequence") or {}
    current_leg = wave_sequence.get("current_leg") or {}
    last_completed_leg = wave_sequence.get("last_completed_leg") or {}
    child_pattern = str(
        current_leg.get("structure")
        or last_completed_leg.get("structure")
        or analysis.get("primary_pattern_type")
        or ""
    ).upper()
    child_family = _pattern_family(child_pattern)
    child_wave_number = (
        current_leg.get("label")
        or getattr(position, "wave_number", None)
        or last_completed_leg.get("label")
        or (describe_current_leg(position) if getattr(position, "wave_number", None) is not None or getattr(position, "structure", None) is not None else None)
        or str((analysis.get("wave_summary") or {}).get("current_wave") or "").upper()
        or None
    )
    child_position = current_leg.get("position") or getattr(position, "position", None)
    parent_bias = str(normalized_htf_context.get("bias") or "").upper() or None
    parent_phase = _higher_timeframe_phase(normalized_htf_context)
    confidence = float(analysis.get("confidence") or 0.0)

    indicator_support = bool(indicator_context.get("indicator_validation")) or bool(indicator_context.get("atr_ok"))
    indicator_support = indicator_support or str(indicator_context.get("rsi_divergence") or "NONE").upper() != "NONE"
    indicator_support = indicator_support or str(indicator_context.get("macd_divergence") or "NONE").upper() != "NONE"

    role = "UNCLASSIFIED"
    aligned = True

    if parent_bias is None:
        return {
            "parent_timeframe": normalized_htf_context.get("timeframe"),
            "parent_bias": parent_bias,
            "parent_wave_number": normalized_htf_context.get("wave_number"),
            "parent_structure": normalized_htf_context.get("structure"),
            "parent_position": normalized_htf_context.get("position"),
            "parent_phase": parent_phase,
            "child_timeframe": str(analysis.get("timeframe") or "").upper(),
            "child_bias": child_bias,
            "child_wave_number": child_wave_number,
            "child_position": child_position,
            "child_pattern_family": child_family,
            "child_pattern_type": child_pattern,
            "child_role": role,
            "indicator_support": indicator_support,
            "aligned": True,
        }

    if parent_phase in {"CORRECTION", "POST_IMPULSE_CORRECTION"}:
        if child_bias == parent_bias:
            if child_family == "CORRECTIVE":
                role = "A_OR_C"
                aligned = True
            elif child_family == "IMPULSE":
                role = "C_EXTENSION"
                aligned = indicator_support
        else:
            if child_family == "CORRECTIVE":
                role = "B_OR_X"
                aligned = confidence >= 0.88 and indicator_support
            else:
                role = "COUNTERTREND_IMPULSE"
                aligned = False
    elif parent_phase == "IMPULSE":
        if child_bias == parent_bias:
            if child_family == "CORRECTIVE":
                role = "PULLBACK_2_OR_4"
                aligned = True
            elif child_family == "IMPULSE":
                role = "TREND_CONTINUATION_1_3_5"
                aligned = True
        else:
            if child_family == "CORRECTIVE":
                role = "COUNTERTREND_BOUNCE"
                aligned = confidence >= 0.9 and indicator_support
            else:
                role = "COUNTERTREND_IMPULSE"
                aligned = False

    return {
        "parent_timeframe": normalized_htf_context.get("timeframe"),
        "parent_bias": parent_bias,
        "parent_wave_number": normalized_htf_context.get("wave_number"),
        "parent_structure": normalized_htf_context.get("structure"),
        "parent_position": normalized_htf_context.get("position"),
        "parent_phase": parent_phase,
        "child_timeframe": str(analysis.get("timeframe") or "").upper(),
        "child_bias": child_bias,
        "child_wave_number": child_wave_number,
        "child_position": child_position,
        "child_pattern_family": child_family,
        "child_pattern_type": child_pattern,
        "child_role": role,
        "indicator_support": indicator_support,
        "aligned": aligned,
    }


def _is_tradeable_regime(analysis: dict) -> bool:
    trend_state = _trend_state(analysis)
    indicator_context = _indicator_context(analysis)
    atr_ok = bool(indicator_context.get("atr_ok"))
    divergence = str(indicator_context.get("rsi_divergence") or "NONE").upper()
    macd_div = str(indicator_context.get("macd_divergence") or "NONE").upper()

    if trend_state != "SIDEWAY":
        return True

    volume_ok = bool(indicator_context.get("volume_spike")) or bool(indicator_context.get("volume_divergence"))
    return atr_ok or divergence != "NONE" or macd_div != "NONE" or volume_ok


def _passes_quality_gate(
    analysis: dict,
    scenario,
    index: int,
    higher_timeframe_bias: str | None,
    htf_wave_number: str | None = None,
    higher_timeframe_context: dict | None = None,
) -> tuple[bool, str | None]:
    symbol = str(analysis.get("symbol") or "")
    timeframe = str(analysis.get("timeframe") or "")
    pattern = str(analysis.get("primary_pattern_type") or "")
    bias = _scenario_bias(scenario)
    trend_state = _trend_state(analysis)
    indicator_context = _indicator_context(analysis)
    confidence = float(analysis.get("confidence") or 0.0)
    probability = float(analysis.get("probability") or 0.0)
    indicator_validation = bool(indicator_context.get("indicator_validation"))
    atr_ok = bool(indicator_context.get("atr_ok"))
    divergence = str(indicator_context.get("rsi_divergence") or "NONE").upper()
    macd_divergence = str(indicator_context.get("macd_divergence") or "NONE").upper()
    is_alternate = _is_alternate(scenario, index)
    side = "LONG" if bias == "BULLISH" else "SHORT" if bias == "BEARISH" else None
    pattern_edge = get_pattern_edge(symbol, timeframe, pattern, side)
    normalized_htf_context = _normalize_higher_timeframe_context(
        higher_timeframe_bias=higher_timeframe_bias,
        htf_wave_number=htf_wave_number,
        higher_timeframe_context=higher_timeframe_context,
    )
    hierarchy = derive_wave_hierarchy(
        analysis=analysis,
        higher_timeframe_bias=higher_timeframe_bias,
        htf_wave_number=htf_wave_number,
        higher_timeframe_context=higher_timeframe_context,
    )

    main_confidence_threshold = MIN_MAIN_CONFIDENCE
    alternate_confidence_threshold = MIN_ALTERNATE_CONFIDENCE
    alternate_probability_threshold = MIN_ALTERNATE_PROBABILITY

    if pattern_edge is not None:
        if pattern_edge.severe_negative:
            return False, "experience store blocked severe negative pattern edge"
        if pattern_edge.negative and (timeframe.upper() == "4H" or is_alternate):
            return False, "experience store blocked negative pattern edge"
        if pattern_edge.negative:
            main_confidence_threshold += 0.06
            alternate_confidence_threshold += 0.08
            alternate_probability_threshold += 0.04
        elif pattern_edge.positive:
            main_confidence_threshold -= 0.08
            alternate_confidence_threshold -= 0.08
            alternate_probability_threshold -= 0.05

    if higher_timeframe_bias and bias and bias != higher_timeframe_bias:
        # Only hard-block 4H against 1D trend, not 1D against weekly
        if timeframe.upper() in ("4H", "1H", "15M"):
            return False, "counter-trend against 1D context"
        # For 1D, soft-block: allow if very high confidence
        if confidence < 0.85:
            return False, "1D counter-trend: confidence too low"

    structure_ok, structure_note = _passes_structure_gate(
        analysis=analysis,
        scenario=scenario,
        confidence=confidence,
        higher_timeframe_context=normalized_htf_context,
    )
    if not structure_ok:
        return False, structure_note
    if hierarchy is not None and not hierarchy.get("aligned"):
        return False, "child wave not aligned with higher timeframe hierarchy"

    # Wave nesting: if we know the HTF wave number, use it to calibrate confidence
    if htf_wave_number:
        # Trading in Wave 3 of higher timeframe: most powerful, lower threshold
        if htf_wave_number in ("3",):
            main_confidence_threshold = max(0.60, main_confidence_threshold - 0.06)
        # Trading in Wave 5: approaching end, be more selective
        elif htf_wave_number in ("5",):
            main_confidence_threshold = min(0.90, main_confidence_threshold + 0.04)
        # Trading in Wave 2 or 4 (correction): need stronger signal to enter
        elif htf_wave_number in ("2", "4"):
            main_confidence_threshold = min(0.88, main_confidence_threshold + 0.05)
        # Trading in corrective C wave: strong entry opportunity
        elif htf_wave_number == "C":
            main_confidence_threshold = max(0.62, main_confidence_threshold - 0.04)

    if (
        timeframe.upper() == "4H"
        and pattern.upper() in CORRECTIVE_PATTERNS
        and not (pattern_edge is not None and pattern_edge.positive)
    ):
        return False, "4H corrective pattern filtered (IMPULSE only on 4H)"

    if is_alternate:
        if confidence < alternate_confidence_threshold:
            return False, "alternate confidence too low"
        if probability < alternate_probability_threshold:
            return False, "alternate probability too low"
        if not indicator_validation:
            return False, "alternate missing indicator validation"
        if not atr_ok:
            return False, "alternate missing atr expansion"
        if not _trend_aligned(bias, trend_state):
            return False, "alternate not aligned with trend"
        return True, None

    if confidence < main_confidence_threshold:
        return False, "main confidence too low"
    if not atr_ok and divergence == "NONE" and macd_divergence == "NONE":
        return False, "main missing atr expansion"
    if not _trend_aligned(bias, trend_state) and not indicator_validation and not atr_ok:
        return False, "main not aligned with trend"

    return True, None


def filter_trade_scenarios(
    analysis: dict,
    higher_timeframe_bias: str | None = None,
    htf_wave_number: str | None = None,
    higher_timeframe_context: dict | None = None,
) -> tuple[list, TradeFilterDecision]:
    scenarios = list(analysis.get("scenarios") or [])
    notes: list[str] = []

    if not scenarios:
        return [], TradeFilterDecision(
            scenario_count_before=0,
            scenario_count_after=0,
            higher_timeframe_bias=higher_timeframe_bias,
            regime_blocked=False,
            ambiguous_blocked=False,
            notes=[],
        )

    wave_summary = analysis.get("wave_summary") or {}
    inprogress = analysis.get("inprogress")
    inprogress_valid = inprogress is not None and getattr(inprogress, "is_valid", False)
    if bool(wave_summary.get("is_ambiguous")) and not inprogress_valid:
        return [], TradeFilterDecision(
            scenario_count_before=len(scenarios),
            scenario_count_after=0,
            higher_timeframe_bias=higher_timeframe_bias,
            regime_blocked=False,
            ambiguous_blocked=True,
            notes=["wave summary is ambiguous"],
        )

    if not _is_tradeable_regime(analysis):
        return [], TradeFilterDecision(
            scenario_count_before=len(scenarios),
            scenario_count_after=0,
            higher_timeframe_bias=higher_timeframe_bias,
            regime_blocked=True,
            ambiguous_blocked=False,
            notes=["regime filter blocked sideway/chop setup"],
        )

    filtered = []
    for index, scenario in enumerate(scenarios):
        passed, note = _passes_quality_gate(
            analysis=analysis,
            scenario=scenario,
            index=index,
            higher_timeframe_bias=higher_timeframe_bias,
            htf_wave_number=htf_wave_number,
            higher_timeframe_context=higher_timeframe_context,
        )
        if passed:
            filtered.append(scenario)
        elif note:
            notes.append(note)

    return filtered, TradeFilterDecision(
        scenario_count_before=len(scenarios),
        scenario_count_after=len(filtered),
        higher_timeframe_bias=higher_timeframe_bias,
        regime_blocked=False,
        ambiguous_blocked=False,
        notes=notes,
    )


def apply_trade_filters(
    analysis: dict,
    higher_timeframe_bias: str | None = None,
    htf_wave_number: str | None = None,
    higher_timeframe_context: dict | None = None,
) -> dict:
    if not analysis:
        return analysis

    filtered_scenarios, decision = filter_trade_scenarios(
        analysis,
        higher_timeframe_bias=higher_timeframe_bias,
        htf_wave_number=htf_wave_number,
        higher_timeframe_context=higher_timeframe_context,
    )

    out = dict(analysis)
    out["all_scenarios"] = list(analysis.get("scenarios") or [])
    out["scenarios"] = filtered_scenarios
    out["wave_hierarchy"] = derive_wave_hierarchy(
        analysis,
        higher_timeframe_bias=higher_timeframe_bias,
        htf_wave_number=htf_wave_number,
        higher_timeframe_context=higher_timeframe_context,
    )
    out["trade_filter"] = {
        "scenario_count_before": decision.scenario_count_before,
        "scenario_count_after": decision.scenario_count_after,
        "higher_timeframe_bias": decision.higher_timeframe_bias,
        "regime_blocked": decision.regime_blocked,
        "ambiguous_blocked": decision.ambiguous_blocked,
        "notes": decision.notes,
    }
    return out
