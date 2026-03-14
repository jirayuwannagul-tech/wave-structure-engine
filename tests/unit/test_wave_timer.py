from analysis.wave_timer import (
    WaveDuration,
    WaveTimeProjection,
    measure_impulse_wave_durations,
    project_wave_time,
    score_time_confidence,
)
from analysis.pivot_detector import Pivot


def _make_pivot(index, price, ptype):
    return Pivot(index=index, price=price, type=ptype, timestamp=f"2026-01-{index:02d}T00:00:00")


def test_measure_wave_durations_bullish():
    pivots = [
        _make_pivot(1,  100.0, "L"),
        _make_pivot(5,  120.0, "H"),
        _make_pivot(8,  110.0, "L"),
        _make_pivot(15, 140.0, "H"),
        _make_pivot(18, 130.0, "L"),
        _make_pivot(25, 160.0, "H"),
    ]
    durations = measure_impulse_wave_durations(pivots)
    assert len(durations) == 5
    assert durations[0].wave_number == "1"
    assert durations[0].bars == 4   # index 5 - 1 = 4


def test_project_wave_time_wave3():
    durations = [
        WaveDuration("1", bars=10, start_index=0, end_index=10, start_price=100, end_price=120),
        WaveDuration("2", bars=4,  start_index=10, end_index=14, start_price=120, end_price=112),
    ]
    proj = project_wave_time(durations, "3", current_bar_index=20, wave_start_index=14)
    assert proj is not None
    assert proj.building_wave == "3"
    assert proj.elapsed_bars == 6
    assert proj.expected_max_bars > proj.expected_min_bars


def test_score_time_confidence_overdue():
    durations = [
        WaveDuration("1", bars=10, start_index=0, end_index=10, start_price=100, end_price=120),
    ]
    proj = project_wave_time(durations, "2", current_bar_index=30, wave_start_index=10)
    assert proj is not None
    assert proj.is_overdue  # elapsed=20, max = 10*0.618=6.18, so overdue
    score = score_time_confidence(proj)
    assert score < 0


def test_score_time_confidence_fresh():
    durations = [
        WaveDuration("1", bars=20, start_index=0, end_index=20, start_price=100, end_price=120),
    ]
    proj = project_wave_time(durations, "2", current_bar_index=22, wave_start_index=20)
    assert proj is not None
    # elapsed = 2, expected_min = 20*0.236=4, max = 20*0.618=12 → progress = 2/12 = 0.17 < 0.382
    score = score_time_confidence(proj)
    assert score >= 0  # fresh entry bonus


def test_score_time_none_returns_zero():
    assert score_time_confidence(None) == 0.0


# ── measure_impulse_wave_durations edge cases ─────────────────────────────────

def test_measure_wave_durations_too_few_pivots():
    """Fewer than 2 pivots → return [] (line 69)."""
    assert measure_impulse_wave_durations([_make_pivot(1, 100.0, "L")]) == []


# ── project_wave_time edge cases ─────────────────────────────────────────────

def test_project_wave_time_unknown_wave_returns_none():
    """Unknown building_wave → ratios=None → return None (line 108)."""
    durations = [WaveDuration("1", bars=10, start_index=0, end_index=10,
                              start_price=100, end_price=120)]
    assert project_wave_time(durations, "X", 20, 10) is None


def test_project_wave_time_empty_durations_returns_none():
    """Empty completed_durations → return None (line 108)."""
    assert project_wave_time([], "2", 20, 10) is None


def test_project_wave_time_ref_not_found_returns_none():
    """Ref wave not in durations → ref_duration=None → return None (line 118)."""
    durations = [WaveDuration("2", bars=5, start_index=10, end_index=15,
                              start_price=120, end_price=112)]
    # building_wave="3" needs ref "1", but "1" not in durations
    assert project_wave_time(durations, "3", 20, 15) is None


def test_project_wave_time_ref_zero_bars_returns_none():
    """Ref wave has bars=0 → return None (line 118)."""
    durations = [WaveDuration("1", bars=0, start_index=0, end_index=0,
                              start_price=100, end_price=100)]
    assert project_wave_time(durations, "2", 5, 0) is None


# ── score_time_confidence branches (lines 159, 161, 164) ─────────────────────

def _proj(p_pct: float) -> WaveTimeProjection:
    max_bars = 100
    return WaveTimeProjection(
        building_wave="2",
        expected_min_bars=30,
        expected_max_bars=max_bars,
        elapsed_bars=round(p_pct * max_bars),
        is_overdue=p_pct > 1.0,
        progress_pct=p_pct,
    )


def test_score_time_confidence_slightly_overdue():
    """p = 1.2 → line 159 → -0.02."""
    assert score_time_confidence(_proj(1.2)) == -0.02


def test_score_time_confidence_healthy_midpoint():
    """p = 0.5 (within 0.382-0.786) → line 161 → +0.02."""
    assert score_time_confidence(_proj(0.5)) == 0.02


def test_score_time_confidence_near_end_neutral():
    """p = 0.9 (>0.786 but <=1.0) → line 164 → 0.0."""
    assert score_time_confidence(_proj(0.9)) == 0.0
