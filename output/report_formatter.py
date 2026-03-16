from __future__ import annotations

from analysis.inprogress_detector import InProgressWave
from analysis.key_levels import KeyLevels
from analysis.trend_classifier import TrendClassification
from analysis.wave_detector import ABCPattern, ImpulsePattern
from analysis.wave_labeler import format_current_wave, format_wave_with_degree, phase_description
from analysis.wave_position import WavePosition, describe_current_leg
from scenarios.scenario_engine import Scenario

_SEP = "═" * 60
_THIN = "─" * 60


def _pct(entry: float, price: float) -> str:
    if entry == 0:
        return ""
    return f"{(price - entry) / entry * 100:+.1f}%"


def _rr(entry: float, stop: float, target: float) -> str:
    risk = abs(entry - stop)
    reward = abs(target - entry)
    if risk == 0:
        return "—"
    return f"1:{reward / risk:.1f}"


def _fmt(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}"


def _check(ok: bool | None) -> str:
    if ok is True:
        return "✅"
    if ok is False:
        return "❌"
    return "—"


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _section_header(symbol: str, timeframe: str) -> list[str]:
    return [
        _SEP,
        f"  WAVE ANALYSIS: {symbol}  |  {timeframe}",
        _SEP,
        f"Symbol: {symbol}",
        f"Timeframe: {timeframe}",
    ]


def _section_primary_count(
    position: WavePosition,
    pattern_type: str | None,
    inprogress: InProgressWave | None,
    timeframe: str,
    confidence: float | None,
    probability: float | None,
) -> list[str]:
    lines = [""]

    # Determine current wave label
    wave_num = (position.wave_number or describe_current_leg(position) or "?")
    if wave_num and wave_num != "?":
        wave_label = format_wave_with_degree(wave_num, timeframe)
    else:
        wave_label = "Unknown position"

    pattern_display = (pattern_type or "").replace("_", " ").title() if pattern_type else "—"
    phase = phase_description(wave_num, position.bias.lower()) if wave_num != "?" else "—"

    if inprogress and inprogress.is_valid:
        ip_label = format_current_wave(inprogress.wave_number, timeframe)
        building_str = f"Building {ip_label} ({'↑' if inprogress.direction == 'bullish' else '↓'})"
    else:
        building_str = position.position

    lines += [
        f"  Primary Count :  {wave_label} — {phase}",
        f"  Pattern Type  :  {pattern_display}",
        f"  Current Wave  :  {building_str}",
        f"  Bias          :  {position.bias}",
    ]

    if confidence is not None:
        pct = int(round(confidence * 100))
        lines.append(f"  Confidence    :  {pct}%")
    if probability is not None:
        pct = int(round(probability * 100))
        lines.append(f"  Probability   :  {pct}%")

    return lines


def _section_key_levels(
    current_price: float,
    key_levels: KeyLevels | None,
    inprogress: InProgressWave | None,
    timeframe: str,
) -> list[str]:
    lines = ["", _THIN, "  KEY LEVELS", _THIN]

    lines.append(f"  Current Price :  ${_fmt(current_price)}")

    if key_levels is not None:
        if getattr(key_levels, "resistance", None) is not None:
            lines.append(f"  Resistance    :  ${_fmt(key_levels.resistance)}")
        if getattr(key_levels, "support", None) is not None:
            lines.append(f"  Support       :  ${_fmt(key_levels.support)}")
        if getattr(key_levels, "confirmation", None) is not None:
            lines.append(f"  Confirmation  :  ${_fmt(key_levels.confirmation)}")
        if getattr(key_levels, "invalidation", None) is not None:
            lines.append(f"  Invalidation  :  ${_fmt(key_levels.invalidation)}")
        if getattr(key_levels, "wave_start", None) is not None:
            lines.append(f"  Wave Start    :  ${_fmt(key_levels.wave_start)}")
        if getattr(key_levels, "wave_end", None) is not None:
            lines.append(f"  Wave End      :  ${_fmt(key_levels.wave_end)}")

    if inprogress is not None and inprogress.fib_targets:
        lines.append("")
        wave_label = format_current_wave(inprogress.wave_number, timeframe)
        lines.append(f"  Fibonacci Targets for {wave_label}:")
        for ratio, price in inprogress.fib_targets.items():
            lines.append(f"    {ratio:>10} :  ${_fmt(price)}")
        lines.append(f"  Invalidation  :  ${_fmt(inprogress.invalidation)}")

    return lines


