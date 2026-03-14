from analysis.pivot_detector import Pivot
from analysis.rule_validator import (
    validate_abc_rules,
    validate_impulse_rules,
    validate_flat_rules,
    validate_expanded_flat_rules,
    validate_running_flat_rules,
    validate_wxy_rules,
    validate_triangle_rules,
    validate_diagonal_rules,
    validate_pattern_rules,
)
from analysis.swing_builder import SwingPoint
from analysis.wave_detector import ABCPattern, ImpulsePattern
from analysis.wxy_detector import WXYPattern
from analysis.triangle_detector import TrianglePattern
from analysis.flat_detector import FlatPattern
from analysis.expanded_flat_detector import ExpandedFlatPattern
from analysis.running_flat_detector import RunningFlatPattern
from analysis.diagonal_detector import DiagonalPattern


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


# ── validate_flat_rules ───────────────────────────────────────────────────────

def _make_flat_bullish(b_vs_a_ratio: float = 0.95, c_price: float = 102.0) -> FlatPattern:
    a = _swing(1, 100.0, "L")
    b = _swing(2, 120.0, "H")
    c = _swing(3, c_price, "L")
    ab = 20.0
    bc = b_vs_a_ratio * ab
    return FlatPattern(
        pattern_type="flat", direction="bullish",
        a=a, b=b, c=c, ab_length=ab, bc_length=bc,
        b_vs_a_ratio=b_vs_a_ratio, c_vs_a_ratio=b_vs_a_ratio,
    )


def test_flat_bullish_valid():
    p = _make_flat_bullish(b_vs_a_ratio=0.95)
    result = validate_flat_rules(p)
    assert result.is_valid is True


def test_flat_bullish_ratio_too_low():
    p = _make_flat_bullish(b_vs_a_ratio=0.40)
    result = validate_flat_rules(p)
    assert result.is_valid is False


def test_flat_bullish_c_below_a():
    a = _swing(1, 100.0, "L")
    b = _swing(2, 120.0, "H")
    c = _swing(3, 95.0, "L")   # c below a → invalid
    p = FlatPattern(
        pattern_type="flat", direction="bullish",
        a=a, b=b, c=c, ab_length=20.0, bc_length=25.0,
        b_vs_a_ratio=1.25, c_vs_a_ratio=1.25,
    )
    result = validate_flat_rules(p)
    assert result.is_valid is False


def test_flat_bearish_valid():
    a = _swing(1, 120.0, "H")
    b = _swing(2, 100.0, "L")
    c = _swing(3, 118.0, "H")
    ab = 20.0
    bc = 18.0
    ratio = bc / ab  # 0.90 — valid
    p = FlatPattern(
        pattern_type="flat", direction="bearish",
        a=a, b=b, c=c, ab_length=ab, bc_length=bc,
        b_vs_a_ratio=ratio, c_vs_a_ratio=ratio,
    )
    result = validate_flat_rules(p)
    assert result.is_valid is True


# ── validate_expanded_flat_rules ──────────────────────────────────────────────

def test_expanded_flat_bullish_valid():
    a = _swing(1, 100.0, "L")
    b = _swing(2, 120.0, "H")
    c = _swing(3, 95.0, "L")   # c below a
    ab = 20.0
    bc = 25.0
    ratio = bc / ab  # 1.25 ≥ 1.00
    p = ExpandedFlatPattern(
        pattern_type="expanded_flat", direction="bullish",
        a=a, b=b, c=c, ab_length=ab, bc_length=bc,
        b_extension_ratio=ratio, c_extension_ratio=ratio,
    )
    result = validate_expanded_flat_rules(p)
    assert result.is_valid is True


def test_expanded_flat_bullish_c_not_below_a():
    a = _swing(1, 100.0, "L")
    b = _swing(2, 120.0, "H")
    c = _swing(3, 105.0, "L")   # c above a → invalid
    ab = 20.0
    bc = 22.0
    ratio = bc / ab  # 1.10
    p = ExpandedFlatPattern(
        pattern_type="expanded_flat", direction="bullish",
        a=a, b=b, c=c, ab_length=ab, bc_length=bc,
        b_extension_ratio=ratio, c_extension_ratio=ratio,
    )
    result = validate_expanded_flat_rules(p)
    assert result.is_valid is False


def test_expanded_flat_bearish_valid():
    a = _swing(1, 120.0, "H")
    b = _swing(2, 100.0, "L")
    c = _swing(3, 125.0, "H")   # c above a
    ab = 20.0
    bc = 25.0
    ratio = bc / ab  # 1.25
    p = ExpandedFlatPattern(
        pattern_type="expanded_flat", direction="bearish",
        a=a, b=b, c=c, ab_length=ab, bc_length=bc,
        b_extension_ratio=ratio, c_extension_ratio=ratio,
    )
    result = validate_expanded_flat_rules(p)
    assert result.is_valid is True


# ── validate_running_flat_rules ───────────────────────────────────────────────

