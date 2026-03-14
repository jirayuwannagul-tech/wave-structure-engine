from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from analysis.wave_detector import ABCPattern, ImpulsePattern


@dataclass
class RuleValidationResult:
    pattern_type: str
    is_valid: bool
    wave2_rule: Optional[bool] = None
    wave3_rule: Optional[bool] = None
    wave4_rule: Optional[bool] = None
    correction_rule: Optional[bool] = None
    message: str = ""


def _build_result(
    pattern_type: str,
    is_valid: bool,
    correction_rule: Optional[bool] = None,
    message: str = "",
) -> RuleValidationResult:
    return RuleValidationResult(
        pattern_type=pattern_type,
        is_valid=is_valid,
        correction_rule=correction_rule,
        message=message,
    )


def validate_impulse_rules(pattern: ImpulsePattern) -> RuleValidationResult:
    wave2_rule = bool(
        pattern.rule_wave2_not_beyond_wave1_origin
        and pattern.wave2_length > 0
        and pattern.wave1_length > 0
        and pattern.wave2_length < pattern.wave1_length
        and pattern.wave2_retrace_ratio < 1.0
    )

    wave3_rule = bool(
        pattern.rule_wave3_not_shortest
        and pattern.wave3_length > 0
        and pattern.wave1_length > 0
        and pattern.wave5_length > 0
        and pattern.wave3_length >= pattern.wave1_length
        and pattern.wave3_length >= pattern.wave5_length
    )

    wave4_rule = bool(
        pattern.rule_wave4_no_overlap_wave1
        and pattern.wave4_length > 0
        and pattern.wave3_length > 0
        and pattern.wave4_length < pattern.wave3_length
    )

    is_valid = bool(wave2_rule and wave3_rule and wave4_rule and pattern.is_valid)

    # Alternation guideline (not a hard rule, but tracked)
    w2_ratio = pattern.wave2_retrace_ratio
    w4_ratio = pattern.wave4_retrace_ratio
    w2_sharp = w2_ratio > 0.618
    w4_sharp = w4_ratio > 0.618
    alternation_ok = not (w2_sharp and w4_sharp) and not (w2_ratio < 0.382 and w4_ratio < 0.382)

    msg_parts = []
    if is_valid:
        msg_parts.append("valid impulse")
    else:
        msg_parts.append("invalid impulse")
    if not alternation_ok:
        msg_parts.append("poor alternation W2/W4")

    return RuleValidationResult(
        pattern_type="impulse",
        is_valid=is_valid,
        wave2_rule=wave2_rule,
        wave3_rule=wave3_rule,
        wave4_rule=wave4_rule,
        message=", ".join(msg_parts),
    )


def validate_abc_rules(pattern: ABCPattern) -> RuleValidationResult:
    max_bc_ratio = 1.000

    if pattern.direction == "bullish":
        correction_rule = bool(
            pattern.b.price > pattern.a.price
            and pattern.c.price < pattern.b.price
            and pattern.c.price > pattern.a.price
            and pattern.ab_length > 0
            and pattern.bc_length > 0
            and 0.500 <= pattern.bc_vs_ab_ratio <= max_bc_ratio
        )
    else:
        correction_rule = bool(
            pattern.b.price < pattern.a.price
            and pattern.c.price > pattern.b.price
            and pattern.c.price < pattern.a.price
            and pattern.ab_length > 0
            and pattern.bc_length > 0
            and 0.500 <= pattern.bc_vs_ab_ratio <= max_bc_ratio
        )

    is_valid = bool(correction_rule)

    return RuleValidationResult(
        pattern_type="abc",
        is_valid=is_valid,
        correction_rule=correction_rule,
        message="valid abc" if is_valid else "invalid abc",
    )


