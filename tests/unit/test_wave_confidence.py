from analysis.wave_confidence import (
    clamp_score,
    score_rule_validation_from_bool,
    score_structure_quality,
    score_fib_ratio,
    score_abc_fibonacci,
    score_impulse_fibonacci,
    score_flat_fibonacci,
    score_expanded_flat_fibonacci,
    score_running_flat_fibonacci,
    score_wxy_fibonacci,
    score_diagonal_quality,
    score_triangle_quality,
    score_momentum_from_lengths,
    score_alternation,
    score_fib_confluence,
    compute_wave_confidence,
)


# ── clamp_score ──────────────────────────────────────────────────────────────

def test_clamp_below_zero():
    assert clamp_score(-0.5) == 0.0


def test_clamp_above_one():
    assert clamp_score(1.5) == 1.0


def test_clamp_in_range():
    assert clamp_score(0.7) == 0.7


# ── score_rule_validation_from_bool ──────────────────────────────────────────

def test_rule_valid():
    assert score_rule_validation_from_bool(True) == 1.0


def test_rule_invalid():
    assert score_rule_validation_from_bool(False) == 0.0


# ── score_structure_quality ──────────────────────────────────────────────────

def test_structure_impulse():
    assert score_structure_quality("IMPULSE") == 1.0


def test_structure_abc():
    assert score_structure_quality("ABC_CORRECTION") == 0.62


def test_structure_expanded_flat():
    assert score_structure_quality("EXPANDED_FLAT") == 0.58


def test_structure_running_flat():
    assert score_structure_quality("RUNNING_FLAT") == 0.56


def test_structure_flat():
    assert score_structure_quality("FLAT") == 0.54


def test_structure_wxy():
    assert score_structure_quality("WXY") == 0.55


def test_structure_contracting_triangle():
    assert score_structure_quality("CONTRACTING_TRIANGLE") == 0.52
    assert score_structure_quality("TRIANGLE") == 0.52


def test_structure_expanding_triangle():
    assert score_structure_quality("EXPANDING_TRIANGLE") == 0.50


def test_structure_barrier_triangles():
    assert score_structure_quality("ASCENDING_BARRIER_TRIANGLE") == 0.54
    assert score_structure_quality("DESCENDING_BARRIER_TRIANGLE") == 0.54


def test_structure_diagonals():
    assert score_structure_quality("ENDING_DIAGONAL") == 0.72
    assert score_structure_quality("LEADING_DIAGONAL") == 0.72


def test_structure_unknown():
    assert score_structure_quality("UNKNOWN") == 0.50


# ── score_fib_ratio ──────────────────────────────────────────────────────────

def test_fib_ratio_exact_match():
    assert score_fib_ratio(0.618, [0.5, 0.618, 0.786]) == 1.0


def test_fib_ratio_close_match():
    score = score_fib_ratio(0.63, [0.618], tolerance=0.12)
    assert score >= 0.8


def test_fib_ratio_far_from_target():
    score = score_fib_ratio(0.9, [0.236, 0.382], tolerance=0.12)
    assert score <= 0.60


def test_fib_ratio_none():
    assert score_fib_ratio(None, [0.618]) == 0.50


# ── pattern Fibonacci scorers ─────────────────────────────────────────────────

class _FakePattern:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_score_abc_fibonacci_valid():
    p = _FakePattern(bc_vs_ab_ratio=0.618)
    assert score_abc_fibonacci(p) >= 0.8


def test_score_impulse_fibonacci_extended_w3():
    p = _FakePattern(
        wave2_retrace_ratio=0.618,
        wave4_retrace_ratio=0.382,
        wave3_vs_wave1_ratio=1.618,
        wave5_vs_wave1_ratio=1.0,
        is_wave3_extended=True,
        wave5_truncated=False,
    )
    score = score_impulse_fibonacci(p)
    assert score > 0.6


