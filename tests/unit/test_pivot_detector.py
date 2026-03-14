import pandas as pd

from analysis.pivot_detector import detect_pivots, mark_broken_pivots, Pivot


def test_detect_pivots_finds_high_and_low():
    df = pd.DataFrame(
        {
            "open_time": pd.date_range("2026-01-01", periods=7, freq="D", tz="UTC"),
            "high": [10, 12, 15, 11, 10, 14, 13],
            "low": [7, 6, 5, 8, 9, 4, 6],
        }
    )

    pivots = detect_pivots(df, left=1, right=1)

    assert len(pivots) >= 2
    assert any(p.type == "H" and p.price == 15 for p in pivots)
    assert any(p.type == "L" and p.price == 5 for p in pivots)


def test_detect_pivots_returns_empty_for_small_data():
    df = pd.DataFrame(
        {
            "open_time": pd.date_range("2026-01-01", periods=2, freq="D", tz="UTC"),
            "high": [10, 11],
            "low": [8, 7],
        }
    )

    pivots = detect_pivots(df, left=2, right=2)

    assert pivots == []


def _make_close_df(closes):
    return pd.DataFrame({"close": closes})


def test_mark_broken_pivots_high_broken():
    """A swing high is broken when a later close exceeds its price."""
    pivot = Pivot(index=2, price=100.0, type="H", timestamp="2026-01-03")
    df = _make_close_df([90, 95, 100, 95, 105])  # index 4 close > 100
    result = mark_broken_pivots([pivot], df)
    assert result[0].broken is True


def test_mark_broken_pivots_high_not_broken():
    """Swing high is not broken when all later closes stay below."""
    pivot = Pivot(index=2, price=100.0, type="H", timestamp="2026-01-03")
    df = _make_close_df([90, 95, 100, 95, 98])
    result = mark_broken_pivots([pivot], df)
    assert result[0].broken is False


def test_mark_broken_pivots_low_broken():
    """A swing low is broken when a later close falls below its price."""
    pivot = Pivot(index=2, price=50.0, type="L", timestamp="2026-01-03")
    df = _make_close_df([60, 55, 50, 55, 45])  # index 4 close < 50
    result = mark_broken_pivots([pivot], df)
    assert result[0].broken is True


def test_mark_broken_pivots_low_not_broken():
    """Swing low is not broken when all later closes stay above."""
    pivot = Pivot(index=2, price=50.0, type="L", timestamp="2026-01-03")
    df = _make_close_df([60, 55, 50, 55, 52])
    result = mark_broken_pivots([pivot], df)
    assert result[0].broken is False


def test_mark_broken_pivots_last_pivot_not_broken():
    """Pivot at last position has no subsequent candles, so never broken."""
    pivot = Pivot(index=4, price=100.0, type="H", timestamp="2026-01-05")
    df = _make_close_df([90, 95, 100, 95, 100])
    result = mark_broken_pivots([pivot], df)
    assert result[0].broken is False


def test_mark_broken_pivots_returns_same_list():
    pivot = Pivot(index=1, price=80.0, type="L", timestamp="2026-01-02")
    df = _make_close_df([90, 80, 85])
    result = mark_broken_pivots([pivot], df)
    assert result is not None
    assert len(result) == 1