from __future__ import annotations

from analysis.patterns.family_registry import get_family
from analysis.patterns.subtype_registry import get_subtype
from analysis.patterns.direction_registry import get_direction
from analysis.patterns.degree_registry import get_degree


def build_pattern_label(pattern_type: str, direction: str, timeframe: str) -> dict:
    family = get_family(pattern_type)
    subtype = get_subtype(pattern_type)
    dir_label = get_direction(direction)
    degree = get_degree(timeframe)

    return {
        "pattern_type": pattern_type,
        "family": family,
        "subtype": subtype,
        "direction": dir_label,
        "degree": degree,
    }


def compute_similarity_score(confidence: float, probability: float) -> float:
    score = (confidence * 0.7) + (probability * 0.3)
    return round(score, 3)


def build_pattern_report(pattern: dict, timeframe: str) -> dict:
    label = build_pattern_label(
        pattern_type=pattern.get("type"),
        direction=pattern.get("pattern").direction if pattern.get("pattern") else None,
        timeframe=timeframe,
    )

    similarity = compute_similarity_score(
        confidence=pattern.get("confidence", 0.0),
        probability=pattern.get("probability", 0.0),
    )

    return {
        **label,
        "pattern": pattern.get("pattern"),
        "confidence": pattern.get("confidence"),
        "probability": pattern.get("probability"),
        "adjusted_confidence": pattern.get("adjusted_confidence"),
        "indicator_context": pattern.get("indicator_context"),
        "similarity_score": similarity,
    }