def test_running_flat_bullish_valid():
    a = _swing(1, 100.0, "L")
    b = _swing(2, 120.0, "H")
    c = _swing(3, 104.0, "L")   # above a but below b
    ab = 20.0
    bc = 16.0
    ratio = bc / ab  # 0.80 — 0 < ratio < 1.0, c > a
    p = RunningFlatPattern(
        pattern_type="running_flat", direction="bullish",
        a=a, b=b, c=c, ab_length=ab, bc_length=bc,
        b_vs_a_ratio=ratio, c_vs_a_ratio=ratio,
    )
    result = validate_running_flat_rules(p)
    assert result.is_valid is True


def test_running_flat_bullish_c_below_a():
    a = _swing(1, 100.0, "L")
    b = _swing(2, 120.0, "H")
    c = _swing(3, 95.0, "L")   # below a → invalid (that's expanded flat)
    ab = 20.0
    bc = 25.0
    ratio = bc / ab  # 1.25
    p = RunningFlatPattern(
        pattern_type="running_flat", direction="bullish",
        a=a, b=b, c=c, ab_length=ab, bc_length=bc,
        b_vs_a_ratio=ratio, c_vs_a_ratio=ratio,
    )
    result = validate_running_flat_rules(p)
    assert result.is_valid is False


def test_running_flat_bearish_valid():
    a = _swing(1, 120.0, "H")
    b = _swing(2, 100.0, "L")
    c = _swing(3, 116.0, "H")   # below a, above b
    ab = 20.0
    bc = 16.0
    ratio = bc / ab  # 0.80
    p = RunningFlatPattern(
        pattern_type="running_flat", direction="bearish",
        a=a, b=b, c=c, ab_length=ab, bc_length=bc,
        b_vs_a_ratio=ratio, c_vs_a_ratio=ratio,
    )
    result = validate_running_flat_rules(p)
    assert result.is_valid is True


# ── validate_wxy_rules ────────────────────────────────────────────────────────

def test_wxy_bearish_valid():
    pattern = WXYPattern(
        pattern_type="WXY",
        direction="bearish",
        w=_swing(1, 120.0, "H"),
        x=_swing(2, 100.0, "L"),
        y=_swing(3, 110.0, "H"),
        wx_length=20.0,
        xy_length=10.0,
        y_vs_w_ratio=0.5,
    )
    result = validate_wxy_rules(pattern)
    assert result.is_valid is True


def test_wxy_ratio_too_tight():
    pattern = WXYPattern(
        pattern_type="WXY",
        direction="bullish",
        w=_swing(1, 100.0, "L"),
        x=_swing(2, 120.0, "H"),
        y=_swing(3, 110.0, "L"),
        wx_length=20.0,
        xy_length=10.0,
        y_vs_w_ratio=0.3,   # < 0.50 → invalid
    )
    result = validate_wxy_rules(pattern)
    assert result.is_valid is False


# ── validate_triangle_rules (all subtypes) ────────────────────────────────────

def _make_triangle(subtype: str, upper: float, lower: float) -> TrianglePattern:
    return TrianglePattern(
        pattern_type=f"{subtype}_triangle",
        direction="neutral",
        points=[
            _swing(1, 120.0, "H"),
            _swing(2, 100.0, "L"),
            _swing(3, 115.0, "H"),
            _swing(4, 103.0, "L"),
            _swing(5, 110.0, "H"),
        ],
        upper_slope=upper,
        lower_slope=lower,
        triangle_subtype=subtype,
    )


def test_validate_expanding_triangle():
    # expanding: upper_slope > 0, lower_slope < 0
    p = _make_triangle("expanding", 2.0, -2.0)
    result = validate_triangle_rules(p)
    assert result.is_valid is True


def test_validate_ascending_barrier_triangle():
    # ascending_barrier: lower_slope > 0 is checked
    p = _make_triangle("ascending_barrier", 0.0, 1.5)
    result = validate_triangle_rules(p)
    assert result.is_valid is True


def test_validate_descending_barrier_triangle():
    # descending_barrier: upper_slope < 0 is checked
    p = _make_triangle("descending_barrier", -1.5, 0.0)
    result = validate_triangle_rules(p)
    assert result.is_valid is True


def test_validate_contracting_triangle_invalid_slopes():
    # contracting needs upper < 0 and lower > 0; passing upper > 0, lower < 0 should fail
    p = _make_triangle("contracting", 2.0, -2.0)
    result = validate_triangle_rules(p)
    assert result.is_valid is False


def test_validate_triangle_wrong_point_count():
    p = TrianglePattern(
        pattern_type="contracting_triangle",
        direction="neutral",
        points=[_swing(1, 120.0, "H"), _swing(2, 100.0, "L")],
        upper_slope=-2.0,
        lower_slope=1.0,
        triangle_subtype="contracting",
    )
    result = validate_triangle_rules(p)
    assert result.is_valid is False


# ── validate_diagonal_rules ───────────────────────────────────────────────────

