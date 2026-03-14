from __future__ import annotations

import pandas as pd

from analysis.diagonal_detector import detect_ending_diagonal
from analysis.expanded_flat_detector import detect_expanded_flat
from analysis.flat_detector import detect_flat
from analysis.indicator_engine import (
    calculate_atr,
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    check_macd_momentum_turning_bearish,
    check_macd_momentum_turning_bullish,
    check_volume_divergence_bearish,
    check_volume_divergence_bullish,
    check_volume_spike,
)
from analysis.indicator_filter import (
    check_atr_expansion,
    check_bearish_momentum,
    check_bearish_trend_context,
    check_bullish_momentum,
    check_bullish_trend_context,
    check_long_term_bearish_trend,
    check_long_term_bullish_trend,
    detect_aligned_rsi_divergence,
    validate_bearish_wave_with_indicators,
    validate_bullish_wave_with_indicators,
)
from analysis.macd_divergence import (
    detect_bearish_macd_divergence,
    detect_bullish_macd_divergence,
)
from analysis.leading_diagonal_detector import detect_leading_diagonal
from analysis.pattern_labeler import label_patterns
from analysis.rule_validator import validate_pattern_rules
from analysis.running_flat_detector import detect_running_flat
from analysis.swing_builder import build_swings
from analysis.triangle_detector import (
    detect_barrier_triangle,
    detect_contracting_triangle,
    detect_expanding_triangle,
)
from analysis.wave_confidence import (
    compute_wave_confidence,
    score_abc_fibonacci,
    score_diagonal_quality,
    score_expanded_flat_fibonacci,
    score_flat_fibonacci,
    score_impulse_fibonacci,
    score_momentum_from_lengths,
    score_rule_validation_from_bool,
    score_running_flat_fibonacci,
    score_structure_quality,
    score_triangle_quality,
    score_wxy_fibonacci,
)
from analysis.wave_detector import detect_latest_abc, detect_latest_impulse
from analysis.wave_probability import rank_wave_counts
from analysis.wxy_detector import detect_wxy

