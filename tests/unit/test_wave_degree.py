from analysis.pivot_detector import Pivot
from analysis.swing_builder import build_swings
from analysis.wave_degree import classify_wave_degrees


def test_classify_wave_degrees_returns_degrees():
    pivots = [
        Pivot(index=1, price=60000, type="L", timestamp="2026-01-01"),
        Pivot(index=2, price=65000, type="H", timestamp="2026-01-02"),
        Pivot(index=3, price=63000, type="L", timestamp="2026-01-03"),
        Pivot(index=4, price=70000, type="H", timestamp="2026-01-04"),
    ]

    swings = build_swings(pivots)
    degree_swings = classify_wave_degrees(swings)

    assert len(degree_swings) >= 1

    for swing in degree_swings:
        assert swing.degree in ["unknown", "micro", "minor", "intermediate", "major"]
        assert swing.price > 0
        assert swing.index >= 0