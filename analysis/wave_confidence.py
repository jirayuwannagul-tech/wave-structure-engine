from __future__ import annotations


def clamp_score(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def score_rule_validation_from_bool(is_valid: bool) -> float:
    return 1.0 if is_valid else 0.0


def score_structure_quality(structure: str) -> float:
    structure = (structure or "").upper()

    if structure == "IMPULSE":
        return 1.0
    if structure == "ABC_CORRECTION":
        return 0.82
    if structure == "EXPANDED_FLAT":
        return 0.78
    if structure == "RUNNING_FLAT":
        return 0.76
    if structure == "FLAT":
        return 0.72
    if structure == "WXY":
        return 0.74
    if structure in ("CONTRACTING_TRIANGLE", "TRIANGLE"):
        return 0.70
    if structure == "EXPANDING_TRIANGLE":
        return 0.68
    if structure in ("ASCENDING_BARRIER_TRIANGLE", "DESCENDING_BARRIER_TRIANGLE"):
        return 0.72
    if structure in ("ENDING_DIAGONAL", "LEADING_DIAGONAL"):
        return 0.75

    return 0.50


def score_fib_ratio(ratio: float | None, targets: list[float], tolerance: float = 0.12) -> float:
    if ratio is None:
        return 0.50

    ratio = abs(ratio)

    best_diff = min(abs(ratio - t) for t in targets)

    if best_diff <= tolerance * 0.5:
        return 1.0
    if best_diff <= tolerance:
        return 0.8
    if best_diff <= tolerance * 2:
        return 0.6
    return 0.35


def score_abc_fibonacci(pattern) -> float:
    ratio = getattr(pattern, "bc_vs_ab_ratio", None)
    return score_fib_ratio(ratio, [0.382, 0.5, 0.618, 0.786], tolerance=0.15)


def score_impulse_fibonacci(pattern) -> float:
    ratios = [
        getattr(pattern, "wave2_retrace_ratio", None),
        getattr(pattern, "wave4_retrace_ratio", None),
        getattr(pattern, "wave3_vs_wave1_ratio", None),
        getattr(pattern, "wave5_vs_wave1_ratio", None),
    ]

    scores = [
        score_fib_ratio(ratios[0], [0.5, 0.618, 0.786], tolerance=0.18),
        score_fib_ratio(ratios[1], [0.236, 0.382, 0.5], tolerance=0.18),
        score_fib_ratio(ratios[2], [1.0, 1.618, 2.0, 2.618], tolerance=0.22),
        score_fib_ratio(ratios[3], [0.618, 1.0, 1.618], tolerance=0.22),
    ]

    base = round(sum(scores) / len(scores), 3)

    # Extension bonus: extended W3 is the most common valid pattern
    if getattr(pattern, "is_wave3_extended", False):
        base = min(1.0, base + 0.05)

    # Truncation penalty: W5 truncation weakens the impulse
    if getattr(pattern, "wave5_truncated", False):
        base = max(0.0, base - 0.05)

    return base


def score_flat_fibonacci(pattern) -> float:
    ratio = getattr(pattern, "c_vs_a_ratio", None)
    return score_fib_ratio(ratio, [0.5, 0.618, 0.786, 1.0], tolerance=0.18)


def score_expanded_flat_fibonacci(pattern) -> float:
    ratio = getattr(pattern, "c_extension_ratio", None)
    return score_fib_ratio(ratio, [1.0, 1.236, 1.618], tolerance=0.22)


def score_running_flat_fibonacci(pattern) -> float:
    ratio = getattr(pattern, "c_vs_a_ratio", None)
    return score_fib_ratio(ratio, [0.382, 0.5, 0.618, 0.786], tolerance=0.18)


def score_wxy_fibonacci(pattern) -> float:
    ratio = getattr(pattern, "y_vs_w_ratio", None)
    return score_fib_ratio(ratio, [0.5, 0.618, 0.786, 1.0], tolerance=0.18)


def score_diagonal_quality(pattern) -> float:
    overlap_exists = getattr(pattern, "overlap_exists", False)
    is_contracting = getattr(pattern, "is_contracting", False)
    w3_vs_w1 = getattr(pattern, "w3_vs_w1_ratio", 0.0)

    base = 0.82 if overlap_exists else 0.60

    # Fibonacci bonus: w3 should be 0.618-1.0 of w1 for ending diagonal
    if w3_vs_w1 and 0.50 <= w3_vs_w1 <= 1.05:
        base += 0.05

    # Contracting bonus
    if is_contracting:
        base += 0.05

    return min(1.0, base)


def score_triangle_quality(pattern) -> float:
    subtype = str(getattr(pattern, "triangle_subtype", "contracting")).lower()
    upper = abs(getattr(pattern, "upper_slope", 0.0))
    lower = abs(getattr(pattern, "lower_slope", 0.0))

    if subtype == "contracting":
        return 0.80 if (upper > 0 and lower > 0) else 0.60
    if subtype == "expanding":
        return 0.75 if (upper > 0 and lower > 0) else 0.55
    if subtype in ("ascending_barrier", "descending_barrier"):
        return 0.82 if (upper > 0 or lower > 0) else 0.60
    return 0.60


def score_momentum_from_lengths(lengths: list[float]) -> float:
    valid = [abs(x) for x in lengths if x is not None and abs(x) > 0]
    if len(valid) < 2:
        return 0.50

    avg_len = sum(valid) / len(valid)
    latest = valid[-1]
    ratio = latest / avg_len if avg_len > 0 else 1.0

    if ratio >= 1.3:
        return 0.85
    if ratio >= 1.0:
        return 0.70
    if ratio >= 0.7:
        return 0.55
    return 0.40


def score_alternation(pattern) -> float:
    """Score impulse wave alternation guideline (W2 vs W4 should differ in form).

    Returns +0.03 for clear alternation, -0.03 for poor alternation, 0.0 if unclear.
    Applied ONLY to IMPULSE patterns.
    """
    w2_ratio = getattr(pattern, "wave2_retrace_ratio", None)
    w4_ratio = getattr(pattern, "wave4_retrace_ratio", None)

    if w2_ratio is None or w4_ratio is None:
        return 0.0

    # Sharp: retrace > 61.8% (zigzag-like)
    # Flat: retrace < 38.2% (flat/triangle-like)
    w2_sharp = w2_ratio > 0.618
    w4_sharp = w4_ratio > 0.618
    w2_flat = w2_ratio < 0.382
    w4_flat = w4_ratio < 0.382

    if (w2_sharp and w4_flat) or (w2_flat and w4_sharp):
        return 0.03   # clear alternation
    if (w2_sharp and w4_sharp) or (w2_flat and w4_flat):
        return -0.03  # poor alternation
    return 0.0        # indeterminate zone


def score_fib_confluence(
    entry_price: float | None,
    fib_targets: dict[str, float] | None,
    tolerance_pct: float = 0.015,
) -> float:
    """Score how many Fibonacci target levels cluster near the entry price.

    Multiple Fib levels clustering at the same price = high confluence = stronger signal.
    Returns 0.0-0.05 bonus based on how many levels cluster.
    """
    if entry_price is None or not fib_targets:
        return 0.0

    tol = entry_price * tolerance_pct
    nearby_count = sum(
        1 for price in fib_targets.values()
        if abs(price - entry_price) <= tol
    )

    if nearby_count >= 3:
        return 0.05
    if nearby_count == 2:
        return 0.03
    if nearby_count == 1:
        return 0.01
    return 0.0


def compute_wave_confidence(
    rule_score: float,
    fib_score: float,
    structure_score: float,
    momentum_score: float,
    pattern=None,          # optional: pass impulse pattern for alternation scoring
    pattern_type: str = "",
) -> float:
    confidence = (
        rule_score * 0.35
        + fib_score * 0.30
        + structure_score * 0.20
        + momentum_score * 0.15
    )

    # Apply alternation guideline adjustment for impulse patterns
    if pattern_type.upper() == "IMPULSE" and pattern is not None:
        confidence += score_alternation(pattern)

    return round(clamp_score(confidence), 3)