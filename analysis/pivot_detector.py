from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import pandas as pd


@dataclass
class Pivot:
    index: int
    price: float
    type: str
    timestamp: pd.Timestamp
    broken: bool = field(default=False)
    confirmed: bool = field(default=True)


def mark_broken_pivots(pivots: List[Pivot], df: pd.DataFrame) -> List[Pivot]:
    """Mark each pivot as broken when price has crossed it since it formed.

    A swing high is broken when a later close exceeds its price.
    A swing low is broken when a later close falls below its price.
    """
    closes = df["close"].values
    for pivot in pivots:
        if pivot.type == "H":
            pivot.broken = any(
                closes[j] > pivot.price for j in range(pivot.index + 1, len(closes))
            )
        else:
            pivot.broken = any(
                closes[j] < pivot.price for j in range(pivot.index + 1, len(closes))
            )
    return pivots


def detect_pivots(
    df: pd.DataFrame,
    left: int = 3,
    right: int = 3,
    min_swing_atr_mult: float = 0.0,
) -> List[Pivot]:
    pivots: List[Pivot] = []

    highs = df["high"].values
    lows = df["low"].values
    atr_vals = df["atr"].values if "atr" in df.columns else None

    for i in range(left, len(df) - right):
        is_pivot_high = True
        is_pivot_low = True

        for j in range(1, left + 1):
            if highs[i] <= highs[i - j]:
                is_pivot_high = False
            if lows[i] >= lows[i - j]:
                is_pivot_low = False

        for j in range(1, right + 1):
            if highs[i] <= highs[i + j]:
                is_pivot_high = False
            if lows[i] >= lows[i + j]:
                is_pivot_low = False

        # ATR-based minimum swing size filter
        if min_swing_atr_mult > 0.0 and atr_vals is not None:
            atr_val = float(atr_vals[i]) if atr_vals[i] > 0 else 0.0
            if atr_val > 0:
                if is_pivot_high:
                    left_low = min(lows[i - j] for j in range(1, left + 1))
                    if (highs[i] - left_low) < atr_val * min_swing_atr_mult:
                        is_pivot_high = False
                if is_pivot_low:
                    left_high = max(highs[i - j] for j in range(1, left + 1))
                    if (left_high - lows[i]) < atr_val * min_swing_atr_mult:
                        is_pivot_low = False

        if is_pivot_high:
            pivots.append(Pivot(
                index=i,
                price=float(highs[i]),
                type="H",
                timestamp=df.iloc[i]["open_time"],
            ))
        if is_pivot_low:
            pivots.append(Pivot(
                index=i,
                price=float(lows[i]),
                type="L",
                timestamp=df.iloc[i]["open_time"],
            ))

    return pivots


if __name__ == "__main__":
    df = pd.read_csv("data/BTCUSDT_1d.csv")
    df["open_time"] = pd.to_datetime(df["open_time"])
    pivots = detect_pivots(df)

    for p in pivots[-10:]:
        print(p)