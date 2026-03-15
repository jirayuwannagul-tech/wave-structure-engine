from __future__ import annotations


DEFAULT_AMBIGUITY_THRESHOLD = 0.01
PATTERN_AMBIGUITY_THRESHOLDS = {
    "IMPULSE": 0.01,
    "ABC_CORRECTION": 0.01,
    "EXPANDED_FLAT": 0.01,
    "RUNNING_FLAT": 0.01,
    "WXY": 0.01,
}
PATTERN_MIN_CONFIDENCE = {
    "IMPULSE": 0.80,
    "ABC_CORRECTION": 0.78,
    "EXPANDED_FLAT": 0.78,
    "RUNNING_FLAT": 0.78,
}


def choose_primary_and_alternate(pattern_reports: list[dict]) -> dict:
    if not pattern_reports:
        return {
            "primary": None,
            "alternate": None,
        }

    primary = pattern_reports[0]
    alternate = pattern_reports[1] if len(pattern_reports) > 1 else None

    return {
        "primary": primary,
        "alternate": alternate,
    }


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

    pattern_type = (primary.get("pattern_type") or "").upper()
    required_margin = PATTERN_AMBIGUITY_THRESHOLDS.get(
        pattern_type,
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
        "alternate_wave": alternate["pattern_type"] if alternate else None,
        "confirm": trade_levels.get("confirm"),
        "stop_loss": trade_levels.get("stop_loss"),
        "targets": trade_levels.get("targets", []),
        "is_ambiguous": is_ambiguous,
        "confidence_too_low": confidence_too_low,
    }
