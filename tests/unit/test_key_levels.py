from analysis.key_levels import (
    align_corrective_key_levels_to_bias,
    extract_abc_key_levels,
    extract_diagonal_key_levels,
    extract_flat_key_levels,
    extract_impulse_key_levels,
    extract_pattern_key_levels,
    extract_triangle_key_levels,
    extract_wxy_key_levels,
)
from analysis.diagonal_detector import DiagonalPattern
from analysis.flat_detector import FlatPattern
from analysis.pivot_detector import Pivot
from analysis.swing_builder import SwingPoint
from analysis.wave_detector import ABCPattern, ImpulsePattern
from analysis.wxy_detector import WXYPattern
from analysis.triangle_detector import TrianglePattern


def _swing(index: int, price: float, type_: str) -> SwingPoint:
    return SwingPoint(index=index, price=price, type=type_, timestamp=f"2026-01-0{index}")


def test_extract_abc_key_levels_bullish():
    pattern = ABCPattern(
        a=Pivot(index=1, price=63030.0, type="L", timestamp="2026-02-28"),
        b=Pivot(index=2, price=74050.0, type="H", timestamp="2026-03-04"),
        c=Pivot(index=3, price=65618.49, type="L", timestamp="2026-03-08"),
        direction="bullish",
        ab_length=11020.0,
        bc_length=8431.51,
        bc_vs_ab_ratio=0.765,
    )

    levels = extract_abc_key_levels(pattern)

    assert levels.structure_type == "abc"
    assert levels.support == 65618.49
    assert levels.resistance == 74050.0
    assert levels.invalidation == 65618.49
    assert levels.confirmation == 74050.0


def test_extract_impulse_key_levels_bearish():
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

    levels = extract_impulse_key_levels(pattern)

    assert levels.structure_type == "impulse"
    assert levels.support == 60
    assert levels.resistance == 80
    assert levels.invalidation == 100
    assert levels.confirmation == 60


def test_align_corrective_key_levels_to_bias_uses_trade_direction():
    levels = align_corrective_key_levels_to_bias(
        extract_abc_key_levels(
            ABCPattern(
                a=Pivot(index=1, price=100.0, type="H", timestamp="2026-01-01"),
                b=Pivot(index=2, price=90.0, type="L", timestamp="2026-01-02"),
                c=Pivot(index=3, price=98.0, type="H", timestamp="2026-01-03"),
                direction="bearish",
                ab_length=10.0,
                bc_length=8.0,
                bc_vs_ab_ratio=0.8,
            )
        ),
        "BULLISH",
    )

    assert levels is not None
    assert levels.support == 90.0
    assert levels.resistance == 98.0
    assert levels.invalidation == 90.0
    assert levels.confirmation == 98.0


def test_extract_pattern_key_levels_for_wxy():
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

    levels = extract_pattern_key_levels("WXY", pattern)

    assert levels is not None
    assert levels.structure_type == "wxy"
    assert levels.support == 110.0
    assert levels.confirmation == 120.0


def test_extract_pattern_key_levels_for_triangle():
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

    levels = extract_pattern_key_levels("TRIANGLE", pattern)

    assert levels is not None
    assert levels.structure_type == "triangle"
    assert levels.support == 100.0
    assert levels.resistance == 120.0


def _make_pivot(i, price, t):
    return Pivot(index=i, price=price, type=t, timestamp=f"2026-01-{i:02d}")


# ---------- extract_abc_key_levels bearish ----------

def test_extract_abc_key_levels_bearish():
    pattern = ABCPattern(
        a=Pivot(index=1, price=100.0, type="H", timestamp="2026-01-01"),
        b=Pivot(index=2, price=90.0, type="L", timestamp="2026-01-02"),
        c=Pivot(index=3, price=98.0, type="H", timestamp="2026-01-03"),
        direction="bearish",
        ab_length=10.0,
        bc_length=8.0,
        bc_vs_ab_ratio=0.8,
    )
    levels = extract_abc_key_levels(pattern)
    assert levels.structure_type == "abc"
    # bearish: support = middle.price, resistance = end.price
    assert levels.support == 90.0
    assert levels.resistance == 98.0
    assert levels.b_level == 90.0
    assert levels.c_level == 98.0


# ---------- extract_impulse_key_levels bullish ----------

def test_extract_impulse_key_levels_bullish():
    pattern = ImpulsePattern(
        p1=Pivot(index=1, price=100, type="L", timestamp="2026-01-01"),
        p2=Pivot(index=2, price=90, type="H", timestamp="2026-01-02"),
        p3=Pivot(index=3, price=130, type="L", timestamp="2026-01-03"),
        p4=Pivot(index=4, price=115, type="H", timestamp="2026-01-04"),
        p5=Pivot(index=5, price=125, type="L", timestamp="2026-01-05"),
        p6=Pivot(index=6, price=155, type="H", timestamp="2026-01-06"),
        direction="bullish",
        wave1_length=30,
        wave2_length=10,
        wave3_length=40,
        wave4_length=15,
        wave5_length=30,
        wave2_retrace_ratio=0.33,
        wave4_retrace_ratio=0.38,
        wave3_vs_wave1_ratio=1.3,
        wave5_vs_wave1_ratio=1.0,
        rule_wave2_not_beyond_wave1_origin=True,
        rule_wave3_not_shortest=True,
        rule_wave4_no_overlap_wave1=True,
        is_valid=True,
    )
    levels = extract_impulse_key_levels(pattern)
    assert levels.structure_type == "impulse"
    # bullish: support=p5.price, resistance=p6.price, invalidation=p1.price
    assert levels.support == 125
    assert levels.resistance == 155
    assert levels.invalidation == 100
    assert levels.confirmation == 155


