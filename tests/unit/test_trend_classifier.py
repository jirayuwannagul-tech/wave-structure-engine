import pandas as pd

from analysis.pivot_detector import Pivot
from analysis.trend_classifier import classify_market_trend, dow_theory_alignment_adjustment


def test_classify_market_trend_uptrend():
    pivots = [
        Pivot(index=1, price=100.0, type="L", timestamp=pd.Timestamp("2026-01-01")),
        Pivot(index=2, price=120.0, type="H", timestamp=pd.Timestamp("2026-01-02")),
        Pivot(index=3, price=108.0, type="L", timestamp=pd.Timestamp("2026-01-03")),
        Pivot(index=4, price=130.0, type="H", timestamp=pd.Timestamp("2026-01-04")),
    ]

    result = classify_market_trend(pivots)

    assert result.state == "UPTREND"
    assert result.swing_structure == "HH_HL"
    assert result.source == "dow_theory"
    assert result.message == "higher highs and higher lows"


def test_classify_market_trend_downtrend():
    pivots = [
        Pivot(index=1, price=130.0, type="H", timestamp=pd.Timestamp("2026-01-01")),
        Pivot(index=2, price=110.0, type="L", timestamp=pd.Timestamp("2026-01-02")),
        Pivot(index=3, price=122.0, type="H", timestamp=pd.Timestamp("2026-01-03")),
        Pivot(index=4, price=100.0, type="L", timestamp=pd.Timestamp("2026-01-04")),
    ]

    result = classify_market_trend(pivots)

    assert result.state == "DOWNTREND"
    assert result.swing_structure == "LH_LL"
    assert result.source == "dow_theory"
    assert result.message == "lower highs and lower lows"


def test_classify_market_trend_sideway_when_structure_is_mixed():
    pivots = [
        Pivot(index=1, price=100.0, type="L", timestamp=pd.Timestamp("2026-01-01")),
        Pivot(index=2, price=120.0, type="H", timestamp=pd.Timestamp("2026-01-02")),
        Pivot(index=3, price=98.0, type="L", timestamp=pd.Timestamp("2026-01-03")),
        Pivot(index=4, price=125.0, type="H", timestamp=pd.Timestamp("2026-01-04")),
    ]

    result = classify_market_trend(pivots)

    assert result.state == "SIDEWAY"
    assert result.swing_structure == "MIXED_SWINGS"
    assert result.source == "dow_theory"
    assert result.message == "pivot highs and lows are mixed"


def test_classify_market_trend_falls_back_to_recent_close_average():
    df = pd.DataFrame({"close": list(range(1, 25))})

    result = classify_market_trend([], df=df)

    assert result.state == "UPTREND"
    assert result.source == "close_average"
    assert result.message == "recent close average is rising"


def test_dow_theory_alignment_adjustment_rewards_aligned_direction():
    pivots = [
        Pivot(index=1, price=100.0, type="L", timestamp=pd.Timestamp("2026-01-01")),
        Pivot(index=2, price=120.0, type="H", timestamp=pd.Timestamp("2026-01-02")),
        Pivot(index=3, price=108.0, type="L", timestamp=pd.Timestamp("2026-01-03")),
        Pivot(index=4, price=130.0, type="H", timestamp=pd.Timestamp("2026-01-04")),
    ]
    trend = classify_market_trend(pivots)

    assert dow_theory_alignment_adjustment("bullish", trend) > 0
    assert dow_theory_alignment_adjustment("bearish", trend) == 0.0