def _section_elliott_rules(
    pattern,
    pattern_type: str | None,
    inprogress: InProgressWave | None,
) -> list[str]:
    lines = ["", _THIN, "  ELLIOTT WAVE RULES", _THIN]

    # From completed pattern
    if pattern_type == "IMPULSE" and pattern is not None:
        r1 = getattr(pattern, "rule_wave2_not_beyond_wave1_origin", None)
        r2 = getattr(pattern, "rule_wave3_not_shortest", None)
        r3 = getattr(pattern, "rule_wave4_no_overlap_wave1", None)
        lines += [
            f"  {_check(r1)} Wave 2 rule: Wave 2 never retraces beyond Wave 1 origin",
            f"  {_check(r2)} Wave 3 rule: Wave 3 is not the shortest",
            f"  {_check(r3)} Wave 4 rule: Wave 4 does not overlap Wave 1 territory",
        ]
    elif inprogress is not None and inprogress.rule_checks:
        rule_labels = {
            "rule1_w2_not_beyond_w1":     "Wave 2 never retraces beyond Wave 1 origin",
            "rule2_w3_not_shorter_than_w1": "Wave 3 not shorter than Wave 1 (partial)",
            "rule3_w4_no_overlap":        "Wave 4 does not overlap Wave 1 territory",
        }
        for key, passed in inprogress.rule_checks.items():
            label = rule_labels.get(key, key)
            lines.append(f"  {_check(passed)} {label}")
    else:
        _corrective_types = {
            "ABC_CORRECTION", "FLAT", "EXPANDED_FLAT", "RUNNING_FLAT",
            "WXY", "TRIANGLE", "CONTRACTING_TRIANGLE", "EXPANDING_TRIANGLE",
            "ASCENDING_BARRIER_TRIANGLE", "DESCENDING_BARRIER_TRIANGLE",
        }
        pt = (pattern_type or "").upper()
        if pt in _corrective_types:
            lines.append("  ℹ Corrective pattern — impulse rules (W2/W3/W4) do not apply")
        else:
            lines.append("  — No rule validation data available")

    return lines


def _section_trade_setup(
    scenarios: list[Scenario],
    current_price: float,
) -> list[str]:
    lines = ["", _THIN, "  TRADE SCENARIOS", _THIN]

    if not scenarios:
        lines.append("  — No scenarios available")
        return lines

    for i, s in enumerate(scenarios, 1):
        tag = "[MAIN]" if i == 1 else "[ALT] "
        lines.append(f"")
        lines.append(f"  {i}. {tag}  {s.name}")
        lines.append(f"     Condition    : {s.condition}")
        lines.append(f"     Outlook      : {s.interpretation}")

        entry = getattr(s, "target", None) or current_price
        sl = getattr(s, "stop_loss", None)
        tgt_list = getattr(s, "targets", None) or []
        confirm = getattr(s, "confirmation", None)
        invalidation = getattr(s, "invalidation", None)

        if confirm:
            lines.append(f"     Confirmation : ${_fmt(confirm)}")
        if invalidation:
            lines.append(f"     Invalidation : ${_fmt(invalidation)}")
        if sl:
            lines.append(f"     Stop Loss    : ${_fmt(sl)}  ({_pct(current_price, sl)})")
        if tgt_list:
            for j, t in enumerate(tgt_list, 1):
                if t is not None:
                    rr = _rr(current_price, sl, t) if sl else "—"
                    lines.append(
                        f"     TP{j}          : ${_fmt(t)}"
                        f"  ({_pct(current_price, t)})  R:R {rr}"
                    )

    return lines