# ---------- extract_flat_key_levels ----------

def test_extract_flat_key_levels_bullish():
    flat = FlatPattern(
        pattern_type="flat",
        direction="bullish",
        a=_swing(1, 100.0, "L"),
        b=_swing(2, 110.0, "H"),
        c=_swing(3, 102.0, "L"),
        ab_length=10.0,
        bc_length=8.0,
        b_vs_a_ratio=0.95,
        c_vs_a_ratio=0.85,
    )
    levels = extract_flat_key_levels(flat)
    assert levels.structure_type == "flat"
    assert levels.support == 102.0   # end.price (bullish)
    assert levels.resistance == 110.0  # middle.price (bullish)


def test_extract_flat_key_levels_bearish():
    flat = FlatPattern(
        pattern_type="flat",
        direction="bearish",
        a=_swing(1, 100.0, "H"),
        b=_swing(2, 92.0, "L"),
        c=_swing(3, 98.0, "H"),
        ab_length=8.0,
        bc_length=6.0,
        b_vs_a_ratio=0.9,
        c_vs_a_ratio=0.8,
    )
    levels = extract_flat_key_levels(flat)
    assert levels.structure_type == "flat"
    # bearish: support=middle.price, resistance=end.price
    assert levels.support == 92.0
    assert levels.resistance == 98.0


# ---------- extract_wxy_key_levels ----------

def test_extract_wxy_key_levels_bearish():
    pattern = WXYPattern(
        pattern_type="WXY",
        direction="bearish",
        w=_swing(1, 100.0, "H"),
        x=_swing(2, 80.0, "L"),
        y=_swing(3, 90.0, "H"),
        wx_length=20.0,
        xy_length=10.0,
        y_vs_w_ratio=0.5,
    )
    levels = extract_wxy_key_levels(pattern)
    assert levels.structure_type == "wxy"
    # bearish: support=middle.price, resistance=end.price
    assert levels.support == 80.0
    assert levels.resistance == 90.0


# ---------- extract_triangle_key_levels ----------

def test_extract_triangle_key_levels_min_max():
    pattern = TrianglePattern(
        pattern_type="expanding_triangle",
        direction="neutral",
        points=[
            _swing(1, 110.0, "H"),
            _swing(2, 95.0, "L"),
            _swing(3, 120.0, "H"),
            _swing(4, 88.0, "L"),
            _swing(5, 130.0, "H"),
        ],
        upper_slope=2.5,
        lower_slope=-1.5,
    )
    levels = extract_triangle_key_levels(pattern)
    assert levels.support == 88.0
    assert levels.resistance == 130.0
    assert levels.wave_start == 110.0
    assert levels.wave_end == 130.0


# ---------- extract_diagonal_key_levels ----------

def test_extract_diagonal_key_levels_bullish():
    p = lambda i, price, t: _make_pivot(i, price, t)
    pattern = DiagonalPattern(
        pattern_type="ending_diagonal",
        direction="bullish",
        p1=p(1, 100.0, "L"),
        p2=p(2, 95.0, "H"),
        p3=p(3, 115.0, "L"),
        p4=p(4, 108.0, "H"),
        p5=p(5, 125.0, "L"),
        overlap_exists=True,
        is_contracting=True,
    )
    levels = extract_diagonal_key_levels(pattern)
    assert levels.structure_type == "ending_diagonal"
    assert levels.support == min([100, 95, 115, 108, 125])
    assert levels.resistance == max([100, 95, 115, 108, 125])
    assert levels.invalidation == 100.0
    assert levels.confirmation == 125.0  # bullish: max price


def test_extract_diagonal_key_levels_bearish():
    p = lambda i, price, t: _make_pivot(i, price, t)
    pattern = DiagonalPattern(
        pattern_type="ending_diagonal",
        direction="bearish",
        p1=p(1, 130.0, "H"),
        p2=p(2, 120.0, "L"),
        p3=p(3, 125.0, "H"),
        p4=p(4, 115.0, "L"),
        p5=p(5, 110.0, "H"),
        overlap_exists=True,
        is_contracting=True,
    )
    levels = extract_diagonal_key_levels(pattern)
    assert levels.structure_type == "ending_diagonal"
    assert levels.invalidation == 130.0  # p1.price
    assert levels.confirmation == min([130, 120, 125, 115, 110])  # bearish: min price


