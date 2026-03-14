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


def _uptrend_pivots():
    return [
        Pivot(index=1, price=100.0, type="L", timestamp=pd.Timestamp("2026-01-01")),
        Pivot(index=2, price=120.0, type="H", timestamp=pd.Timestamp("2026-01-02")),
        Pivot(index=3, price=108.0, type="L", timestamp=pd.Timestamp("2026-01-03")),
        Pivot(index=4, price=130.0, type="H", timestamp=pd.Timestamp("2026-01-04")),
    ]


def _downtrend_pivots():
    return [
        Pivot(index=1, price=130.0, type="H", timestamp=pd.Timestamp("2026-01-01")),
        Pivot(index=2, price=110.0, type="L", timestamp=pd.Timestamp("2026-01-02")),
        Pivot(index=3, price=122.0, type="H", timestamp=pd.Timestamp("2026-01-03")),
        Pivot(index=4, price=100.0, type="L", timestamp=pd.Timestamp("2026-01-04")),
    ]


def test_classify_market_trend_bos_down_when_uptrend_breaks_below_last_low():
    # Uptrend pivots: last_low=108, last_high=130; close=105 < 108 → BROKEN_DOWN
    df = pd.DataFrame({"close": [90, 100, 115, 125, 105]})
    result = classify_market_trend(_uptrend_pivots(), df=df)

    assert result.state == "BROKEN_DOWN"
    assert result.swing_structure == "BOS_DOWN"
    assert result.source == "dow_theory"
    assert result.confidence == 0.85


def test_classify_market_trend_bos_up_when_downtrend_breaks_above_last_high():
    # Downtrend pivots: last_high=122, last_low=100; close=125 > 122 → BROKEN_UP
    df = pd.DataFrame({"close": [130, 115, 120, 105, 125]})
    result = classify_market_trend(_downtrend_pivots(), df=df)

    assert result.state == "BROKEN_UP"
    assert result.swing_structure == "BOS_UP"
    assert result.source == "dow_theory"
    assert result.confidence == 0.85


def test_classify_market_trend_no_bos_when_price_inside_range():
    # Uptrend pivots: last_low=108, last_high=130; close=115 → still UPTREND
    df = pd.DataFrame({"close": [90, 100, 115, 125, 115]})
    result = classify_market_trend(_uptrend_pivots(), df=df)

    assert result.state == "UPTREND"


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