def _make_diagonal(direction, is_contracting, overlap_exists, pattern_type="ending_diagonal"):
    pivots = {
        "bullish": [
            Pivot(index=1, price=100.0, type="L", timestamp="2026-01-01"),
            Pivot(index=2, price=115.0, type="H", timestamp="2026-01-02"),
            Pivot(index=3, price=104.0, type="L", timestamp="2026-01-03"),
            Pivot(index=4, price=112.0, type="H", timestamp="2026-01-04"),
            Pivot(index=5, price=107.0, type="L", timestamp="2026-01-05"),
        ],
        "bearish": [
            Pivot(index=1, price=120.0, type="H", timestamp="2026-01-01"),
            Pivot(index=2, price=105.0, type="L", timestamp="2026-01-02"),
            Pivot(index=3, price=116.0, type="H", timestamp="2026-01-03"),
            Pivot(index=4, price=108.0, type="L", timestamp="2026-01-04"),
            Pivot(index=5, price=113.0, type="H", timestamp="2026-01-05"),
        ],
    }[direction]
    return DiagonalPattern(
        pattern_type=pattern_type,
        direction=direction,
        p1=pivots[0], p2=pivots[1], p3=pivots[2], p4=pivots[3], p5=pivots[4],
        overlap_exists=overlap_exists,
        is_contracting=is_contracting,
    )


def test_ending_diagonal_bullish_valid():
    p = _make_diagonal("bullish", is_contracting=True, overlap_exists=True)
    result = validate_diagonal_rules(p)
    assert result.is_valid is True


def test_ending_diagonal_bearish_valid():
    p = _make_diagonal("bearish", is_contracting=True, overlap_exists=True)
    result = validate_diagonal_rules(p)
    assert result.is_valid is True


def test_ending_diagonal_not_contracting():
    p = _make_diagonal("bullish", is_contracting=False, overlap_exists=True)
    result = validate_diagonal_rules(p)
    assert result.is_valid is False  # must be contracting


def test_ending_diagonal_no_overlap():
    p = _make_diagonal("bullish", is_contracting=True, overlap_exists=False)
    result = validate_diagonal_rules(p)
    assert result.is_valid is False


def test_leading_diagonal_does_not_require_contracting():
    p = _make_diagonal("bullish", is_contracting=False, overlap_exists=True,
                       pattern_type="leading_diagonal")
    result = validate_diagonal_rules(p)
    assert result.is_valid is True  # leading diagonal only needs overlap


# ── validate_pattern_rules dispatch ──────────────────────────────────────────

def test_dispatch_flat():
    a = _swing(1, 100.0, "L")
    b = _swing(2, 120.0, "H")
    c = _swing(3, 102.0, "L")
    p = FlatPattern(
        pattern_type="flat", direction="bullish",
        a=a, b=b, c=c, ab_length=20.0, bc_length=18.0,
        b_vs_a_ratio=0.90, c_vs_a_ratio=0.90,
    )
    result = validate_pattern_rules("FLAT", p)
    assert result.pattern_type == "flat"


def test_dispatch_expanded_flat():
    a = _swing(1, 100.0, "L")
    b = _swing(2, 120.0, "H")
    c = _swing(3, 95.0, "L")
    p = ExpandedFlatPattern(
        pattern_type="expanded_flat", direction="bullish",
        a=a, b=b, c=c, ab_length=20.0, bc_length=25.0,
        b_extension_ratio=1.25, c_extension_ratio=1.25,
    )
    result = validate_pattern_rules("EXPANDED_FLAT", p)
    assert result.pattern_type == "expanded_flat"


def test_dispatch_unsupported():
    result = validate_pattern_rules("FOOBAR", object())
    assert result.is_valid is False
    assert result.message == "unsupported pattern"


def test_dispatch_contracting_triangle():
    p = _make_triangle("contracting", -2.0, 1.0)
    result = validate_pattern_rules("CONTRACTING_TRIANGLE", p)
    assert result.is_valid is True


def test_dispatch_expanding_triangle():
    p = _make_triangle("expanding", 2.0, -2.0)
    result = validate_pattern_rules("EXPANDING_TRIANGLE", p)
    assert result.is_valid is True


def test_dispatch_ending_diagonal():
    p = _make_diagonal("bullish", is_contracting=True, overlap_exists=True)
    result = validate_pattern_rules("ENDING_DIAGONAL", p)
    assert result.is_valid is True


def test_dispatch_leading_diagonal():
    p = _make_diagonal("bullish", is_contracting=False, overlap_exists=True,
                       pattern_type="leading_diagonal")
    result = validate_pattern_rules("LEADING_DIAGONAL", p)
    assert result.is_valid is True


def test_dispatch_ascending_barrier():
    p = _make_triangle("ascending_barrier", 0.0, 1.5)
    result = validate_pattern_rules("ASCENDING_BARRIER_TRIANGLE", p)
    assert result.is_valid is True