# ---------- extract_pattern_key_levels dispatch ----------

def test_extract_pattern_key_levels_abc_correction():
    pattern = ABCPattern(
        a=Pivot(index=1, price=100.0, type="L", timestamp="2026-01-01"),
        b=Pivot(index=2, price=110.0, type="H", timestamp="2026-01-02"),
        c=Pivot(index=3, price=105.0, type="L", timestamp="2026-01-03"),
        direction="bullish",
        ab_length=10.0,
        bc_length=5.0,
        bc_vs_ab_ratio=0.5,
    )
    levels = extract_pattern_key_levels("ABC_CORRECTION", pattern)
    assert levels is not None
    assert levels.structure_type == "abc"


def test_extract_pattern_key_levels_flat():
    flat = FlatPattern(
        pattern_type="flat",
        direction="bullish",
        a=_swing(1, 100.0, "L"),
        b=_swing(2, 110.0, "H"),
        c=_swing(3, 102.0, "L"),
        ab_length=10.0,
        bc_length=8.0,
        b_vs_a_ratio=0.95,
        c_vs_a_ratio=0.85,
    )
    levels = extract_pattern_key_levels("FLAT", flat)
    assert levels is not None


def test_extract_pattern_key_levels_expanded_flat():
    from analysis.expanded_flat_detector import ExpandedFlatPattern
    flat = ExpandedFlatPattern(
        pattern_type="expanded_flat",
        direction="bearish",
        a=_swing(1, 100.0, "H"),
        b=_swing(2, 85.0, "L"),
        c=_swing(3, 105.0, "H"),
        ab_length=15.0,
        bc_length=20.0,
        b_extension_ratio=1.1,
        c_extension_ratio=1.05,
    )
    levels = extract_pattern_key_levels("EXPANDED_FLAT", flat)
    assert levels is not None


def test_extract_pattern_key_levels_running_flat():
    from analysis.running_flat_detector import RunningFlatPattern
    flat = RunningFlatPattern(
        pattern_type="running_flat",
        direction="bullish",
        a=_swing(1, 100.0, "L"),
        b=_swing(2, 108.0, "H"),
        c=_swing(3, 104.0, "L"),
        ab_length=8.0,
        bc_length=4.0,
        b_vs_a_ratio=0.5,
        c_vs_a_ratio=0.4,
    )
    levels = extract_pattern_key_levels("RUNNING_FLAT", flat)
    assert levels is not None


def test_extract_pattern_key_levels_ending_diagonal():
    p = lambda i, price, t: _make_pivot(i, price, t)
    pattern = DiagonalPattern(
        pattern_type="ending_diagonal",
        direction="bullish",
        p1=p(1, 100.0, "L"),
        p2=p(2, 95.0, "H"),
        p3=p(3, 115.0, "L"),
        p4=p(4, 108.0, "H"),
        p5=p(5, 125.0, "L"),
        overlap_exists=True,
    )
    levels = extract_pattern_key_levels("ENDING_DIAGONAL", pattern)
    assert levels is not None


def test_extract_pattern_key_levels_leading_diagonal():
    from analysis.leading_diagonal_detector import LeadingDiagonalPattern
    p = lambda i, price, t: _make_pivot(i, price, t)
    pattern = LeadingDiagonalPattern(
        pattern_type="leading_diagonal",
        direction="bearish",
        p1=p(1, 130.0, "H"),
        p2=p(2, 120.0, "L"),
        p3=p(3, 125.0, "H"),
        p4=p(4, 115.0, "L"),
        p5=p(5, 110.0, "H"),
        overlap_exists=True,
    )
    levels = extract_pattern_key_levels("LEADING_DIAGONAL", pattern)
    assert levels is not None


def test_extract_pattern_key_levels_impulse():
    pattern = ImpulsePattern(
        p1=_make_pivot(1, 100, "L"),
        p2=_make_pivot(2, 90, "H"),
        p3=_make_pivot(3, 130, "L"),
        p4=_make_pivot(4, 115, "H"),
        p5=_make_pivot(5, 125, "L"),
        p6=_make_pivot(6, 155, "H"),
        direction="bullish",
        wave1_length=30, wave2_length=10, wave3_length=40,
        wave4_length=15, wave5_length=30,
        wave2_retrace_ratio=0.33, wave4_retrace_ratio=0.38,
        wave3_vs_wave1_ratio=1.3, wave5_vs_wave1_ratio=1.0,
        rule_wave2_not_beyond_wave1_origin=True,
        rule_wave3_not_shortest=True,
        rule_wave4_no_overlap_wave1=True,
        is_valid=True,
    )
    levels = extract_pattern_key_levels("IMPULSE", pattern)
    assert levels is not None
    assert levels.structure_type == "impulse"


def test_extract_pattern_key_levels_unknown_returns_none():
    levels = extract_pattern_key_levels("UNKNOWN_TYPE", object())
    assert levels is None


def test_extract_pattern_key_levels_none_pattern():
    levels = extract_pattern_key_levels("FLAT", None)
    assert levels is None
