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


def compress_pivots(pivots: List[Pivot]) -> List[Pivot]:
    """Reduce pivots to strictly alternating H/L by keeping only the most extreme.

    When consecutive pivots of the same type appear (e.g. H H or L L), only the
    most extreme one is kept (highest H, lowest L).  The result is a list where
    every adjacent pair has opposite types, which is required by the Elliott Wave
    sequence matchers.

    Args:
        pivots: Pivot list, ordered chronologically.

    Returns:
        New list with strictly alternating H/L pivots.
    """
    if not pivots:
        return []

    compressed: List[Pivot] = []
    group_start = 0

    for i in range(1, len(pivots) + 1):
        if i == len(pivots) or pivots[i].type != pivots[group_start].type:
            # End of a same-type group — pick the most extreme pivot
            group = pivots[group_start:i]
            if group[0].type == "H":
                best = max(group, key=lambda p: p.price)
            else:
                best = min(group, key=lambda p: p.price)
            compressed.append(best)
            group_start = i

    return compressed


def find_structural_anchor(pivots: List[Pivot]) -> int:
    """Return the index of the anchor pivot for the current EW wave count.

    Uses Break of Structure (BOS) logic on a strictly alternating H/L pivot
    list (output of ``compress_pivots``).

    Definition of BOS in the alternating list:
    - **Bullish BOS**: a High pivot that exceeds the previous High (two positions
      back).  The Low pivot between them becomes the wave anchor — it marks the
      start of the new upward impulse.
    - **Bearish BOS**: a Low pivot that falls below the previous Low.  The High
      pivot between them is the anchor — start of the new downward impulse.

    Scans from the most recent pivot backwards so that the MOST RECENT structural
    break is returned.  This correctly identifies the current-degree anchor rather
    than a completed historical structure.

    Args:
        pivots: Strictly alternating H/L pivots in chronological order.

    Returns:
        Index of the anchor pivot.  Returns ``0`` if no BOS is found (fall back
        to the very first pivot as the anchor of the entire sequence).
    """
    if len(pivots) < 3:
        return 0

    for i in range(len(pivots) - 1, 1, -1):
        p_curr = pivots[i]
        p_prev = pivots[i - 2]   # same type as p_curr in a clean alternating list

        if p_prev.type != p_curr.type:
            # Sequence is not properly alternating at this triplet — skip
            continue

        if p_curr.type == "H" and p_curr.price > p_prev.price:
            # Bullish BOS: new higher high → anchor is the Low between them
            return i - 1

        if p_curr.type == "L" and p_curr.price < p_prev.price:
            # Bearish BOS: new lower low → anchor is the High between them
            return i - 1

    # No BOS found — use the very first pivot as anchor
    return 0


if __name__ == "__main__":
    df = pd.read_csv("data/BTCUSDT_1d.csv")
    df["open_time"] = pd.to_datetime(df["open_time"])
    pivots = detect_pivots(df)

    for p in pivots[-10:]:
        print(p)