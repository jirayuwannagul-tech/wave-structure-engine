from __future__ import annotations

from dataclasses import replace

from analysis.candle_pattern import detect_candle_patterns
from analysis.fibonacci_confluence import build_fib_levels_from_swing, find_confluence_zones
from analysis.future_projection import project_next_wave
from analysis.inprogress_detector import detect_inprogress_wave
from analysis.key_levels import extract_pattern_key_levels
from analysis.multi_count_engine import (
    generate_labeled_wave_counts,
    generate_wave_counts,
)
from analysis.pivot_detector import detect_pivots
from analysis.setup_filter import apply_trade_filters
from analysis.trend_classifier import classify_market_trend
from analysis.wave_decision_engine import build_wave_summary
from analysis.wave_position import detect_wave_position
from analysis.wave_sequence_engine import build_wave_sequence
from data.candle_utils import drop_unclosed_candle
from data.market_data_fetcher import MarketDataFetcher
from output.report_formatter import format_report
from scenarios.scenario_engine import generate_scenarios


def build_dataframe_analysis(
    symbol: str,
    timeframe: str,
    df,
    current_price: float | None = None,
    higher_timeframe_bias: str | None = None,
    higher_timeframe_wave_number: str | None = None,
    higher_timeframe_context: dict | None = None,
) -> dict:
    """Run the full Elliott Wave analysis pipeline on a pre-loaded DataFrame.

    Args:
        symbol: Trading pair symbol, e.g. "BTCUSDT".
        timeframe: Candle interval string, e.g. "1d" or "4h".
        df: pandas DataFrame with OHLCV columns (open, high, low, close, volume).
        current_price: Override the current price. If None, uses df's last close.

    Returns:
        dict with keys: symbol, timeframe, has_pattern, current_price,
        primary_pattern_type, primary_pattern, position, key_levels, projection,
        scenarios, wave_summary, trend, confidence, probability, report.
        If no pattern is detected, returns a minimal dict with has_pattern=False.
    """
    # Add ATR column if not present (needed for swing size filtering)
    from analysis.indicator_engine import calculate_atr
    if "atr" not in df.columns:
        df = df.copy()
        df["atr"] = calculate_atr(df, period=14)

    # Timeframe-aware pivot detection: faster confirmation for shorter timeframes
    _PIVOT_RIGHT = {"1W": 2, "1D": 1, "4H": 1, "1H": 1}
    _PIVOT_ATR_MULT = {"1W": 1.0, "1D": 0.5, "4H": 0.3, "1H": 0.2}
    tf_upper = timeframe.upper()
    right_bars = _PIVOT_RIGHT.get(tf_upper, 3)
    atr_mult = _PIVOT_ATR_MULT.get(tf_upper, 0.0)
    pivots = detect_pivots(df, right=right_bars, min_swing_atr_mult=atr_mult)
    trend = classify_market_trend(pivots, df=df)

    # Detect candle patterns at entry zone
    candle_patterns = detect_candle_patterns(df, lookback=3)
    inprogress = detect_inprogress_wave(pivots)
    wave_sequence = build_wave_sequence(pivots, inprogress=inprogress)
    wave_counts = generate_wave_counts(pivots, df=df)
    labeled_wave_counts = generate_labeled_wave_counts(pivots, timeframe.upper(), df=df)

    if not wave_counts or not labeled_wave_counts:
        return {
            "symbol": symbol,
            "timeframe": timeframe.upper(),
            "has_pattern": False,
            "report": f"Symbol: {symbol}\nTimeframe: {timeframe.upper()}\n\nNo wave pattern detected.",
        }

    enriched_wave_reports = []
    for report in labeled_wave_counts:
        pattern_type = report.get("pattern_type")
        pattern = report.get("pattern")
        key_levels = extract_pattern_key_levels(pattern_type, pattern)
        enriched_wave_reports.append(
            {
                **report,
                "key_levels": key_levels,
                "support": getattr(key_levels, "support", None),
                "resistance": getattr(key_levels, "resistance", None),
            }
        )

    wave_summary = build_wave_summary(enriched_wave_reports)
    current_wave = wave_summary.get("current_wave")
    primary_report = enriched_wave_reports[0]
    primary_pattern = primary_report.get("pattern")
    primary_pattern_type = primary_report.get("pattern_type")
    key_levels = primary_report.get("key_levels")

    position = detect_wave_position(
        pattern_type=primary_pattern_type,
        pattern=primary_pattern,
        inprogress=inprogress,
    )
    current_leg = (wave_sequence.get("current_leg") or {})
    current_leg_label = current_leg.get("label")
    current_leg_structure = current_leg.get("structure")
    current_leg_position = current_leg.get("position")
    if current_leg_label:
        if hasattr(position, "__dataclass_fields__"):
            position = replace(
                position,
                wave_number=current_leg_label,
                building_wave=bool(current_leg.get("building", position.building_wave)),
                position=current_leg_position or position.position,
                structure=current_leg_structure or position.structure,
            )
        else:
            position.wave_number = current_leg_label
            position.building_wave = bool(current_leg.get("building", getattr(position, "building_wave", False)))
            position.position = current_leg_position or getattr(position, "position", None)
            position.structure = current_leg_structure or getattr(position, "structure", None)

    # Build Fibonacci confluence zones from recent significant swings
    confluence_zones = []
    if len(pivots) >= 4:
        fib_levels_list = []
        for i in range(max(0, len(pivots) - 4), len(pivots) - 1):
            p_start = pivots[i]
            p_end = pivots[i + 1]
            levels = build_fib_levels_from_swing(
                f"swing_{i}",
                float(p_start.price),
                float(p_end.price),
            )
            if levels:
                fib_levels_list.append(levels)
        if fib_levels_list:
            # Flatten list-of-lists into a single list of level dicts
            all_levels = [lvl for swing_levels in fib_levels_list for lvl in swing_levels]
            confluence_zones = find_confluence_zones(all_levels)

    scenarios = []
    projection = None

    if key_levels is not None:
        atr_val = float(df.iloc[-1]["atr"]) if "atr" in df.columns and len(df) > 0 else 0.0
        projection = project_next_wave(position, key_levels, recent_pivots=pivots, atr=atr_val)
        scenarios = generate_scenarios(position, key_levels, projection, confluence_zones=confluence_zones)

    if current_price is None:
        current_price = float(df.iloc[-1]["close"])

    # Generate early-entry scenarios from in-progress wave detection
    from scenarios.scenario_engine import generate_inprogress_scenarios as _gen_inprog

    inprogress_scenarios = []
    if (inprogress and getattr(inprogress, "is_valid", False)
            and getattr(inprogress, "confidence", 0) >= 0.45):
        inprogress_scenarios = _gen_inprog(inprogress, current_price or float(df.iloc[-1]["close"]))

    # Merge: add inprogress scenarios that have different bias from existing ones
    if inprogress_scenarios:
        if not scenarios:
            scenarios = inprogress_scenarios
        else:
            existing_biases = {getattr(s, "bias", None) for s in scenarios}
            for s in inprogress_scenarios:
                if getattr(s, "bias", None) not in existing_biases:
                    scenarios.append(s)

    probability = primary_report.get("probability")
    confidence = primary_report.get("confidence")
    indicator_context = primary_report.get("indicator_context")

    report = format_report(
        symbol=symbol,
        timeframe=timeframe.upper(),
        current_price=current_price,
        pattern=primary_pattern,
        position=position,
        scenarios=scenarios,
        impulse_pattern=primary_pattern if current_wave == "IMPULSE" else None,
        confidence=confidence,
        probability=probability,
        wave_summary=wave_summary,
        pattern_type=primary_pattern_type,
        trend=trend,
        indicator_context=indicator_context,
        inprogress=inprogress,
        key_levels=key_levels,
    )

    analysis = {
        "symbol": symbol,
        "timeframe": timeframe.upper(),
        "has_pattern": True,
        "current_price": current_price,
        "abc_pattern": primary_pattern if primary_pattern_type == "ABC_CORRECTION" else None,
        "impulse_pattern": primary_pattern if primary_pattern_type == "IMPULSE" else None,
        "primary_pattern_type": primary_pattern_type,
        "primary_pattern": primary_pattern,
        "position": position,
        "inprogress": inprogress,
        "inprogress_scenarios": inprogress_scenarios,
        "wave_sequence": wave_sequence,
        "key_levels": key_levels,
        "projection": projection,
        "scenarios": scenarios,
        "wave_summary": wave_summary,
        "trend": trend,
        "confidence": confidence,
        "probability": probability,
        "indicator_context": indicator_context,
        "report": report,
        "higher_timeframe_context": higher_timeframe_context,
        "confluence_zones": confluence_zones,
        "candle_patterns": candle_patterns,
    }

    return apply_trade_filters(
        analysis,
        higher_timeframe_bias=higher_timeframe_bias,
        htf_wave_number=higher_timeframe_wave_number,
        higher_timeframe_context=higher_timeframe_context,
    )


