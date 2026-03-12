import pandas as pd

from analysis.pivot_detector import detect_pivots


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