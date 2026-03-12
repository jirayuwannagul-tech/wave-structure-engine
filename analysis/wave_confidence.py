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
    if structure == "TRIANGLE":
        return 0.70
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

    return round(sum(scores) / len(scores), 3)


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
    return 0.82 if overlap_exists else 0.60


def score_triangle_quality(pattern) -> float:
    upper = abs(getattr(pattern, "upper_slope", 0.0))
    lower = abs(getattr(pattern, "lower_slope", 0.0))

    if upper > 0 and lower > 0:
        return 0.80
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


def compute_wave_confidence(
    rule_score: float,
    fib_score: float,
    structure_score: float,
    momentum_score: float,
) -> float:
    confidence = (
        rule_score * 0.35
        + fib_score * 0.30
        + structure_score * 0.20
        + momentum_score * 0.15
    )
    return round(clamp_score(confidence), 3)