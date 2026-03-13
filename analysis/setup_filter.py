from __future__ import annotations

from dataclasses import dataclass, replace

from storage.experience_store import get_pattern_edge


MIN_MAIN_CONFIDENCE = 0.72
MIN_ALTERNATE_CONFIDENCE = 0.84
MIN_ALTERNATE_PROBABILITY = 0.52


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
        return trend_state == "UPTREND"
    if bias == "BEARISH":
        return trend_state == "DOWNTREND"
    return False


def _is_alternate(scenario, index: int) -> bool:
    name = _scenario_name(scenario).upper()
    return index > 0 or "ALTERNATE" in name


def _is_tradeable_regime(analysis: dict) -> bool:
    trend_state = _trend_state(analysis)
    indicator_context = _indicator_context(analysis)
    atr_ok = bool(indicator_context.get("atr_ok"))
    divergence = str(indicator_context.get("rsi_divergence") or "NONE").upper()

    if trend_state != "SIDEWAY":
        return True

    return atr_ok or divergence != "NONE"


def _passes_quality_gate(
    analysis: dict,
    scenario,
    index: int,
    higher_timeframe_bias: str | None,
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
    is_alternate = _is_alternate(scenario, index)
    side = "LONG" if bias == "BULLISH" else "SHORT" if bias == "BEARISH" else None
    pattern_edge = get_pattern_edge(symbol, timeframe, pattern, side)

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
        return False, "counter-trend against 1D context"

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
    if not atr_ok and divergence == "NONE":
        return False, "main missing atr expansion"
    if not _trend_aligned(bias, trend_state) and not indicator_validation and not atr_ok:
        return False, "main not aligned with trend"

    return True, None


def filter_trade_scenarios(
    analysis: dict,
    higher_timeframe_bias: str | None = None,
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
) -> dict:
    if not analysis:
        return analysis

    filtered_scenarios, decision = filter_trade_scenarios(
        analysis,
        higher_timeframe_bias=higher_timeframe_bias,
    )

    out = dict(analysis)
    out["all_scenarios"] = list(analysis.get("scenarios") or [])
    out["scenarios"] = filtered_scenarios
    out["trade_filter"] = {
        "scenario_count_before": decision.scenario_count_before,
        "scenario_count_after": decision.scenario_count_after,
        "higher_timeframe_bias": decision.higher_timeframe_bias,
        "regime_blocked": decision.regime_blocked,
        "ambiguous_blocked": decision.ambiguous_blocked,
        "notes": decision.notes,
    }
    return out
