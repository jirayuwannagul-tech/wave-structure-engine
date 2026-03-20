from __future__ import annotations


DEFAULT_AMBIGUITY_THRESHOLD = 0.04
PATTERN_AMBIGUITY_THRESHOLDS = {
    "IMPULSE": 0.05,           # impulse vs corrective: require 5pp gap
    "ABC_CORRECTION": 0.06,    # raised: ABC vs EF is structurally ambiguous
    "EXPANDED_FLAT": 0.04,
    "RUNNING_FLAT": 0.04,
    "WXY": 0.04,
}

# EW principle: certain pattern pairs are structurally too similar to distinguish
# reliably. When the alternate falls in one of these "conflict pairs", a larger
# probability margin is required before emitting a signal.
# EXPANDED_FLAT vs WXY: both are 3-wave corrective structures with overlapping
# Fibonacci characteristics — when they compete closely, signal quality is low.
_CONFLICT_PAIR_THRESHOLD: dict[tuple[str, str], float] = {
    ("EXPANDED_FLAT", "WXY"): 0.10,
    ("LEADING_DIAGONAL", "WXY"): 0.051,
    ("LEADING_DIAGONAL", "RUNNING_FLAT"): 0.044,
}

# EW principle: impulse patterns describe the primary trend;
# prefer them over corrective alternatives when the margin is tight
_IMPULSE_LIKE = {"IMPULSE", "LEADING_DIAGONAL", "ENDING_DIAGONAL"}
_TIGHT_MARGIN = 0.03
PATTERN_MIN_CONFIDENCE = {
    "IMPULSE": 0.80,
    "ABC_CORRECTION": 0.78,
    "EXPANDED_FLAT": 0.78,
    "RUNNING_FLAT": 0.78,
}


def choose_primary_and_alternate(pattern_reports: list[dict]) -> dict:
    if not pattern_reports:
        return {"primary": None, "alternate": None}

    if len(pattern_reports) == 1:
        return {"primary": pattern_reports[0], "alternate": None}

    first  = pattern_reports[0]
    second = pattern_reports[1]

    first_prob  = float(first.get("probability") or 0.0)
    second_prob = float(second.get("probability") or 0.0)
    margin = first_prob - second_prob

    # EW principle: when margin is tight and rank-2 is an indicator-confirmed
    # impulse while rank-1 is corrective, prefer the impulse as primary.
    first_type  = (first.get("pattern_type") or first.get("type") or "").upper()
    second_type = (second.get("pattern_type") or second.get("type") or "").upper()

    if (
        0 < margin < _TIGHT_MARGIN
        and first_type not in _IMPULSE_LIKE
        and second_type in _IMPULSE_LIKE
    ):
        impulse_ctx = second.get("indicator_context") or {}
        if bool(impulse_ctx.get("indicator_validation")):
            first, second = second, first

    return {"primary": first, "alternate": second}


def _score_margin(primary: dict | None, alternate: dict | None) -> float:
    if primary is None or alternate is None:
        return 1.0

    primary_probability = primary.get("probability")
    alternate_probability = alternate.get("probability")

    if primary_probability is not None and alternate_probability is not None:
        return float(primary_probability) - float(alternate_probability)

    return float(primary.get("similarity_score", 0.0)) - float(
        alternate.get("similarity_score", 0.0)
    )


def _is_ambiguous(
    primary: dict | None,
    alternate: dict | None,
    ambiguity_threshold: float,
) -> bool:
    if primary is None or alternate is None:
        return False

    primary_type   = (primary.get("pattern_type") or "").upper()
    alternate_type = (alternate.get("pattern_type") or "").upper()

    # Check conflict-pair threshold first (stricter than per-pattern threshold)
    conflict_threshold = _CONFLICT_PAIR_THRESHOLD.get(
        (primary_type, alternate_type)
    )
    if conflict_threshold is not None:
        return _score_margin(primary, alternate) < conflict_threshold

    required_margin = PATTERN_AMBIGUITY_THRESHOLDS.get(
        primary_type,
        ambiguity_threshold,
    )

    return _score_margin(primary, alternate) < required_margin


def _fails_minimum_confidence(primary: dict | None) -> bool:
    if primary is None:
        return False

    pattern_type = (primary.get("pattern_type") or "").upper()
    min_confidence = PATTERN_MIN_CONFIDENCE.get(pattern_type, 0.0)
    confidence = float(primary.get("confidence") or 0.0)

    return confidence < min_confidence


def _build_trade_levels(pattern: dict) -> dict:
    direction = (pattern.get("direction") or "").upper()

    support = pattern.get("support")
    resistance = pattern.get("resistance")

    confirm = None
    stop_loss = None
    targets = []

    if direction == "BULLISH":
        confirm = resistance
        stop_loss = support

        if resistance is not None:
            targets = [round(resistance, 2)]

    if direction == "BEARISH":
        confirm = support
        stop_loss = resistance

        if support is not None:
            targets = [round(support, 2)]

    return {
        "confirm": confirm,
        "stop_loss": stop_loss,
        "targets": targets,
    }


def build_wave_summary(
    pattern_reports: list[dict],
    ambiguity_threshold: float = DEFAULT_AMBIGUITY_THRESHOLD,
) -> dict:
    decision = choose_primary_and_alternate(pattern_reports)

    primary = decision["primary"]
    alternate = decision["alternate"]
    is_ambiguous = _is_ambiguous(primary, alternate, ambiguity_threshold)
    confidence_too_low = _fails_minimum_confidence(primary)
    direction = (primary.get("direction") or "").upper() if primary else ""
    is_actionable = (
        primary is not None
        and direction in {"BULLISH", "BEARISH"}
        and not is_ambiguous
        and not confidence_too_low
    )

    trade_levels = _build_trade_levels(primary) if is_actionable else {}
    bias = direction if is_actionable else None

    return {
        "current_wave": primary["pattern_type"] if primary else None,
        "bias": bias,
        "pattern_direction": direction or None,
        "alternate_wave": alternate["pattern_type"] if alternate else None,
        "confirm": trade_levels.get("confirm"),
        "stop_loss": trade_levels.get("stop_loss"),
        "targets": trade_levels.get("targets", []),
        "is_ambiguous": is_ambiguous,
        "confidence_too_low": confidence_too_low,
    }