def test_score_impulse_fibonacci_truncated_w5():
    p = _FakePattern(
        wave2_retrace_ratio=0.618,
        wave4_retrace_ratio=0.382,
        wave3_vs_wave1_ratio=1.618,
        wave5_vs_wave1_ratio=1.0,
        is_wave3_extended=False,
        wave5_truncated=True,
    )
    score_ext = score_impulse_fibonacci(_FakePattern(
        wave2_retrace_ratio=0.618,
        wave4_retrace_ratio=0.382,
        wave3_vs_wave1_ratio=1.618,
        wave5_vs_wave1_ratio=1.0,
        is_wave3_extended=False,
        wave5_truncated=False,
    ))
    score_trunc = score_impulse_fibonacci(p)
    assert score_trunc < score_ext


def test_score_flat_fibonacci():
    p = _FakePattern(c_vs_a_ratio=0.786)
    assert score_flat_fibonacci(p) >= 0.8


def test_score_expanded_flat_fibonacci():
    p = _FakePattern(c_extension_ratio=1.618)
    assert score_expanded_flat_fibonacci(p) >= 0.6


def test_score_running_flat_fibonacci():
    p = _FakePattern(c_vs_a_ratio=0.618)
    assert score_running_flat_fibonacci(p) >= 0.8


def test_score_wxy_fibonacci():
    p = _FakePattern(y_vs_w_ratio=0.786)
    assert score_wxy_fibonacci(p) >= 0.8


# ── score_diagonal_quality ────────────────────────────────────────────────────

def test_diagonal_with_overlap_and_contracting():
    p = _FakePattern(overlap_exists=True, is_contracting=True, w3_vs_w1_ratio=0.75)
    score = score_diagonal_quality(p)
    assert score >= 0.90


def test_diagonal_no_overlap():
    p = _FakePattern(overlap_exists=False, is_contracting=False, w3_vs_w1_ratio=0.0)
    score = score_diagonal_quality(p)
    assert score == 0.60


def test_diagonal_fib_bonus():
    p_good = _FakePattern(overlap_exists=True, is_contracting=False, w3_vs_w1_ratio=0.75)
    p_bad = _FakePattern(overlap_exists=True, is_contracting=False, w3_vs_w1_ratio=2.0)
    assert score_diagonal_quality(p_good) > score_diagonal_quality(p_bad)


# ── score_triangle_quality ────────────────────────────────────────────────────

def test_triangle_contracting():
    p = _FakePattern(triangle_subtype="contracting", upper_slope=2.0, lower_slope=1.0)
    assert score_triangle_quality(p) == 0.80


def test_triangle_expanding():
    p = _FakePattern(triangle_subtype="expanding", upper_slope=2.0, lower_slope=1.0)
    assert score_triangle_quality(p) == 0.75


def test_triangle_ascending_barrier():
    p = _FakePattern(triangle_subtype="ascending_barrier", upper_slope=0.0, lower_slope=1.5)
    assert score_triangle_quality(p) == 0.82


def test_triangle_descending_barrier():
    p = _FakePattern(triangle_subtype="descending_barrier", upper_slope=1.5, lower_slope=0.0)
    assert score_triangle_quality(p) == 0.82


def test_triangle_unknown_subtype():
    p = _FakePattern(triangle_subtype="unknown", upper_slope=1.0, lower_slope=1.0)
    assert score_triangle_quality(p) == 0.60


# ── score_momentum_from_lengths ───────────────────────────────────────────────

def test_momentum_accelerating():
    # latest > 1.3× avg
    score = score_momentum_from_lengths([10, 10, 15, 20])
    assert score >= 0.85


def test_momentum_normal():
    score = score_momentum_from_lengths([10, 12, 11, 12])
    assert 0.55 <= score <= 0.85


def test_momentum_decelerating():
    score = score_momentum_from_lengths([20, 15, 10, 5])
    assert score <= 0.55


def test_momentum_too_few_lengths():
    assert score_momentum_from_lengths([10]) == 0.50
    assert score_momentum_from_lengths([]) == 0.50


# ── score_alternation ────────────────────────────────────────────────────────

def test_alternation_clear_w2_sharp_w4_flat():
    p = _FakePattern(wave2_retrace_ratio=0.70, wave4_retrace_ratio=0.30)
    assert score_alternation(p) == 0.03