def build_timeframe_analysis(
    symbol: str,
    interval: str,
    limit: int = 200,
    higher_timeframe_bias: str | None = None,
    higher_timeframe_wave_number: str | None = None,
    higher_timeframe_context: dict | None = None,
) -> dict:
    """Fetch live OHLCV data from Binance and run the full analysis pipeline.

    Args:
        symbol: Trading pair symbol, e.g. "BTCUSDT".
        interval: Candle interval, e.g. "1d" or "4h".
        limit: Number of candles to fetch (default 200).

    Returns:
        Analysis dict as produced by build_dataframe_analysis().

    Raises:
        requests.RequestException: if Binance OHLCV fetch fails after all retries.
    """
    fetcher = MarketDataFetcher(symbol=symbol, interval=interval, limit=limit)
    df = drop_unclosed_candle(fetcher.fetch_ohlcv())

    try:
        current_price = fetcher.fetch_latest_price()
    except Exception:
        current_price = float(df.iloc[-1]["close"])

    return build_dataframe_analysis(
        symbol=symbol,
        timeframe=interval,
        df=df,
        current_price=current_price,
        higher_timeframe_bias=higher_timeframe_bias,
        higher_timeframe_wave_number=higher_timeframe_wave_number,
        higher_timeframe_context=higher_timeframe_context,
    )


def run_single_timeframe(symbol: str, interval: str, limit: int = 200) -> str:
    """Fetch data, run analysis, and return the formatted text report."""
    analysis = build_timeframe_analysis(symbol, interval, limit)
    return analysis["report"]


def run_multi_timeframe(symbol: str = "BTCUSDT") -> str:
    """Run analysis on 1D and 4H timeframes and return a combined text report."""
    reports = [
        run_single_timeframe(symbol, "1d", 200),
        run_single_timeframe(symbol, "4h", 200),
    ]
    return "\n\n" + ("\n" + "=" * 80 + "\n\n").join(reports)


if __name__ == "__main__":
    print(run_multi_timeframe())
