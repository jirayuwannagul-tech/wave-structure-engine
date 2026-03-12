from analysis.pivot_detector import Pivot
from analysis.rule_validator import (
    validate_abc_rules,
    validate_impulse_rules,
    validate_pattern_rules,
)
from analysis.swing_builder import SwingPoint
from analysis.wave_detector import ABCPattern, ImpulsePattern
from analysis.wxy_detector import WXYPattern
from analysis.triangle_detector import TrianglePattern


def _swing(index: int, price: float, type_: str) -> SwingPoint:
    return SwingPoint(index=index, price=price, type=type_, timestamp=f"2026-01-0{index}")


def test_validate_impulse_rules_valid_case():
    pattern = ImpulsePattern(
        p1=Pivot(index=1, price=100, type="H", timestamp="2026-01-01"),
        p2=Pivot(index=2, price=90, type="L", timestamp="2026-01-02"),
        p3=Pivot(index=3, price=95, type="H", timestamp="2026-01-03"),
        p4=Pivot(index=4, price=70, type="L", timestamp="2026-01-04"),
        p5=Pivot(index=5, price=80, type="H", timestamp="2026-01-05"),
        p6=Pivot(index=6, price=60, type="L", timestamp="2026-01-06"),
        direction="bearish",
        wave1_length=10,
        wave2_length=5,
        wave3_length=25,
        wave4_length=10,
        wave5_length=20,
        wave2_retrace_ratio=0.5,
        wave4_retrace_ratio=0.4,
        wave3_vs_wave1_ratio=2.5,
        wave5_vs_wave1_ratio=2.0,
        rule_wave2_not_beyond_wave1_origin=True,
        rule_wave3_not_shortest=True,
        rule_wave4_no_overlap_wave1=True,
        is_valid=True,
    )

    result = validate_impulse_rules(pattern)

    assert result.pattern_type == "impulse"
    assert result.is_valid is True
    assert result.wave2_rule is True
    assert result.wave3_rule is True
    assert result.wave4_rule is True


def test_validate_impulse_rules_invalid_when_wave3_shortest():
    pattern = ImpulsePattern(
        p1=Pivot(index=1, price=100, type="H", timestamp="2026-01-01"),
        p2=Pivot(index=2, price=90, type="L", timestamp="2026-01-02"),
        p3=Pivot(index=3, price=95, type="H", timestamp="2026-01-03"),
        p4=Pivot(index=4, price=88, type="L", timestamp="2026-01-04"),
        p5=Pivot(index=5, price=92, type="H", timestamp="2026-01-05"),
        p6=Pivot(index=6, price=80, type="L", timestamp="2026-01-06"),
        direction="bearish",
        wave1_length=10,
        wave2_length=5,
        wave3_length=7,
        wave4_length=4,
        wave5_length=12,
        wave2_retrace_ratio=0.5,
        wave4_retrace_ratio=0.57,
        wave3_vs_wave1_ratio=0.7,
        wave5_vs_wave1_ratio=1.2,
        rule_wave2_not_beyond_wave1_origin=True,
        rule_wave3_not_shortest=False,
        rule_wave4_no_overlap_wave1=True,
        is_valid=False,
    )

    result = validate_impulse_rules(pattern)

    assert result.is_valid is False
    assert result.wave3_rule is False


def test_validate_abc_rules_valid_case():
    pattern = ABCPattern(
        a=Pivot(index=1, price=63030.0, type="L", timestamp="2026-02-28"),
        b=Pivot(index=2, price=74050.0, type="H", timestamp="2026-03-04"),
        c=Pivot(index=3, price=65618.49, type="L", timestamp="2026-03-08"),
        direction="bullish",
        ab_length=11020.0,
        bc_length=8431.51,
        bc_vs_ab_ratio=0.765,
    )

    result = validate_abc_rules(pattern)

    assert result.pattern_type == "abc"
    assert result.is_valid is True
    assert result.correction_rule is True


def test_validate_abc_rules_invalid_when_ratio_too_large():
    pattern = ABCPattern(
        a=Pivot(index=1, price=63030.0, type="L", timestamp="2026-02-28"),
        b=Pivot(index=2, price=74050.0, type="H", timestamp="2026-03-04"),
        c=Pivot(index=3, price=63500.0, type="L", timestamp="2026-03-08"),
        direction="bullish",
        ab_length=11020.0,
        bc_length=30000.0,
        bc_vs_ab_ratio=2.72,
    )

    result = validate_abc_rules(pattern)

    assert result.is_valid is False
    assert result.correction_rule is False


def test_validate_wxy_rules_valid_case():
    pattern = WXYPattern(
        pattern_type="WXY",
        direction="bullish",
        w=_swing(1, 100.0, "L"),
        x=_swing(2, 120.0, "H"),
        y=_swing(3, 110.0, "L"),
        wx_length=20.0,
        xy_length=10.0,
        y_vs_w_ratio=0.5,
    )

    result = validate_pattern_rules("WXY", pattern)

    assert result.is_valid is True
    assert result.correction_rule is True


def test_validate_triangle_rules_valid_case():
    pattern = TrianglePattern(
        pattern_type="contracting_triangle",
        direction="neutral",
        points=[
            _swing(1, 120.0, "H"),
            _swing(2, 100.0, "L"),
            _swing(3, 115.0, "H"),
            _swing(4, 105.0, "L"),
            _swing(5, 110.0, "H"),
        ],
        upper_slope=-2.0,
        lower_slope=1.0,
    )

    result = validate_pattern_rules("TRIANGLE", pattern)

    assert result.is_valid is True
    assert result.correction_rule is True