def test_alternation_clear_w2_flat_w4_sharp():
    p = _FakePattern(wave2_retrace_ratio=0.30, wave4_retrace_ratio=0.72)
    assert score_alternation(p) == 0.03


def test_alternation_poor_both_sharp():
    p = _FakePattern(wave2_retrace_ratio=0.72, wave4_retrace_ratio=0.70)
    assert score_alternation(p) == -0.03


def test_alternation_poor_both_flat():
    p = _FakePattern(wave2_retrace_ratio=0.30, wave4_retrace_ratio=0.28)
    assert score_alternation(p) == -0.03


def test_alternation_indeterminate():
    p = _FakePattern(wave2_retrace_ratio=0.50, wave4_retrace_ratio=0.45)
    assert score_alternation(p) == 0.0


def test_alternation_missing_ratios():
    p = _FakePattern()
    assert score_alternation(p) == 0.0


# ── score_fib_confluence ──────────────────────────────────────────────────────

def test_fib_confluence_three_levels():
    targets = {"0.618": 100.5, "0.786": 100.8, "1.0": 99.8}
    score = score_fib_confluence(100.0, targets, tolerance_pct=0.015)
    assert score == 0.05


def test_fib_confluence_two_levels():
    targets = {"0.618": 100.5, "1.618": 120.0}
    score = score_fib_confluence(100.0, targets, tolerance_pct=0.015)
    assert score == 0.01


def test_fib_confluence_zero_levels():
    targets = {"0.618": 120.0, "1.618": 150.0}
    score = score_fib_confluence(100.0, targets, tolerance_pct=0.005)
    assert score == 0.0


def test_fib_confluence_none_entry():
    assert score_fib_confluence(None, {"a": 100.0}) == 0.0


def test_fib_confluence_empty_targets():
    assert score_fib_confluence(100.0, {}) == 0.0


# ── compute_wave_confidence ───────────────────────────────────────────────────

def test_wave_confidence_range():
    score = compute_wave_confidence(
        rule_score=1, fib_score=0.8, structure_score=1, momentum_score=0.7
    )
    assert 0 <= score <= 1


def test_wave_confidence_high_score():
    score = compute_wave_confidence(
        rule_score=1, fib_score=1, structure_score=1, momentum_score=1
    )
    assert score >= 0.9


def test_wave_confidence_with_good_alternation():
    p = _FakePattern(wave2_retrace_ratio=0.70, wave4_retrace_ratio=0.30)
    score_with = compute_wave_confidence(1, 0.8, 1, 0.8, pattern=p, pattern_type="IMPULSE")
    score_without = compute_wave_confidence(1, 0.8, 1, 0.8)
    assert score_with > score_without


def test_wave_confidence_with_poor_alternation():
    p = _FakePattern(wave2_retrace_ratio=0.72, wave4_retrace_ratio=0.70)
    score_poor = compute_wave_confidence(1, 0.8, 1, 0.8, pattern=p, pattern_type="IMPULSE")
    score_base = compute_wave_confidence(1, 0.8, 1, 0.8)
    assert score_poor < score_base


def test_wave_confidence_non_impulse_ignores_alternation():
    p = _FakePattern(wave2_retrace_ratio=0.70, wave4_retrace_ratio=0.30)
    score_abc = compute_wave_confidence(1, 0.8, 1, 0.8, pattern=p, pattern_type="ABC_CORRECTION")
    score_base = compute_wave_confidence(1, 0.8, 1, 0.8)
    assert score_abc == score_base


def test_fib_ratio_medium_match():
    """best_diff > tolerance but <= tolerance*2 → return 0.6 (line 52)."""
    # ratio=0.75, target=0.618: diff=0.132. tolerance=0.12 → 0.12 < 0.132 <= 0.24
    assert score_fib_ratio(0.75, [0.618], tolerance=0.12) == 0.6


def test_fib_confluence_exactly_two_levels():
    """Exactly 2 targets near entry → return 0.03 (line 207)."""
    targets = {"a": 100.3, "b": 100.5, "c": 200.0}
    score = score_fib_confluence(100.0, targets, tolerance_pct=0.015)
    assert score == 0.03