def validate_flat_rules(pattern) -> RuleValidationResult:
    direction = (pattern.direction or "").lower()
    # Regular Flat: B retraces 90-105% of A, C stays within 90-105% of A
    b_ratio_ok = bool(0.90 <= pattern.b_vs_a_ratio <= 1.05)
    c_ratio_ok = bool(0.90 <= pattern.c_vs_a_ratio <= 1.05)

    if direction == "bullish":
        correction_rule = bool(
            pattern.b.price > pattern.a.price
            and pattern.c.price >= pattern.a.price
            and b_ratio_ok
            and c_ratio_ok
        )
    else:
        correction_rule = bool(
            pattern.b.price < pattern.a.price
            and pattern.c.price <= pattern.a.price
            and b_ratio_ok
            and c_ratio_ok
        )

    return _build_result(
        pattern_type="flat",
        is_valid=correction_rule,
        correction_rule=correction_rule,
        message="valid flat" if correction_rule else "invalid flat",
    )


def validate_expanded_flat_rules(pattern) -> RuleValidationResult:
    direction = (pattern.direction or "").lower()
    # Expanded Flat: B must retrace ≥ 100% of A, C must extend > 100% of A
    b_ratio_ok = bool(pattern.b_extension_ratio >= 1.00)
    c_ratio_ok = bool(pattern.c_extension_ratio > 1.0)

    if direction == "bullish":
        correction_rule = bool(
            pattern.b.price > pattern.a.price
            and pattern.c.price < pattern.a.price
            and b_ratio_ok
            and c_ratio_ok
        )
    else:
        correction_rule = bool(
            pattern.b.price < pattern.a.price
            and pattern.c.price > pattern.a.price
            and b_ratio_ok
            and c_ratio_ok
        )

    return _build_result(
        pattern_type="expanded_flat",
        is_valid=correction_rule,
        correction_rule=correction_rule,
        message="valid expanded flat" if correction_rule else "invalid expanded flat",
    )


def validate_running_flat_rules(pattern) -> RuleValidationResult:
    direction = (pattern.direction or "").lower()
    # Running Flat: C retraces less than A (bc/ab < 1.0), C fails to reach A origin
    # b_vs_a_ratio = bc/ab; < 1.0 means C doesn't fully retrace the AB move
    b_ratio_ok = bool(0.0 < getattr(pattern, "b_vs_a_ratio", 0.0) < 1.0)
    c_ratio_ok = bool(0.0 < pattern.c_vs_a_ratio < 1.0)

    if direction == "bullish":
        correction_rule = bool(
            pattern.b.price > pattern.a.price
            and pattern.c.price > pattern.a.price
            and b_ratio_ok
            and c_ratio_ok
        )
    else:
        correction_rule = bool(
            pattern.b.price < pattern.a.price
            and pattern.c.price < pattern.a.price
            and b_ratio_ok
            and c_ratio_ok
        )

    return _build_result(
        pattern_type="running_flat",
        is_valid=correction_rule,
        correction_rule=correction_rule,
        message="valid running flat" if correction_rule else "invalid running flat",
    )


def validate_wxy_rules(pattern) -> RuleValidationResult:
    direction = (pattern.direction or "").lower()
    ratio_ok = bool(0.50 <= pattern.y_vs_w_ratio <= 1.10)  # tightened from 0.3-1.2

    if direction == "bullish":
        correction_rule = bool(
            pattern.x.price > pattern.w.price
            and pattern.y.price > pattern.w.price
            and ratio_ok
        )
    else:
        correction_rule = bool(
            pattern.x.price < pattern.w.price
            and pattern.y.price < pattern.w.price
            and ratio_ok
        )

    return _build_result(
        pattern_type="wxy",
        is_valid=correction_rule,
        correction_rule=correction_rule,
        message="valid wxy" if correction_rule else "invalid wxy",
    )