def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _prepare_indicator_df(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None:
        return None

    if len(df) == 0:
        return None

    out = df.copy()

    if "ema50" not in out.columns:
        out["ema50"] = calculate_ema(out, 50)

    if "rsi" not in out.columns:
        out["rsi"] = calculate_rsi(out)

    if "atr" not in out.columns:
        out["atr"] = calculate_atr(out)

    if "macd" not in out.columns:
        macd_df = calculate_macd(out)
        out["macd"] = macd_df["macd"]
        out["macd_signal"] = macd_df["macd_signal"]
        out["macd_hist"] = macd_df["macd_hist"]

    if "volume_ma20" not in out.columns and "volume" in out.columns:
        from analysis.indicator_engine import calculate_volume_ma
        out["volume_ma20"] = calculate_volume_ma(out)

    if "ema200" not in out.columns:
        out["ema200"] = calculate_ema(out, 200)

    return out


def _indicator_adjustment(direction: str, df: pd.DataFrame | None) -> float:
    adjustment, _ = _indicator_adjustment_with_context(direction, df, [])
    return adjustment


def _indicator_adjustment_with_context(
    direction: str,
    df: pd.DataFrame | None,
    pivots,
) -> tuple[float, dict | None]:
    if df is None:
        return 0.0, None

    direction = (direction or "").lower()
    aligned_divergence = detect_aligned_rsi_divergence(direction, df, pivots)

    if direction == "bullish":
        macd_divergence = detect_bullish_macd_divergence(df, pivots)
    elif direction == "bearish":
        macd_divergence = detect_bearish_macd_divergence(df, pivots)
    else:
        macd_divergence = None

    volume_spike = check_volume_spike(df) if "volume" in df.columns else False
    if direction == "bullish":
        vol_div = check_volume_divergence_bullish(df) if "volume" in df.columns else False
    elif direction == "bearish":
        vol_div = check_volume_divergence_bearish(df) if "volume" in df.columns else False
    else:
        vol_div = False

    macd_hist_bullish = check_macd_momentum_turning_bullish(df) if "macd_hist" in df.columns else False
    macd_hist_bearish = check_macd_momentum_turning_bearish(df) if "macd_hist" in df.columns else False

    context = {
        "trend_ok": None,
        "momentum_ok": None,
        "atr_ok": check_atr_expansion(df),
        "indicator_validation": False,
        "rsi_divergence": aligned_divergence.state if aligned_divergence else "NONE",
        "rsi_divergence_message": (
            aligned_divergence.message
            if aligned_divergence
            else "No aligned RSI divergence detected."
        ),
        "macd_divergence": macd_divergence.state if macd_divergence else "NONE",
        "macd_divergence_message": (
            macd_divergence.message
            if macd_divergence
            else "No MACD divergence detected."
        ),
        "volume_spike": volume_spike,
        "volume_divergence": vol_div,
        "macd_hist_turning": macd_hist_bullish if direction == "bullish" else macd_hist_bearish,
        "long_term_trend_ok": check_long_term_bullish_trend(df) if direction == "bullish" else check_long_term_bearish_trend(df),
    }

    if direction == "bullish":
        context["trend_ok"] = check_bullish_trend_context(df)
        context["momentum_ok"] = check_bullish_momentum(df)
        context["indicator_validation"] = validate_bullish_wave_with_indicators(df)
        adjustment = 0.04 if context["indicator_validation"] else -0.04
        if aligned_divergence is not None and context["indicator_validation"]:
            adjustment += 0.02
        if macd_divergence is not None:
            adjustment += 0.015
        if volume_spike:
            adjustment += 0.01
        if vol_div:
            adjustment += 0.01
        if macd_hist_bullish:
            adjustment += 0.01
        # Long-term trend alignment bonus
        if check_long_term_bullish_trend(df):
            adjustment += 0.01
        return adjustment, context

    if direction == "bearish":
        context["trend_ok"] = check_bearish_trend_context(df)
        context["momentum_ok"] = check_bearish_momentum(df)
        context["indicator_validation"] = validate_bearish_wave_with_indicators(df)
        adjustment = 0.04 if context["indicator_validation"] else -0.04
        if aligned_divergence is not None and context["indicator_validation"]:
            adjustment += 0.02
        if macd_divergence is not None:
            adjustment += 0.015
        if volume_spike:
            adjustment += 0.01
        if vol_div:
            adjustment += 0.01
        if macd_hist_bearish:
            adjustment += 0.01
        if check_long_term_bearish_trend(df):
            adjustment += 0.01
        return adjustment, context

    return 0.0, context


def generate_labeled_wave_counts(pivots, timeframe: str, df: pd.DataFrame | None = None):
    counts = generate_wave_counts(pivots, df=df)
    return label_patterns(counts, timeframe)


def _append_count(
    counts: list[dict],
    pattern_type: str,
    pattern,
    confidence: float,
    indicator_context: dict | None = None,
):
    payload = {
        "type": pattern_type,
        "pattern": pattern,
        "confidence": round(_clamp(confidence), 3),
    }
    if indicator_context is not None:
        payload["indicator_context"] = indicator_context
    counts.append(payload)


def generate_wave_counts(pivots, df: pd.DataFrame | None = None):
    counts = []
    indicator_df = _prepare_indicator_df(df)

    abc = detect_latest_abc(pivots)
    impulse = detect_latest_impulse(pivots)
    swings = build_swings(pivots)

    flat = detect_flat(swings)
    expanded_flat = detect_expanded_flat(swings)
    running_flat = detect_running_flat(swings)
    triangle = detect_contracting_triangle(swings)
    expanding_triangle = detect_expanding_triangle(swings)
    barrier_triangle = detect_barrier_triangle(swings)
    wxy = detect_wxy(swings)
    ending_diagonal = detect_ending_diagonal(pivots)
    leading_diagonal = detect_leading_diagonal(pivots)

    if abc is not None:
        rule_result = validate_pattern_rules("ABC_CORRECTION", abc)
        if rule_result.is_valid:
            rule_score = score_rule_validation_from_bool(rule_result.is_valid)
            fib_score = score_abc_fibonacci(abc)
            structure_score = score_structure_quality("ABC_CORRECTION")
            momentum_score = score_momentum_from_lengths([abc.ab_length, abc.bc_length])

            confidence = compute_wave_confidence(
                rule_score=rule_score,
                fib_score=fib_score,
                structure_score=structure_score,
                momentum_score=momentum_score,
            )
            indicator_adjustment, indicator_context = _indicator_adjustment_with_context(
                abc.direction, indicator_df, pivots
            )
            confidence += indicator_adjustment
            _append_count(counts, "ABC_CORRECTION", abc, confidence, indicator_context)

    if impulse is not None:
        rule_result = validate_pattern_rules("IMPULSE", impulse)
        if rule_result.is_valid:
            rule_score = score_rule_validation_from_bool(rule_result.is_valid)
            fib_score = score_impulse_fibonacci(impulse)
            structure_score = score_structure_quality("IMPULSE")
            momentum_score = score_momentum_from_lengths(
                [
                    impulse.wave1_length,
                    impulse.wave2_length,
                    impulse.wave3_length,
                    impulse.wave4_length,
                    impulse.wave5_length,
                ]
            )

            confidence = compute_wave_confidence(
                rule_score=rule_score,
                fib_score=fib_score,
                structure_score=structure_score,
                momentum_score=momentum_score,
            )
            indicator_adjustment, indicator_context = _indicator_adjustment_with_context(
                impulse.direction, indicator_df, pivots
            )
            confidence += indicator_adjustment
            _append_count(counts, "IMPULSE", impulse, confidence, indicator_context)

    if flat is not None:
        rule_result = validate_pattern_rules("FLAT", flat)
        if rule_result.is_valid:
            confidence = compute_wave_confidence(
                rule_score=score_rule_validation_from_bool(rule_result.is_valid),
                fib_score=score_flat_fibonacci(flat),
                structure_score=score_structure_quality("FLAT"),
                momentum_score=score_momentum_from_lengths([flat.ab_length, flat.bc_length]),
            )
            indicator_adjustment, indicator_context = _indicator_adjustment_with_context(
                flat.direction, indicator_df, pivots
            )
            confidence += indicator_adjustment
            _append_count(counts, "FLAT", flat, confidence, indicator_context)

    if expanded_flat is not None:
        rule_result = validate_pattern_rules("EXPANDED_FLAT", expanded_flat)
        if rule_result.is_valid:
            confidence = compute_wave_confidence(
                rule_score=score_rule_validation_from_bool(rule_result.is_valid),
                fib_score=score_expanded_flat_fibonacci(expanded_flat),
                structure_score=score_structure_quality("EXPANDED_FLAT"),
                momentum_score=score_momentum_from_lengths(
                    [expanded_flat.ab_length, expanded_flat.bc_length]
                ),
            )
            indicator_adjustment, indicator_context = _indicator_adjustment_with_context(
                expanded_flat.direction, indicator_df, pivots
            )
            confidence += indicator_adjustment
            _append_count(
                counts,
                "EXPANDED_FLAT",
                expanded_flat,
                confidence,
                indicator_context,
            )

    if running_flat is not None:
        rule_result = validate_pattern_rules("RUNNING_FLAT", running_flat)
        if rule_result.is_valid:
            confidence = compute_wave_confidence(
                rule_score=score_rule_validation_from_bool(rule_result.is_valid),
                fib_score=score_running_flat_fibonacci(running_flat),
                structure_score=score_structure_quality("RUNNING_FLAT"),
                momentum_score=score_momentum_from_lengths(
                    [running_flat.ab_length, running_flat.bc_length]
                ),
            )
            indicator_adjustment, indicator_context = _indicator_adjustment_with_context(
                running_flat.direction, indicator_df, pivots
            )
            confidence += indicator_adjustment
            _append_count(
                counts,
                "RUNNING_FLAT",
                running_flat,
                confidence,
                indicator_context,
            )

    if triangle is not None:
        rule_result = validate_pattern_rules("CONTRACTING_TRIANGLE", triangle)
        if rule_result.is_valid:
            confidence = compute_wave_confidence(
                rule_score=score_rule_validation_from_bool(rule_result.is_valid),
                fib_score=0.65,
                structure_score=score_triangle_quality(triangle),
                momentum_score=0.55,
            )
            _append_count(counts, "CONTRACTING_TRIANGLE", triangle, confidence)

    if expanding_triangle is not None:
        rule_result = validate_pattern_rules("EXPANDING_TRIANGLE", expanding_triangle)
        if rule_result.is_valid:
            confidence = compute_wave_confidence(
                rule_score=score_rule_validation_from_bool(rule_result.is_valid),
                fib_score=0.60,
                structure_score=score_triangle_quality(expanding_triangle),
                momentum_score=0.52,
            )
            _append_count(counts, "EXPANDING_TRIANGLE", expanding_triangle, confidence)

    if barrier_triangle is not None:
        pattern_key = barrier_triangle.pattern_type.upper()
        rule_result = validate_pattern_rules(pattern_key, barrier_triangle)
        if rule_result.is_valid:
            confidence = compute_wave_confidence(
                rule_score=score_rule_validation_from_bool(rule_result.is_valid),
                fib_score=0.65,
                structure_score=score_triangle_quality(barrier_triangle),
                momentum_score=0.55,
            )
            _append_count(counts, pattern_key, barrier_triangle, confidence)

    if wxy is not None:
        rule_result = validate_pattern_rules("WXY", wxy)
        if rule_result.is_valid:
            confidence = compute_wave_confidence(
                rule_score=score_rule_validation_from_bool(rule_result.is_valid),
                fib_score=score_wxy_fibonacci(wxy),
                structure_score=score_structure_quality("WXY"),
                momentum_score=score_momentum_from_lengths([wxy.wx_length, wxy.xy_length]),
            )
            indicator_adjustment, indicator_context = _indicator_adjustment_with_context(
                wxy.direction, indicator_df, pivots
            )
            confidence += indicator_adjustment
            _append_count(counts, "WXY", wxy, confidence, indicator_context)

    if ending_diagonal is not None:
        rule_result = validate_pattern_rules("ENDING_DIAGONAL", ending_diagonal)
        if rule_result.is_valid:
            confidence = compute_wave_confidence(
                rule_score=score_rule_validation_from_bool(rule_result.is_valid),
                fib_score=0.70,
                structure_score=score_diagonal_quality(ending_diagonal),
                momentum_score=0.62,
            )
            indicator_adjustment, indicator_context = _indicator_adjustment_with_context(
                ending_diagonal.direction, indicator_df, pivots
            )
            confidence += indicator_adjustment
            _append_count(
                counts,
                "ENDING_DIAGONAL",
                ending_diagonal,
                confidence,
                indicator_context,
            )

    if leading_diagonal is not None:
        rule_result = validate_pattern_rules("LEADING_DIAGONAL", leading_diagonal)
        if rule_result.is_valid:
            confidence = compute_wave_confidence(
                rule_score=score_rule_validation_from_bool(rule_result.is_valid),
                fib_score=0.68,
                structure_score=score_diagonal_quality(leading_diagonal),
                momentum_score=0.60,
            )
            indicator_adjustment, indicator_context = _indicator_adjustment_with_context(
                leading_diagonal.direction, indicator_df, pivots
            )
            confidence += indicator_adjustment
            _append_count(
                counts,
                "LEADING_DIAGONAL",
                leading_diagonal,
                confidence,
                indicator_context,
            )

    counts = rank_wave_counts(counts)
    return counts
