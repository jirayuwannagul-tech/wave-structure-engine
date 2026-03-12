import pandas as pd

from analysis.pivot_detector import Pivot
from analysis.rsi_divergence import (
    detect_bearish_rsi_divergence,
    detect_bullish_rsi_divergence,
)


def test_detect_bullish_rsi_divergence():
    df = pd.DataFrame({"rsi": [50.0, 42.0, 30.0, 36.0, 38.0]})
    pivots = [
        Pivot(index=2, price=100.0, type="L", timestamp=pd.Timestamp("2026-01-01")),
        Pivot(index=4, price=95.0, type="L", timestamp=pd.Timestamp("2026-01-02")),
    ]

    signal = detect_bullish_rsi_divergence(df, pivots)

    assert signal is not None
    assert signal.state == "BULLISH_RSI_DIVERGENCE"
    assert signal.first_price == 100.0
    assert signal.second_price == 95.0
    assert signal.first_rsi == 30.0
    assert signal.second_rsi == 38.0


def test_detect_bearish_rsi_divergence():
    df = pd.DataFrame({"rsi": [45.0, 58.0, 64.0, 60.0, 55.0]})
    pivots = [
        Pivot(index=2, price=100.0, type="H", timestamp=pd.Timestamp("2026-01-01")),
        Pivot(index=4, price=105.0, type="H", timestamp=pd.Timestamp("2026-01-02")),
    ]

    signal = detect_bearish_rsi_divergence(df, pivots)

    assert signal is not None
    assert signal.state == "BEARISH_RSI_DIVERGENCE"
    assert signal.first_rsi == 64.0
    assert signal.second_rsi == 55.0


def test_detect_rsi_divergence_returns_none_when_structure_does_not_match():
    df = pd.DataFrame({"rsi": [50.0, 42.0, 30.0, 36.0, 28.0]})
    pivots = [
        Pivot(index=2, price=100.0, type="L", timestamp=pd.Timestamp("2026-01-01")),
        Pivot(index=4, price=95.0, type="L", timestamp=pd.Timestamp("2026-01-02")),
    ]

    signal = detect_bullish_rsi_divergence(df, pivots)

    assert signal is None