def _section_inprogress_detail(
    inprogress: InProgressWave | None,
    timeframe: str,
) -> list[str]:
    if inprogress is None:
        return []

    wave_label = format_current_wave(inprogress.wave_number, timeframe)
    lines = [
        "",
        _THIN,
        f"  IN-PROGRESS WAVE DETAIL  ({timeframe})",
        _THIN,
        f"  Building      :  {wave_label}  ({'↑ Bullish' if inprogress.direction == 'bullish' else '↓ Bearish'})",
        f"  Wave Start    :  ${_fmt(inprogress.current_wave_start)}",
        f"  Invalidation  :  ${_fmt(inprogress.invalidation)}",
        f"  Confidence    :  {int(round(inprogress.confidence * 100))}%",
    ]

    if inprogress.pivots:
        lines.append(f"  Confirmed Pts :  {len(inprogress.pivots)} pivots")
        for j, p in enumerate(inprogress.pivots, 1):
            ts = str(p.timestamp)[:10] if p.timestamp else ""
            lines.append(f"    Wave {j}: {p.type} @ ${_fmt(p.price)}  {ts}")

    return lines


def _section_wave_summary(wave_summary: dict | None) -> list[str]:
    if not wave_summary:
        return []
    lines = ["", _THIN, "  WAVE SUMMARY", _THIN]
    cw = wave_summary.get("current_wave", "—")
    bias = wave_summary.get("bias", "—")
    alt = wave_summary.get("alternate_wave", "—")
    confirm = wave_summary.get("confirm")
    sl = wave_summary.get("stop_loss")
    targets = wave_summary.get("targets")
    lines += [
        f"  Current Wave  :  {cw}",
        f"  Bias          :  {bias}",
        f"  Alt Wave      :  {alt}",
    ]
    if confirm:
        lines.append(f"  Confirm       :  ${_fmt(confirm)}")
    if sl:
        lines.append(f"  Stop Loss     :  ${_fmt(sl)}")
    if targets:
        lines.append(f"  Targets       :  {targets}")
    return lines


def _section_indicators(indicator_context: dict | None, trend: TrendClassification | None) -> list[str]:
    lines = ["", _THIN, "  INDICATORS & CONTEXT", _THIN]

    if trend is not None:
        lines.append(f"  Trend         :  {trend.state}  ({trend.swing_structure})")

    if indicator_context is not None:
        trend_ok = indicator_context.get("trend_ok")
        mom_ok = indicator_context.get("momentum_ok")
        atr_ok = indicator_context.get("atr_ok")
        val_ok = indicator_context.get("indicator_validation")
        div = indicator_context.get("rsi_divergence", "NONE")
        div_msg = indicator_context.get("rsi_divergence_message", "")

        if trend_ok is not None:
            lines.append(f"  Trend Filter  :  {_check(trend_ok)}  {'PASS' if trend_ok else 'FAIL'}")
        if mom_ok is not None:
            lines.append(f"  Momentum      :  {_check(mom_ok)}  {'PASS' if mom_ok else 'FAIL'}")
        if atr_ok is not None:
            lines.append(f"  ATR Expansion :  {_check(atr_ok)}  {'PASS' if atr_ok else 'FAIL'}")
        if val_ok is not None:
            lines.append(f"  Indicator Val :  {_check(val_ok)}  {'PASS' if val_ok else 'FAIL'}")
        lines.append(f"  RSI Divergence:  {div}")
        if div_msg and div != "NONE":
            lines.append(f"  RSI Detail    :  {div_msg}")

    if not trend and not indicator_context:
        lines.append("  — No indicator data available")

    return lines


# ---------------------------------------------------------------------------
# Legacy pattern lines (kept for backward compatibility)
# ---------------------------------------------------------------------------


