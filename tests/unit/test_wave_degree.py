from analysis.pivot_detector import Pivot
from analysis.swing_builder import build_swings, SwingPoint
from analysis.wave_degree import classify_wave_degrees


def _sw(index, price, t):
    return SwingPoint(index=index, price=price, type=t, timestamp=f"2026-01-{index:02d}")


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


def test_classify_too_few_swings():
    assert classify_wave_degrees([]) == []
    assert classify_wave_degrees([_sw(1, 100.0, "L")]) == []


def test_classify_micro_degree():
    """Swing much smaller than average → micro degree."""
    swings = [
        _sw(1, 100.0, "L"),
        _sw(2, 200.0, "H"),   # size 100 (large)
        _sw(3, 150.0, "L"),   # size 50 (medium — intermediate)
        _sw(4, 155.0, "H"),   # size 5 (tiny — micro)
    ]
    degree_swings = classify_wave_degrees(swings)
    # avg size = (100 + 50 + 5) / 3 = 51.67; last swing 5 < 51.67*0.5 = 25.8 → micro
    assert degree_swings[-1].degree == "micro"


def test_classify_major_degree():
    """Swing much larger than average → major degree."""
    swings = [
        _sw(1, 100.0, "L"),
        _sw(2, 105.0, "H"),   # size 5 (small)
        _sw(3, 103.0, "L"),   # size 2 (tiny)
        _sw(4, 200.0, "H"),   # size 97 (huge — major)
    ]
    degree_swings = classify_wave_degrees(swings)
    # avg size = (5 + 2 + 97) / 3 = 34.67; last swing 97 > 34.67*2 = 69.33 → major
    assert degree_swings[-1].degree == "major"


def test_classify_zero_avg_size():
    """All swings at same price → avg_size = 0 → unknown degree."""
    swings = [_sw(1, 100.0, "L"), _sw(2, 100.0, "H"), _sw(3, 100.0, "L")]
    degree_swings = classify_wave_degrees(swings)
    assert all(d.degree == "unknown" for d in degree_swings)


def test_first_swing_has_zero_size():
    """First swing has no predecessor → swing_size = 0."""
    swings = [_sw(1, 100.0, "L"), _sw(2, 120.0, "H")]
    degree_swings = classify_wave_degrees(swings)
    assert degree_swings[0].swing_size == 0.0