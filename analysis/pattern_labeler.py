from __future__ import annotations

from analysis.pattern_similarity_engine import build_pattern_report


def label_patterns(patterns: list[dict], timeframe: str) -> list[dict]:
    reports = []

    for pattern in patterns:
        reports.append(build_pattern_report(pattern, timeframe))

    reports.sort(key=lambda x: x["similarity_score"], reverse=True)
    return reports