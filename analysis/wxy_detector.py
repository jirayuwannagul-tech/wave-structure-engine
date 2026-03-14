from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from analysis.swing_builder import SwingPoint


@dataclass
class WXYPattern:
    pattern_type: str
    direction: str
    w: SwingPoint
    x: SwingPoint
    y: SwingPoint
    wx_length: float
    xy_length: float
    y_vs_w_ratio: float
    x_retrace_ratio: float = 1.0   # X/W length ratio — how strong was the connector wave


def _safe_ratio(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return a / b


def detect_wxy(swings: List[SwingPoint]) -> Optional[WXYPattern]:
    if len(swings) < 3:
        return None

    for i in range(len(swings) - 3, -1, -1):
        w, x, y = swings[i : i + 3]

        # bullish WXY : L-H-L
        if [w.type, x.type, y.type] == ["L", "H", "L"]:
            wx = x.price - w.price
            xy = x.price - y.price

            if wx <= 0 or xy <= 0:
                continue

            ratio = _safe_ratio(xy, wx)

            if y.price > w.price and 0.50 <= ratio <= 1.10:
                return WXYPattern(
                    pattern_type="WXY",
                    direction="bullish",
                    w=w,
                    x=x,
                    y=y,
                    wx_length=wx,
                    xy_length=xy,
                    y_vs_w_ratio=ratio,
                    x_retrace_ratio=1.0,
                )

        # bearish WXY : H-L-H
        if [w.type, x.type, y.type] == ["H", "L", "H"]:
            wx = w.price - x.price
            xy = y.price - x.price

            if wx <= 0 or xy <= 0:
                continue

            ratio = _safe_ratio(xy, wx)

            if y.price < w.price and 0.50 <= ratio <= 1.10:
                return WXYPattern(
                    pattern_type="WXY",
                    direction="bearish",
                    w=w,
                    x=x,
                    y=y,
                    wx_length=wx,
                    xy_length=xy,
                    y_vs_w_ratio=ratio,
                    x_retrace_ratio=1.0,
                )

    return None