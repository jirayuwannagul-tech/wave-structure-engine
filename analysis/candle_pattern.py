"""Candlestick pattern detection for entry confirmation.

Detects reversal patterns at key levels:
- Hammer / Inverted Hammer (bullish reversal at support)
- Shooting Star / Hanging Man (bearish reversal at resistance)
- Bullish/Bearish Engulfing
- Doji (indecision - neutral signal)
- Pin Bar (long wick, small body)
"""
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd


@dataclass
class CandlePattern:
    name: str           # e.g. "HAMMER", "ENGULFING_BEARISH"
    direction: str      # "bullish" or "bearish"
    strength: float     # 0.0-1.0
    index: int          # candle index in dataframe


def detect_candle_patterns(df: pd.DataFrame, lookback: int = 3) -> list[CandlePattern]:
    """Detect reversal candlestick patterns in the last `lookback` candles."""
    patterns = []
    if len(df) < 2:
        return patterns

    start = max(0, len(df) - lookback)
    for i in range(start, len(df)):
        row = df.iloc[i]
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        body = abs(c - o)
        total_range = h - l
        if total_range == 0:
            continue
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l
        body_ratio = body / total_range

        # Hammer (bullish): small body at top, long lower wick
        if (lower_wick >= 2 * body and upper_wick <= 0.3 * total_range
                and body_ratio <= 0.35):
            strength = min(1.0, lower_wick / total_range * 2)
            patterns.append(CandlePattern("HAMMER", "bullish", strength, i))

        # Shooting Star (bearish): small body at bottom, long upper wick
        if (upper_wick >= 2 * body and lower_wick <= 0.3 * total_range
                and body_ratio <= 0.35):
            strength = min(1.0, upper_wick / total_range * 2)
            patterns.append(CandlePattern("SHOOTING_STAR", "bearish", strength, i))

        # Bullish Engulfing (needs previous candle)
        if i > 0:
            prev = df.iloc[i - 1]
            po, pc = float(prev["open"]), float(prev["close"])
            if pc < po and c > o and c > po and o < pc:  # prev bearish, curr bullish engulfs
                strength = min(1.0, body / (abs(pc - po) + 0.001))
                patterns.append(CandlePattern("ENGULFING_BULLISH", "bullish", min(strength, 1.0), i))
            if pc > po and c < o and c < po and o > pc:  # prev bullish, curr bearish engulfs
                strength = min(1.0, body / (abs(pc - po) + 0.001))
                patterns.append(CandlePattern("ENGULFING_BEARISH", "bearish", min(strength, 1.0), i))

        # Doji: very small body
        if body_ratio <= 0.1 and total_range > 0:
            patterns.append(CandlePattern("DOJI", "neutral", 0.3, i))

        # Pin Bar: long wick (>60% of range) with small body
        if lower_wick >= 0.6 * total_range and body_ratio <= 0.2:
            patterns.append(CandlePattern("PIN_BAR_BULLISH", "bullish", lower_wick / total_range, i))
        if upper_wick >= 0.6 * total_range and body_ratio <= 0.2:
            patterns.append(CandlePattern("PIN_BAR_BEARISH", "bearish", upper_wick / total_range, i))

    return patterns


def score_candle_confirmation(
    patterns: list[CandlePattern],
    bias: str,
) -> float:
    """Score how well recent candle patterns confirm the trade bias.

    Returns:
        +0.05 to +0.10: strong confirmation
        0.0: neutral / no pattern
        -0.05: contradicting pattern (opposite direction)
    """
    if not patterns:
        return 0.0

    bias_upper = bias.upper()
    expected_direction = "bullish" if bias_upper == "BULLISH" else "bearish"

    best_confirm = 0.0
    worst_contradict = 0.0

    for p in patterns:
        if p.direction == expected_direction:
            best_confirm = max(best_confirm, p.strength)
        elif p.direction != "neutral":
            worst_contradict = max(worst_contradict, p.strength)

    if best_confirm >= 0.6:
        return 0.10
    if best_confirm >= 0.4:
        return 0.05
    if worst_contradict >= 0.6:
        return -0.05
    return 0.0
