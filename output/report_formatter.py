from __future__ import annotations

from analysis.wave_detector import ABCPattern, ImpulsePattern
from analysis.wave_position import WavePosition
from scenarios.scenario_engine import Scenario


def _build_pattern_lines(pattern, pattern_type: str | None) -> list[str]:
    pattern_type = (pattern_type or "").upper()

    if pattern is None:
        return []

    if pattern_type in {"ABC_CORRECTION", "FLAT", "EXPANDED_FLAT", "RUNNING_FLAT"}:
        lines = [
            "ABC structure detected:" if pattern_type == "ABC_CORRECTION" else f"{pattern_type} structure detected:",
            f"A = {pattern.a.price}",
            f"B = {pattern.b.price}",
            f"C = {pattern.c.price}",
            f"Direction: {pattern.direction}",
        ]
        if hasattr(pattern, "bc_vs_ab_ratio"):
            lines.append(f"BC/AB ratio: {pattern.bc_vs_ab_ratio:.3f}")
        lines.append("")
        return lines

    if pattern_type == "WXY":
        return [
            "WXY structure detected:",
            f"W = {pattern.w.price}",
            f"X = {pattern.x.price}",
            f"Y = {pattern.y.price}",
            f"Direction: {pattern.direction}",
            "",
        ]

    if pattern_type == "TRIANGLE":
        points = ", ".join(str(point.price) for point in pattern.points)
        return [
            "Triangle structure detected:",
            f"Points = {points}",
            f"Direction: {pattern.direction}",
            f"Upper slope: {pattern.upper_slope}",
            f"Lower slope: {pattern.lower_slope}",
            "",
        ]

    if pattern_type == "IMPULSE":
        return [
            "Impulse structure detected:",
            f"Direction: {pattern.direction}",
            f"Wave 1 = {pattern.p1.price} -> {pattern.p2.price}",
            f"Wave 2 = {pattern.p2.price} -> {pattern.p3.price}",
            f"Wave 3 = {pattern.p3.price} -> {pattern.p4.price}",
            f"Wave 4 = {pattern.p4.price} -> {pattern.p5.price}",
            f"Wave 5 = {pattern.p5.price} -> {pattern.p6.price}",
            "",
            "Impulse validation:",
            f"Wave 2 rule: {pattern.rule_wave2_not_beyond_wave1_origin}",
            f"Wave 3 rule: {pattern.rule_wave3_not_shortest}",
            f"Wave 4 rule: {pattern.rule_wave4_no_overlap_wave1}",
            "",
        ]

    if pattern_type in {"ENDING_DIAGONAL", "LEADING_DIAGONAL"}:
        return [
            f"{pattern_type} detected:",
            f"Direction: {pattern.direction}",
            f"P1 = {pattern.p1.price}",
            f"P2 = {pattern.p2.price}",
            f"P3 = {pattern.p3.price}",
            f"P4 = {pattern.p4.price}",
            f"P5 = {pattern.p5.price}",
            f"Overlap exists: {pattern.overlap_exists}",
            "",
        ]

    return [
        f"{pattern_type or 'Pattern'} detected:",
        f"Direction: {getattr(pattern, 'direction', 'unknown')}",
        "",
    ]


def format_report(
    symbol: str,
    timeframe: str,
    current_price: float,
    pattern: ABCPattern | object | None,
    position: WavePosition,
    scenarios: list[Scenario],
    impulse_pattern: ImpulsePattern | None = None,
    confidence: float | None = None,
    probability: float | None = None,
    wave_summary: dict | None = None,
    pattern_type: str | None = None,
) -> str:
    lines = [
        f"Symbol: {symbol}",
        f"Timeframe: {timeframe}",
        "",
    ]

    if wave_summary is not None:
        lines.extend(
            [
                "Wave summary:",
                f"Current wave: {wave_summary.get('current_wave')}",
                f"Bias: {wave_summary.get('bias')}",
                f"Alternate wave: {wave_summary.get('alternate_wave')}",
                f"Confirm: {wave_summary.get('confirm')}",
                f"Stop Loss: {wave_summary.get('stop_loss')}",
                f"Targets: {wave_summary.get('targets')}",
                "",
            ]
        )

    if impulse_pattern is not None and pattern is None:
        pattern = impulse_pattern
        pattern_type = "IMPULSE"

    lines.extend(_build_pattern_lines(pattern, pattern_type))
    lines.extend(
        [
            "Current wave position:",
            f"Structure: {position.structure}",
            f"Position: {position.position}",
            f"Bias: {position.bias}",
            "",
            f"Current price: {current_price}",
        ]
    )

    if confidence is not None:
        lines.append(f"Wave Confidence: {confidence}")

    if probability is not None:
        lines.append(f"Wave Probability: {probability}")

    lines.extend(
        [
            "",
            "Market scenarios:",
        ]
    )

    for i, s in enumerate(scenarios, start=1):
        lines.extend(
            [
                f"{i}. {s.name}",
                f"   If {s.condition}",
                f"   -> {s.interpretation}",
                f"   -> {s.target}",
                f"   -> Confirmation: {s.confirmation}",
                f"   -> Invalidation: {s.invalidation}",
                f"   -> Stop Loss: {s.stop_loss}",
                f"   -> Targets: {s.targets}",
            ]
        )

    return "\n".join(lines)
