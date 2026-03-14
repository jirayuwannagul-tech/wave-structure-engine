from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from analysis.pivot_detector import Pivot


@dataclass
class TrendClassification:
    state: str
    last_high: float | None
    previous_high: float | None
    last_low: float | None
    previous_low: float | None
    swing_structure: str
    source: str
    confidence: float
    message: str


def _last_two_prices(pivots: list[Pivot], pivot_type: str) -> tuple[float | None, float | None]:
    filtered = [pivot.price for pivot in pivots if pivot.type == pivot_type]
    if len(filtered) < 2:
        return None, None
    return float(filtered[-1]), float(filtered[-2])


def _fallback_from_closes(df: pd.DataFrame | None) -> TrendClassification:
    if df is None or "close" not in df.columns or len(df) < 20:
        return TrendClassification(
            state="SIDEWAY",
            last_high=None,
            previous_high=None,
            last_low=None,
            previous_low=None,
            swing_structure="UNKNOWN",
            source="fallback",
            confidence=0.2,
            message="insufficient pivot structure, defaulting to sideway",
        )

    recent = df["close"].tail(20)
    first_half = recent.head(10).mean()
    second_half = recent.tail(10).mean()

    if second_half > first_half:
        state = "UPTREND"
        message = "recent close average is rising"
    elif second_half < first_half:
        state = "DOWNTREND"
        message = "recent close average is falling"
    else:
        state = "SIDEWAY"
        message = "recent close average is flat"

    return TrendClassification(
        state=state,
        last_high=None,
        previous_high=None,
        last_low=None,
        previous_low=None,
        swing_structure="CLOSE_AVERAGE",
        source="close_average",
        confidence=0.35,
        message=message,
    )


def _apply_bos(
    state: str,
    last_high: float | None,
    last_low: float | None,
    df: pd.DataFrame | None,
) -> str:
    """Return BROKEN_UP or BROKEN_DOWN if the latest close has crossed the last swing."""
    if df is None or "close" not in df.columns or len(df) == 0:
        return state
    last_close = float(df.iloc[-1]["close"])
    if last_low is not None and last_close < last_low:
        return "BROKEN_DOWN"
    if last_high is not None and last_close > last_high:
        return "BROKEN_UP"
    return state


def classify_market_trend(
    pivots: list[Pivot],
    df: pd.DataFrame | None = None,
) -> TrendClassification:
    last_high, previous_high = _last_two_prices(pivots, "H")
    last_low, previous_low = _last_two_prices(pivots, "L")

    if None in {last_high, previous_high, last_low, previous_low}:
        return _fallback_from_closes(df)

    if last_high > previous_high and last_low > previous_low:
        state = _apply_bos("UPTREND", last_high, last_low, df)
        return TrendClassification(
            state=state,
            last_high=last_high,
            previous_high=previous_high,
            last_low=last_low,
            previous_low=previous_low,
            swing_structure="BOS_DOWN" if state == "BROKEN_DOWN" else "HH_HL",
            source="dow_theory",
            confidence=0.85 if state in {"BROKEN_UP", "BROKEN_DOWN"} else 0.8,
            message="break of structure downward" if state == "BROKEN_DOWN" else "higher highs and higher lows",
        )

    if last_high < previous_high and last_low < previous_low:
        state = _apply_bos("DOWNTREND", last_high, last_low, df)
        return TrendClassification(
            state=state,
            last_high=last_high,
            previous_high=previous_high,
            last_low=last_low,
            previous_low=previous_low,
            swing_structure="BOS_UP" if state == "BROKEN_UP" else "LH_LL",
            source="dow_theory",
            confidence=0.85 if state in {"BROKEN_UP", "BROKEN_DOWN"} else 0.8,
            message="break of structure upward" if state == "BROKEN_UP" else "lower highs and lower lows",
        )

    state = _apply_bos("SIDEWAY", last_high, last_low, df)
    swing_structure = (
        "BOS_UP" if state == "BROKEN_UP"
        else "BOS_DOWN" if state == "BROKEN_DOWN"
        else "MIXED_SWINGS"
    )
    return TrendClassification(
        state=state,
        last_high=last_high,
        previous_high=previous_high,
        last_low=last_low,
        previous_low=previous_low,
        swing_structure=swing_structure,
        source="dow_theory",
        confidence=0.85 if state in {"BROKEN_UP", "BROKEN_DOWN"} else 0.65,
        message=(
            "break of structure upward" if state == "BROKEN_UP"
            else "break of structure downward" if state == "BROKEN_DOWN"
            else "pivot highs and lows are mixed"
        ),
    )


def dow_theory_alignment_adjustment(direction: str, trend: TrendClassification) -> float:
    direction = (direction or "").lower()

    if direction not in {"bullish", "bearish"}:
        return 0.0

    if trend.state in {"UPTREND", "BROKEN_UP"}:
        return 0.003 if direction == "bullish" else 0.0

    if trend.state in {"DOWNTREND", "BROKEN_DOWN"}:
        return 0.003 if direction == "bearish" else 0.0

    return 0.0