def _build_pattern_lines(pattern, pattern_type: str | None) -> list[str]:
    pattern_type = (pattern_type or "").upper()
    if pattern is None:
        return []

    if pattern_type in {"ABC_CORRECTION", "FLAT", "EXPANDED_FLAT", "RUNNING_FLAT"}:
        lines = [
            f"  {pattern_type.replace('_', ' ').title()} structure:",
            f"    A = ${_fmt(pattern.a.price)}",
            f"    B = ${_fmt(pattern.b.price)}",
            f"    C = ${_fmt(pattern.c.price)}",
            f"    Direction: {pattern.direction}",
        ]
        if hasattr(pattern, "bc_vs_ab_ratio"):
            lines.append(f"    BC/AB ratio: {pattern.bc_vs_ab_ratio:.3f}")
        return lines

    if pattern_type == "WXY":
        return [
            "  WXY structure detected:",
            f"    W = ${_fmt(pattern.w.price)}",
            f"    X = ${_fmt(pattern.x.price)}",
            f"    Y = ${_fmt(pattern.y.price)}",
            f"    Direction: {pattern.direction}",
        ]

    if pattern_type == "IMPULSE":
        return [
            "  Impulse structure:",
            f"    Wave 1 : ${_fmt(pattern.p1.price)} → ${_fmt(pattern.p2.price)}",
            f"    Wave 2 : ${_fmt(pattern.p2.price)} → ${_fmt(pattern.p3.price)}",
            f"    Wave 3 : ${_fmt(pattern.p3.price)} → ${_fmt(pattern.p4.price)}",
            f"    Wave 4 : ${_fmt(pattern.p4.price)} → ${_fmt(pattern.p5.price)}",
            f"    Wave 5 : ${_fmt(pattern.p5.price)} → ${_fmt(pattern.p6.price)}",
        ]

    if pattern_type in {"ENDING_DIAGONAL", "LEADING_DIAGONAL"}:
        return [
            f"  {pattern_type.replace('_', ' ').title()} structure:",
            f"    P1={_fmt(pattern.p1.price)}  P2={_fmt(pattern.p2.price)}"
            f"  P3={_fmt(pattern.p3.price)}  P4={_fmt(pattern.p4.price)}"
            f"  P5={_fmt(pattern.p5.price)}",
            f"    Overlap: {getattr(pattern, 'overlap_exists', '—')}",
        ]

    return [
        f"  {pattern_type or 'Pattern'} detected (direction: {getattr(pattern, 'direction', '—')})"
    ]


# ---------------------------------------------------------------------------
# Main formatter
# ---------------------------------------------------------------------------


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
    trend: TrendClassification | None = None,
    indicator_context: dict | None = None,
    inprogress: InProgressWave | None = None,
    key_levels: KeyLevels | None = None,
) -> str:
    """Build a full Elliott Wave analysis report string.

    Sections:
        1. Header (symbol + timeframe)
        2. Primary count (wave label, bias, confidence)
        3. Key levels (support, resistance, invalidation, Fib targets)
        4. Pattern detail (completed wave pivots)
        5. Elliott rules validation
        6. In-progress wave detail
        7. Trade scenarios (main + alternate)
        8. Indicators & trend context
        9. Wave summary (decision engine output)
    """
    if impulse_pattern is not None and pattern is None:
        pattern = impulse_pattern
        pattern_type = "IMPULSE"

    lines: list[str] = []

    # 1. Header
    lines += _section_header(symbol, timeframe)

    # 2. Primary count
    lines += _section_primary_count(
        position, pattern_type, inprogress, timeframe, confidence, probability
    )

    # 3. Key levels
    lines += _section_key_levels(current_price, key_levels, inprogress, timeframe)

    # 4. Pattern detail
    pattern_lines = _build_pattern_lines(pattern, pattern_type)
    if pattern_lines:
        lines += ["", _THIN, "  COMPLETED PATTERN STRUCTURE", _THIN]
        lines += pattern_lines

    # 5. Elliott rules
    lines += _section_elliott_rules(pattern, pattern_type, inprogress)

    # 6. In-progress detail
    lines += _section_inprogress_detail(inprogress, timeframe)

    # 7. Trade scenarios
    lines += _section_trade_setup(scenarios, current_price)

    # 8. Indicators
    lines += _section_indicators(indicator_context, trend)

    # 9. Wave summary
    lines += _section_wave_summary(wave_summary)

    lines += ["", _SEP, ""]

    return "\n".join(lines)
