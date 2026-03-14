from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from analysis.pivot_detector import Pivot


@dataclass(frozen=True)
class MACDDivergenceSignal:
    direction: str
    first_index: int
    second_index: int
    first_price: float
    second_price: float
    first_macd: float
    second_macd: float

    @property
    def state(self) -> str:
        return f"{self.direction.upper()}_MACD_DIVERGENCE"

    @property
    def message(self) -> str:
        if self.direction == "bullish":
            return "price made a lower low while MACD made a higher low"
        return "price made a higher high while MACD made a lower high"


def _latest_same_type_pair(
    pivots: list[Pivot],
    pivot_type: str,
) -> tuple[Pivot, Pivot] | None:
    same_type = [pivot for pivot in pivots if pivot.type == pivot_type]
    if len(same_type) < 2:
        return None
    return same_type[-2], same_type[-1]


def _macd_at_index(df: pd.DataFrame, index: int) -> float | None:
    if "macd" not in df.columns:
        return None
    if index < 0 or index >= len(df):
        return None

    value = df.iloc[index]["macd"]
    if pd.isna(value):
        return None

    return float(value)


def detect_bullish_macd_divergence(
    df: pd.DataFrame,
    pivots: list[Pivot],
) -> MACDDivergenceSignal | None:
    """Bullish divergence: price lower low, MACD higher low — momentum turning up."""
    pair = _latest_same_type_pair(pivots, "L")
    if pair is None:
        return None

    first, second = pair
    first_macd = _macd_at_index(df, first.index)
    second_macd = _macd_at_index(df, second.index)

    if first_macd is None or second_macd is None:
        return None

    if second.price < first.price and second_macd > first_macd:
        return MACDDivergenceSignal(
            direction="bullish",
            first_index=first.index,
            second_index=second.index,
            first_price=float(first.price),
            second_price=float(second.price),
            first_macd=first_macd,
            second_macd=second_macd,
        )

    return None


def detect_bearish_macd_divergence(
    df: pd.DataFrame,
    pivots: list[Pivot],
) -> MACDDivergenceSignal | None:
    """Bearish divergence: price higher high, MACD lower high — momentum fading."""
    pair = _latest_same_type_pair(pivots, "H")
    if pair is None:
        return None

    first, second = pair
    first_macd = _macd_at_index(df, first.index)
    second_macd = _macd_at_index(df, second.index)

    if first_macd is None or second_macd is None:
        return None

    if second.price > first.price and second_macd < first_macd:
        return MACDDivergenceSignal(
            direction="bearish",
            first_index=first.index,
            second_index=second.index,
            first_price=float(first.price),
            second_price=float(second.price),
            first_macd=first_macd,
            second_macd=second_macd,
        )

    return None
