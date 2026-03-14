from analysis.diagonal_detector import detect_ending_diagonal
from analysis.pivot_detector import Pivot


def test_detect_bullish_ending_diagonal():
    pivots = [
        Pivot(index=1, price=100.0, type="L", timestamp="2026-01-01"),
        Pivot(index=2, price=120.0, type="H", timestamp="2026-01-02"),
        Pivot(index=3, price=105.0, type="L", timestamp="2026-01-03"),
        Pivot(index=4, price=122.0, type="H", timestamp="2026-01-04"),
        Pivot(index=5, price=110.0, type="L", timestamp="2026-01-05"),
    ]

    pattern = detect_ending_diagonal(pivots)

    assert pattern is not None
    assert pattern.pattern_type == "ending_diagonal"
    assert pattern.direction == "bullish"


def test_detect_bearish_ending_diagonal():
    pivots = [
        Pivot(index=1, price=120.0, type="H", timestamp="2026-01-01"),
        Pivot(index=2, price=100.0, type="L", timestamp="2026-01-02"),
        Pivot(index=3, price=115.0, type="H", timestamp="2026-01-03"),
        Pivot(index=4, price=98.0, type="L", timestamp="2026-01-04"),
        Pivot(index=5, price=110.0, type="H", timestamp="2026-01-05"),
    ]

    pattern = detect_ending_diagonal(pivots)

    assert pattern is not None
    assert pattern.pattern_type == "ending_diagonal"
    assert pattern.direction == "bearish"


def test_bullish_ending_diagonal_not_contracting_skips():
    """LHLHL but w3 > w1 → not contracting → skip → None (line 46)."""
    pivots = [
        Pivot(index=1, price=100.0, type="L", timestamp="2026-01-01"),
        Pivot(index=2, price=110.0, type="H", timestamp="2026-01-02"),  # w1=10
        Pivot(index=3, price=107.0, type="L", timestamp="2026-01-03"),  # w2=3
        Pivot(index=4, price=120.0, type="H", timestamp="2026-01-04"),  # w3=13 > w1=10
        Pivot(index=5, price=115.0, type="L", timestamp="2026-01-05"),  # w4=5
    ]
    assert detect_ending_diagonal(pivots) is None


def test_bearish_ending_diagonal_not_contracting_skips():
    """HLHLH but w3 > w1 → not contracting → skip → None (line 76)."""
    pivots = [
        Pivot(index=1, price=120.0, type="H", timestamp="2026-01-01"),
        Pivot(index=2, price=110.0, type="L", timestamp="2026-01-02"),  # w1=10
        Pivot(index=3, price=113.0, type="H", timestamp="2026-01-03"),  # w2=3
        Pivot(index=4, price=100.0, type="L", timestamp="2026-01-04"),  # w3=13 > w1=10
        Pivot(index=5, price=105.0, type="H", timestamp="2026-01-05"),
    ]
    assert detect_ending_diagonal(pivots) is None


def test_ending_diagonal_too_few_returns_none():
    """Fewer than 5 pivots → return None immediately."""
    pivots = [
        Pivot(index=1, price=100.0, type="L", timestamp="2026-01-01"),
        Pivot(index=2, price=110.0, type="H", timestamp="2026-01-02"),
    ]
    assert detect_ending_diagonal(pivots) is None