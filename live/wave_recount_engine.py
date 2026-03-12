from __future__ import annotations

from analysis.multi_count_engine import generate_labeled_wave_counts
from analysis.pivot_detector import detect_pivots
from analysis.wave_decision_engine import build_wave_summary
from analysis.wave_position import detect_wave_position


def recount_wave(df):

    pivots = detect_pivots(df)
    labeled_counts = generate_labeled_wave_counts(
        pivots,
        timeframe="LIVE",
        df=df,
    )

    if not labeled_counts:
        return None

    summary = build_wave_summary(labeled_counts)
    primary = labeled_counts[0]
    position = detect_wave_position(
        pattern_type=primary.get("pattern_type"),
        pattern=primary.get("pattern"),
    )

    return {
        "structure": position.structure,
        "bias": summary.get("bias") or position.bias,
    }
