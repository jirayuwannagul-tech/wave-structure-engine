from __future__ import annotations

import pandas as pd

from analysis.indicator_engine import (
    check_volume_divergence_bearish,
    check_volume_divergence_bullish,
    check_volume_spike,
)
from analysis.rsi_divergence import (
    RSIDivergenceSignal,
    detect_bearish_rsi_divergence,
    detect_bullish_rsi_divergence,
)


def check_bullish_trend_context(df: pd.DataFrame) -> bool:
    if "close" not in df.columns or "ema50" not in df.columns:
        return False
    if len(df) == 0:
        return False
    return bool(df.iloc[-1]["close"] > df.iloc[-1]["ema50"])


def check_bearish_trend_context(df: pd.DataFrame) -> bool:
    if "close" not in df.columns or "ema50" not in df.columns:
        return False
    if len(df) == 0:
        return False
    return bool(df.iloc[-1]["close"] < df.iloc[-1]["ema50"])


def check_long_term_bullish_trend(df: pd.DataFrame) -> bool:
    """Price above EMA 200 = long-term bullish context."""
    if "ema200" not in df.columns or len(df) == 0:
        return False
    return bool(df.iloc[-1]["close"] > df.iloc[-1]["ema200"])


def check_long_term_bearish_trend(df: pd.DataFrame) -> bool:
    """Price below EMA 200 = long-term bearish context."""
    if "ema200" not in df.columns or len(df) == 0:
        return False
    return bool(df.iloc[-1]["close"] < df.iloc[-1]["ema200"])


def check_bullish_momentum(df: pd.DataFrame, rsi_threshold: float = 50.0) -> bool:
    if "rsi" not in df.columns or len(df) == 0:
        return False
    return bool(df.iloc[-1]["rsi"] >= rsi_threshold)


def check_bearish_momentum(df: pd.DataFrame, rsi_threshold: float = 50.0) -> bool:
    if "rsi" not in df.columns or len(df) == 0:
        return False
    return bool(df.iloc[-1]["rsi"] <= rsi_threshold)


def check_atr_expansion(df: pd.DataFrame, lookback: int = 20) -> bool:
    if "atr" not in df.columns or len(df) < lookback:
        return False

    recent_atr = df.iloc[-1]["atr"]
    avg_atr = df["atr"].tail(lookback).mean()

    if pd.isna(recent_atr) or pd.isna(avg_atr) or avg_atr == 0:
        return False

    return bool(recent_atr >= avg_atr)


def check_bullish_volume_confirmation(df: pd.DataFrame) -> bool:
    """Volume spike on current bar confirms bullish momentum."""
    return check_volume_spike(df)


def check_bearish_volume_confirmation(df: pd.DataFrame) -> bool:
    """Volume spike on current bar confirms bearish momentum."""
    return check_volume_spike(df)


def detect_aligned_rsi_divergence(
    direction: str,
    df: pd.DataFrame,
    pivots,
) -> RSIDivergenceSignal | None:
    direction = (direction or "").lower()

    if len(df) == 0 or not pivots:
        return None

    if direction == "bullish":
        return detect_bullish_rsi_divergence(df, pivots)

    if direction == "bearish":
        return detect_bearish_rsi_divergence(df, pivots)

    return None


def validate_bullish_wave_with_indicators(df: pd.DataFrame) -> bool:
    trend_ok = check_bullish_trend_context(df)
    momentum_ok = check_bullish_momentum(df)
    atr_ok = check_atr_expansion(df)
    volume_ok = check_bullish_volume_confirmation(df)
    # trend + momentum required; atr OR volume confirms
    return bool(trend_ok and momentum_ok and (atr_ok or volume_ok))


def validate_bearish_wave_with_indicators(df: pd.DataFrame) -> bool:
    trend_ok = check_bearish_trend_context(df)
    momentum_ok = check_bearish_momentum(df)
    atr_ok = check_atr_expansion(df)
    volume_ok = check_bearish_volume_confirmation(df)
    return bool(trend_ok and momentum_ok and (atr_ok or volume_ok))
