from __future__ import annotations

import pandas as pd

from analysis.setup_filter import apply_trade_filters, build_higher_timeframe_context, extract_trade_bias
from core.engine import build_dataframe_analysis
from storage.manual_wave_context import get_manual_wave_context, serialize_manual_wave_context


def resolve_backtest_higher_timeframe_context(
    *,
    symbol: str,
    timeframe: str,
    sample_df: pd.DataFrame,
    higher_timeframe_df: pd.DataFrame | None = None,
    higher_timeframe_min_window: int | None = None,
    parent_timeframe_df: pd.DataFrame | None = None,
    parent_timeframe_min_window: int | None = None,
) -> tuple[str | None, dict | None, bool]:
    timeframe_upper = str(timeframe or "").upper()
    cutoff_time = None
    if "open_time" in sample_df.columns and len(sample_df):
        cutoff_time = sample_df.iloc[-1]["open_time"]

    weekly_context = _resolve_weekly_context(
        symbol=symbol,
        cutoff_time=cutoff_time,
        weekly_df=parent_timeframe_df,
        weekly_min_window=parent_timeframe_min_window,
    )
    weekly_bias = str((weekly_context or {}).get("bias") or "").upper() or None

    if timeframe_upper == "1D":
        return weekly_bias, weekly_context, True

    if (
        timeframe_upper != "4H"
        or higher_timeframe_df is None
        or higher_timeframe_min_window is None
        or cutoff_time is None
    ):
        return None, None, True

    higher_sample_df = higher_timeframe_df[higher_timeframe_df["open_time"] <= cutoff_time].copy()
    if len(higher_sample_df) < higher_timeframe_min_window:
        return None, None, True

    daily_analysis = build_dataframe_analysis(
        symbol=symbol,
        timeframe="1D",
        df=higher_sample_df,
        current_price=float(higher_sample_df.iloc[-1]["close"]),
    )
    daily_analysis = apply_trade_filters(
        daily_analysis,
        higher_timeframe_bias=weekly_bias,
        higher_timeframe_context=weekly_context,
    )
    daily_context = build_higher_timeframe_context(daily_analysis) or {
        "timeframe": "1D",
        "bias": extract_trade_bias(daily_analysis),
    }
    if weekly_context:
        daily_context["parent"] = weekly_context

    is_tradeable = bool(daily_analysis.get("scenarios"))
    daily_context["is_tradeable"] = is_tradeable
    return extract_trade_bias(daily_analysis), daily_context, is_tradeable


def _resolve_weekly_context(
    *,
    symbol: str,
    cutoff_time,
    weekly_df: pd.DataFrame | None,
    weekly_min_window: int | None,
) -> dict | None:
    manual_context = get_manual_wave_context(symbol, "1W")
    if manual_context is not None:
        return serialize_manual_wave_context(manual_context)

    if weekly_df is None or weekly_min_window is None or cutoff_time is None:
        return None

    weekly_sample_df = weekly_df[weekly_df["open_time"] <= cutoff_time].copy()
    if len(weekly_sample_df) < weekly_min_window:
        return None

    weekly_analysis = build_dataframe_analysis(
        symbol=symbol,
        timeframe="1W",
        df=weekly_sample_df,
        current_price=float(weekly_sample_df.iloc[-1]["close"]),
    )
    return build_higher_timeframe_context(weekly_analysis)
