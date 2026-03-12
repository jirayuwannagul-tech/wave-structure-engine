from analysis.pivot_detector import Pivot
from analysis.swing_builder import build_swings


def test_build_swings_keeps_alternating_types():
    pivots = [
        Pivot(index=1, price=10, type="H", timestamp="2026-01-01"),
        Pivot(index=2, price=8, type="L", timestamp="2026-01-02"),
        Pivot(index=3, price=12, type="H", timestamp="2026-01-03"),
        Pivot(index=4, price=9, type="L", timestamp="2026-01-04"),
    ]

    swings = build_swings(pivots)

    assert len(swings) == 4
    assert [s.type for s in swings] == ["H", "L", "H", "L"]


def test_build_swings_replaces_weaker_same_type():
    pivots = [
        Pivot(index=1, price=10, type="H", timestamp="2026-01-01"),
        Pivot(index=2, price=12, type="H", timestamp="2026-01-02"),
        Pivot(index=3, price=8, type="L", timestamp="2026-01-03"),
        Pivot(index=4, price=6, type="L", timestamp="2026-01-04"),
    ]

    swings = build_swings(pivots)

    assert len(swings) == 2
    assert swings[0].type == "H"
    assert swings[0].price == 12
    assert swings[1].type == "L"
    assert swings[1].price == 6