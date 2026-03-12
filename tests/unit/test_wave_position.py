from analysis.pivot_detector import Pivot
from analysis.swing_builder import SwingPoint
from analysis.wave_detector import ABCPattern, ImpulsePattern
from analysis.wave_position import detect_wave_position
from analysis.wxy_detector import WXYPattern
from analysis.triangle_detector import TrianglePattern


def _swing(index: int, price: float, type_: str) -> SwingPoint:
    return SwingPoint(index=index, price=price, type=type_, timestamp=f"2026-01-0{index}")


def test_detect_wave_position_from_bullish_abc():
    abc = ABCPattern(
        a=Pivot(index=1, price=63030.0, type="L", timestamp="2026-02-28"),
        b=Pivot(index=2, price=74050.0, type="H", timestamp="2026-03-04"),
        c=Pivot(index=3, price=65618.49, type="L", timestamp="2026-03-08"),
        direction="bullish",
        ab_length=11020.0,
        bc_length=8431.51,
        bc_vs_ab_ratio=0.765,
    )

    pos = detect_wave_position(abc_pattern=abc, impulse_pattern=None)

    assert pos.structure == "ABC_CORRECTION"
    assert pos.position == "WAVE_C_END"
    assert pos.bias == "BULLISH"
    assert pos.confidence == "medium"


def test_detect_wave_position_from_bearish_impulse():
    impulse = ImpulsePattern(
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

    pos = detect_wave_position(abc_pattern=None, impulse_pattern=impulse)

    assert pos.structure == "IMPULSE"
    assert pos.position == "WAVE_5_COMPLETE"
    assert pos.bias == "BEARISH"
    assert pos.confidence == "medium"


def test_detect_wave_position_from_bullish_wxy():
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

    pos = detect_wave_position(pattern_type="WXY", pattern=pattern)

    assert pos.structure == "WXY"
    assert pos.position == "CORRECTION_COMPLETE"
    assert pos.bias == "BULLISH"


def test_detect_wave_position_from_triangle():
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
        upper_slope=-2.5,
        lower_slope=1.5,
    )

    pos = detect_wave_position(pattern_type="TRIANGLE", pattern=pattern)

    assert pos.structure == "TRIANGLE"
    assert pos.position == "CONSOLIDATION_END"
    assert pos.bias == "NEUTRAL"
