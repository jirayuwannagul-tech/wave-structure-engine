from __future__ import annotations

import pandas as pd


def calculate_ema(df: pd.DataFrame, period: int) -> pd.Series:
    return df["close"].ewm(span=period, adjust=False).mean()


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    delta = df["close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()

    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

    atr = tr.rolling(period).mean()

    return atr


def calculate_volume_ma(df: pd.DataFrame, period: int = 20) -> pd.Series:
    return df["volume"].rolling(period).mean()


def check_volume_spike(df: pd.DataFrame, lookback: int = 20, multiplier: float = 1.5) -> bool:
    """Volume spike: current volume > multiplier × MA(lookback)."""
    if "volume" not in df.columns or len(df) < lookback:
        return False
    current_vol = df.iloc[-1]["volume"]
    avg_vol = df["volume"].tail(lookback).mean()
    if pd.isna(current_vol) or pd.isna(avg_vol) or avg_vol == 0:
        return False
    return bool(current_vol >= avg_vol * multiplier)


def check_volume_divergence_bullish(df: pd.DataFrame, lookback: int = 5) -> bool:
    """Bullish volume divergence: price makes lower lows but volume is declining.

    Indicates selling pressure is weakening — typical near Wave 5 bottom or Wave C bottom.
    """
    if "volume" not in df.columns or "low" not in df.columns or len(df) < lookback:
        return False
    recent = df.tail(lookback)
    price_declining = recent["low"].iloc[-1] < recent["low"].iloc[0]
    volume_declining = recent["volume"].iloc[-1] < recent["volume"].iloc[0]
    return bool(price_declining and volume_declining)


def check_volume_divergence_bearish(df: pd.DataFrame, lookback: int = 5) -> bool:
    """Bearish volume divergence: price makes higher highs but volume is declining.

    Indicates buying pressure is weakening — typical near Wave 5 top or Wave C top.
    """
    if "volume" not in df.columns or "high" not in df.columns or len(df) < lookback:
        return False
    recent = df.tail(lookback)
    price_rising = recent["high"].iloc[-1] > recent["high"].iloc[0]
    volume_declining = recent["volume"].iloc[-1] < recent["volume"].iloc[0]
    return bool(price_rising and volume_declining)


def calculate_macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """Calculate MACD line, signal line, and histogram (EMA-based)."""
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    return pd.DataFrame(
        {
            "macd": macd_line,
            "macd_signal": signal_line,
            "macd_hist": histogram,
        },
        index=df.index,
    )


def check_macd_momentum_turning_bullish(df: pd.DataFrame, lookback: int = 3) -> bool:
    """MACD histogram is increasing (becoming less negative or more positive).

    Signals bullish momentum acceleration — confirms Wave 3 or Wave C bounce.
    """
    if "macd_hist" not in df.columns or len(df) < lookback:
        return False
    recent = df["macd_hist"].tail(lookback)
    if recent.isna().any():
        return False
    return bool(recent.iloc[-1] > recent.iloc[0])


def check_macd_momentum_turning_bearish(df: pd.DataFrame, lookback: int = 3) -> bool:
    """MACD histogram is decreasing (becoming less positive or more negative).

    Signals bearish momentum acceleration — confirms Wave 3 down or Wave C drop.
    """
    if "macd_hist" not in df.columns or len(df) < lookback:
        return False
    recent = df["macd_hist"].tail(lookback)
    if recent.isna().any():
        return False
    return bool(recent.iloc[-1] < recent.iloc[0])