import pandas as pd

from analysis.inprogress_detector import InProgressWave
from analysis.pivot_detector import Pivot
from analysis.wave_sequence_engine import build_wave_sequence


def test_build_wave_sequence_detects_bullish_impulse_left_to_right():
    pivots = [
        Pivot(index=0, price=100.0, type="L", timestamp=pd.Timestamp("2026-01-01")),
        Pivot(index=1, price=120.0, type="H", timestamp=pd.Timestamp("2026-01-02")),
        Pivot(index=2, price=108.0, type="L", timestamp=pd.Timestamp("2026-01-03")),
        Pivot(index=3, price=142.0, type="H", timestamp=pd.Timestamp("2026-01-04")),
        Pivot(index=4, price=126.0, type="L", timestamp=pd.Timestamp("2026-01-05")),
        Pivot(index=5, price=160.0, type="H", timestamp=pd.Timestamp("2026-01-06")),
    ]

    sequence = build_wave_sequence(pivots)

    assert [leg["label"] for leg in sequence["completed_legs"]] == ["1", "2", "3", "4", "5"]
    assert sequence["patterns"][0]["structure"] == "IMPULSE"
    assert sequence["last_completed_leg"]["label"] == "5"


def test_build_wave_sequence_detects_anchored_bearish_abc():
    pivots = [
        Pivot(index=10, price=160.0, type="H", timestamp=pd.Timestamp("2026-02-01")),
        Pivot(index=11, price=145.0, type="L", timestamp=pd.Timestamp("2026-02-02")),
        Pivot(index=12, price=152.0, type="H", timestamp=pd.Timestamp("2026-02-03")),
        Pivot(index=13, price=138.0, type="L", timestamp=pd.Timestamp("2026-02-04")),
    ]

    sequence = build_wave_sequence(pivots)

    assert [leg["label"] for leg in sequence["completed_legs"]] == ["A", "B", "C"]
    assert sequence["patterns"][0]["structure"] == "ABC_CORRECTION"
    assert sequence["patterns"][0]["direction"] == "bearish"


def test_build_wave_sequence_exposes_current_leg_from_inprogress_wave():
    pivots = [
        Pivot(index=0, price=100.0, type="L", timestamp=pd.Timestamp("2026-01-01")),
        Pivot(index=1, price=120.0, type="H", timestamp=pd.Timestamp("2026-01-02")),
        Pivot(index=2, price=108.0, type="L", timestamp=pd.Timestamp("2026-01-03")),
    ]
    inprogress = InProgressWave(
        structure="IMPULSE",
        direction="bullish",
        wave_number="3",
        completed_waves=2,
        pivots=pivots,
        last_pivot=pivots[-1],
        current_wave_start=108.0,
        invalidation=100.0,
        is_valid=True,
        confidence=0.81,
    )

    sequence = build_wave_sequence(pivots, inprogress=inprogress)

    assert sequence["current_leg"]["label"] == "3"
    assert sequence["current_leg"]["structure"] == "IMPULSE"
    assert sequence["current_leg"]["position"] == "IN_WAVE_3"


def test_build_wave_sequence_detects_anchored_bullish_abc():
    """[L,H,L,H] sequence → bullish ABC correction (lines 116-142)."""
    pivots = [
        Pivot(index=0, price=100.0, type="L", timestamp=pd.Timestamp("2026-03-01")),
        Pivot(index=1, price=120.0, type="H", timestamp=pd.Timestamp("2026-03-02")),
        Pivot(index=2, price=108.0, type="L", timestamp=pd.Timestamp("2026-03-03")),  # above start
        Pivot(index=3, price=130.0, type="H", timestamp=pd.Timestamp("2026-03-04")),  # above prev H
    ]

    sequence = build_wave_sequence(pivots)

    assert [leg["label"] for leg in sequence["completed_legs"]] == ["A", "B", "C"]
    assert sequence["patterns"][0]["structure"] == "ABC_CORRECTION"
    assert sequence["patterns"][0]["direction"] == "bullish"


def test_build_wave_sequence_no_impulse_match():
    """Window that fails impulse detection → line 47 (return None)."""
    # Use fewer than 6 pivots with invalid prices so impulse detector returns None
    pivots = [
        Pivot(index=0, price=100.0, type="L", timestamp=pd.Timestamp("2026-04-01")),
        Pivot(index=1, price=90.0, type="H", timestamp=pd.Timestamp("2026-04-02")),  # H < L → invalid
        Pivot(index=2, price=85.0, type="L", timestamp=pd.Timestamp("2026-04-03")),
        Pivot(index=3, price=80.0, type="H", timestamp=pd.Timestamp("2026-04-04")),
        Pivot(index=4, price=75.0, type="L", timestamp=pd.Timestamp("2026-04-05")),
        Pivot(index=5, price=70.0, type="H", timestamp=pd.Timestamp("2026-04-06")),
    ]

    sequence = build_wave_sequence(pivots)
    # No valid pattern should be detected from this malformed sequence
    assert sequence is not None  # always returns a dict
    assert sequence.get("pattern_count", 0) == 0
