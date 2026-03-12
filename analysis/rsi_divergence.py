from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from analysis.pivot_detector import Pivot


@dataclass(frozen=True)
class RSIDivergenceSignal:
    direction: str
    first_index: int
    second_index: int
    first_price: float
    second_price: float
    first_rsi: float
    second_rsi: float

    @property
    def state(self) -> str:
        return f"{self.direction.upper()}_RSI_DIVERGENCE"

    @property
    def message(self) -> str:
        if self.direction == "bullish":
            return "price made a lower low while RSI made a higher low"
        return "price made a higher high while RSI made a lower high"


def _latest_same_type_pair(
    pivots: list[Pivot],
    pivot_type: str,
) -> tuple[Pivot, Pivot] | None:
    same_type = [pivot for pivot in pivots if pivot.type == pivot_type]
    if len(same_type) < 2:
        return None
    return same_type[-2], same_type[-1]


def _rsi_at_index(df: pd.DataFrame, index: int) -> float | None:
    if "rsi" not in df.columns:
        return None
    if index < 0 or index >= len(df):
        return None

    value = df.iloc[index]["rsi"]
    if pd.isna(value):
        return None

    return float(value)


def detect_bullish_rsi_divergence(
    df: pd.DataFrame,
    pivots: list[Pivot],
) -> RSIDivergenceSignal | None:
    pair = _latest_same_type_pair(pivots, "L")
    if pair is None:
        return None

    first, second = pair
    first_rsi = _rsi_at_index(df, first.index)
    second_rsi = _rsi_at_index(df, second.index)

    if first_rsi is None or second_rsi is None:
        return None

    if second.price < first.price and second_rsi > first_rsi:
        return RSIDivergenceSignal(
            direction="bullish",
            first_index=first.index,
            second_index=second.index,
            first_price=float(first.price),
            second_price=float(second.price),
            first_rsi=first_rsi,
            second_rsi=second_rsi,
        )

    return None


def detect_bearish_rsi_divergence(
    df: pd.DataFrame,
    pivots: list[Pivot],
) -> RSIDivergenceSignal | None:
    pair = _latest_same_type_pair(pivots, "H")
    if pair is None:
        return None

    first, second = pair
    first_rsi = _rsi_at_index(df, first.index)
    second_rsi = _rsi_at_index(df, second.index)

    if first_rsi is None or second_rsi is None:
        return None

    if second.price > first.price and second_rsi < first_rsi:
        return RSIDivergenceSignal(
            direction="bearish",
            first_index=first.index,
            second_index=second.index,
            first_price=float(first.price),
            second_price=float(second.price),
            first_rsi=first_rsi,
            second_rsi=second_rsi,
        )

    return None