def validate_triangle_rules(pattern) -> RuleValidationResult:
    has_five_points = len(getattr(pattern, "points", [])) == 5
    upper_slope = float(getattr(pattern, "upper_slope", 0.0))
    lower_slope = float(getattr(pattern, "lower_slope", 0.0))
    subtype = str(getattr(pattern, "triangle_subtype", "contracting")).lower()
    pattern_name = str(getattr(pattern, "pattern_type", "triangle"))

    if subtype == "contracting":
        # Highs descend (upper_slope < 0), lows ascend (lower_slope > 0)
        correction_rule = bool(has_five_points and upper_slope < 0 and lower_slope > 0)

    elif subtype == "expanding":
        # Highs ascend (upper_slope > 0), lows descend (lower_slope < 0)
        correction_rule = bool(has_five_points and upper_slope > 0 and lower_slope < 0)

    elif subtype == "ascending_barrier":
        # Upper boundary flat, lower boundary rising
        correction_rule = bool(has_five_points and lower_slope > 0)

    elif subtype == "descending_barrier":
        # Lower boundary flat, upper boundary falling
        correction_rule = bool(has_five_points and upper_slope < 0)

    else:
        correction_rule = False

    return _build_result(
        pattern_type=pattern_name,
        is_valid=correction_rule,
        correction_rule=correction_rule,
        message=f"valid {subtype} triangle" if correction_rule else f"invalid {subtype} triangle",
    )


def validate_diagonal_rules(pattern) -> RuleValidationResult:
    direction = (pattern.direction or "").lower()
    pattern_type_name = str(getattr(pattern, "pattern_type", "diagonal"))
    is_contracting = getattr(pattern, "is_contracting", False)
    w3_vs_w1 = getattr(pattern, "w3_vs_w1_ratio", 0.0)

    if direction == "bullish":
        overlap_ok = bool(
            pattern.p2.price > pattern.p1.price
            and pattern.p4.price > pattern.p3.price
            and getattr(pattern, "overlap_exists", False)
        )
    else:
        overlap_ok = bool(
            pattern.p2.price < pattern.p1.price
            and pattern.p4.price < pattern.p3.price
            and getattr(pattern, "overlap_exists", False)
        )

    # For ending diagonal: must be contracting
    if "ending" in pattern_type_name.lower():
        correction_rule = bool(overlap_ok and is_contracting)
    else:
        # Leading diagonal: just need overlap and valid direction
        correction_rule = bool(overlap_ok)

    return _build_result(
        pattern_type=pattern_type_name,
        is_valid=correction_rule,
        correction_rule=correction_rule,
        message="valid diagonal" if correction_rule else "invalid diagonal",
    )


def validate_pattern_rules(pattern_type: str, pattern) -> RuleValidationResult:
    pattern_type = (pattern_type or "").upper()

    if pattern_type == "ABC_CORRECTION":
        return validate_abc_rules(pattern)

    if pattern_type == "IMPULSE":
        return validate_impulse_rules(pattern)

    if pattern_type == "FLAT":
        return validate_flat_rules(pattern)

    if pattern_type == "EXPANDED_FLAT":
        return validate_expanded_flat_rules(pattern)

    if pattern_type == "RUNNING_FLAT":
        return validate_running_flat_rules(pattern)

    if pattern_type == "WXY":
        return validate_wxy_rules(pattern)

    if pattern_type in {
        "TRIANGLE",
        "CONTRACTING_TRIANGLE",
        "EXPANDING_TRIANGLE",
        "ASCENDING_BARRIER_TRIANGLE",
        "DESCENDING_BARRIER_TRIANGLE",
    }:
        return validate_triangle_rules(pattern)

    if pattern_type in {"ENDING_DIAGONAL", "LEADING_DIAGONAL"}:
        return validate_diagonal_rules(pattern)

    return _build_result(
        pattern_type=pattern_type.lower(),
        is_valid=False,
        correction_rule=False,
        message="unsupported pattern",
    )


if __name__ == "__main__":
    import pandas as pd
    from analysis.pivot_detector import detect_pivots
    from analysis.wave_detector import detect_latest_abc, detect_latest_impulse

    df = pd.read_csv("data/BTCUSDT_1d.csv")
    df["open_time"] = pd.to_datetime(df["open_time"])

    pivots = detect_pivots(df)

    impulse = detect_latest_impulse(pivots)
    abc = detect_latest_abc(pivots)

    if impulse is not None:
        print(validate_impulse_rules(impulse))

    if abc is not None:
        print(validate_abc_rules(abc))
