from __future__ import annotations


def _pattern_bonus(pattern_type: str) -> float:
    pattern_type = (pattern_type or "").upper()

    bonuses = {
        "IMPULSE": 0.005,
        "ABC_CORRECTION": 0.004,
        "EXPANDED_FLAT": 0.004,
        "FLAT": 0.003,
        "RUNNING_FLAT": 0.003,
        "WXY": 0.003,
        "ENDING_DIAGONAL": 0.003,
        "LEADING_DIAGONAL": 0.003,
        "TRIANGLE": -0.01,
    }

    return bonuses.get(pattern_type, 0.0)


def _direction_bonus(pattern) -> float:
    direction = (getattr(pattern, "direction", "") or "").lower()

    if direction in ("bullish", "bearish"):
        return 0.01

    return 0.0


def _structure_bonus(count: dict) -> float:
    pattern_type = count.get("type", "")
    pattern = count.get("pattern")

    bonus = 0.0
    bonus += _pattern_bonus(pattern_type)
    bonus += _direction_bonus(pattern)

    return bonus


def normalize_probabilities(counts: list[dict]) -> list[dict]:
    if not counts:
        return counts

    adjusted = []
    for c in counts:
        confidence = float(c.get("confidence", 0.0))
        adjusted_confidence = max(0.0, confidence + _structure_bonus(c))
        c["adjusted_confidence"] = round(adjusted_confidence, 3)
        adjusted.append(adjusted_confidence)

    total = sum(adjusted)

    if total == 0:
        for c in counts:
            c["probability"] = 0.0
        return counts

    for c in counts:
        c["probability"] = round(c["adjusted_confidence"] / total, 3)

    return counts


def rank_wave_counts(counts: list[dict]) -> list[dict]:
    counts = normalize_probabilities(counts)
    counts.sort(
        key=lambda x: (
            x.get("probability", 0),
            x.get("adjusted_confidence", 0),
            x.get("confidence", 0),
        ),
        reverse=True,
    )
    return counts
