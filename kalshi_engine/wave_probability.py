from __future__ import annotations


def _indicator_multiplier(count: dict) -> float:
    """Multiplicative scaling based on indicator confirmation strength.

    A fully confirmed pattern gets up to 1.18×.
    An unconfirmed pattern gets as low as 0.88×.
    This creates a 7-10× larger probability gap than the additive ±0.04
    approach, making the ranking stable and decisive.

    Elliott Wave principle: when RSI momentum aligns with impulse direction
    and MACD histogram is turning, that count should dominate alternatives.
    """
    ctx = count.get("indicator_context") or {}
    if not ctx:
        return 1.0  # no indicator data — neutral, do not penalise

    validated   = bool(ctx.get("indicator_validation", False))
    atr_ok      = bool(ctx.get("atr_ok", False))
    rsi_div     = str(ctx.get("rsi_divergence", "NONE")).upper() != "NONE"
    macd_div    = str(ctx.get("macd_divergence", "NONE")).upper() != "NONE"
    vol_ok      = bool(ctx.get("volume_spike", False)) or bool(ctx.get("volume_divergence", False))
    macd_hist   = bool(ctx.get("macd_hist_turning", False))
    lt_trend    = bool(ctx.get("long_term_trend_ok", False))

    extra_signals = sum([atr_ok, rsi_div, macd_div, vol_ok, macd_hist, lt_trend])

    if validated:
        # Confirmed: base 1.08, +0.02 per extra signal, cap 1.18
        return min(1.18, 1.08 + extra_signals * 0.02)
    else:
        # Unconfirmed: base 0.94, partially offset by extra signals
        return max(0.88, 0.94 + extra_signals * 0.01)


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
        "CONTRACTING_TRIANGLE": -0.01,
        "EXPANDING_TRIANGLE": -0.008,
        "ASCENDING_BARRIER_TRIANGLE": -0.005,
        "DESCENDING_BARRIER_TRIANGLE": -0.005,
    }

    return bonuses.get(pattern_type, 0.0)


def _score_alternation_bonus(pattern) -> float:
    """Alternation guideline: Wave 2 and Wave 4 should alternate in correction form.

    Sharp W2 (retrace > 61.8%) should be followed by flat/sideways W4 (< 38.2%), and vice versa.
    Returns +0.02 for good alternation, -0.02 for poor alternation, 0.0 if indeterminate.
    """
    w2_ratio = getattr(pattern, "wave2_retrace_ratio", None)
    w4_ratio = getattr(pattern, "wave4_retrace_ratio", None)

    if w2_ratio is None or w4_ratio is None:
        return 0.0

    w2_sharp = w2_ratio > 0.618
    w4_sharp = w4_ratio > 0.618
    w2_flat = w2_ratio < 0.382
    w4_flat = w4_ratio < 0.382

    if (w2_sharp and w4_flat) or (w2_flat and w4_sharp):
        return 0.02   # good alternation

    if (w2_sharp and w4_sharp) or (w2_flat and w4_flat):
        return -0.02  # poor alternation — both corrected the same way

    return 0.0  # indeterminate (both in 0.382-0.618 zone)


def _direction_bonus(pattern) -> float:
    direction = (getattr(pattern, "direction", "") or "").lower()

    if direction in ("bullish", "bearish"):
        return 0.01

    return 0.0


def _structure_bonus(count: dict) -> float:
    pattern_type = (count.get("type") or "").upper()
    pattern = count.get("pattern")

    bonus = 0.0
    bonus += _pattern_bonus(pattern_type)
    bonus += _direction_bonus(pattern)

    if pattern_type == "IMPULSE" and pattern is not None:
        bonus += _score_alternation_bonus(pattern)

    return bonus


def normalize_probabilities(counts: list[dict]) -> list[dict]:
    if not counts:
        return counts

    adjusted = []
    for c in counts:
        confidence = float(c.get("confidence", 0.0))
        # Step 1: additive structure bonus (existing)
        additive = confidence + _structure_bonus(c)
        # Step 2: multiplicative indicator scaling (amplifies confirmed patterns)
        multiplier = _indicator_multiplier(c)
        adjusted_confidence = max(0.0, additive * multiplier)
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
