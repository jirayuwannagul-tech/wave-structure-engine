from __future__ import annotations

from analysis.future_projection import project_next_wave
from analysis.key_levels import extract_pattern_key_levels
from analysis.multi_count_engine import (
    generate_labeled_wave_counts,
    generate_wave_counts,
)
from analysis.pivot_detector import detect_pivots
from analysis.trend_classifier import classify_market_trend
from analysis.wave_decision_engine import build_wave_summary
from analysis.wave_position import detect_wave_position
from data.candle_utils import drop_unclosed_candle
from data.market_data_fetcher import MarketDataFetcher
from output.report_formatter import format_report
from scenarios.scenario_engine import generate_scenarios


def build_dataframe_analysis(
    symbol: str,
    timeframe: str,
    df,
    current_price: float | None = None,
) -> dict:
    pivots = detect_pivots(df)
    trend = classify_market_trend(pivots, df=df)
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
    )

    scenarios = []
    projection = None

    if key_levels is not None:
        projection = project_next_wave(position, key_levels)
        scenarios = generate_scenarios(position, key_levels, projection)

    if current_price is None:
        current_price = float(df.iloc[-1]["close"])

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
    )

    return {
        "symbol": symbol,
        "timeframe": timeframe.upper(),
        "has_pattern": True,
        "current_price": current_price,
        "abc_pattern": primary_pattern if primary_pattern_type == "ABC_CORRECTION" else None,
        "impulse_pattern": primary_pattern if primary_pattern_type == "IMPULSE" else None,
        "primary_pattern_type": primary_pattern_type,
        "primary_pattern": primary_pattern,
        "position": position,
        "key_levels": key_levels,
        "projection": projection,
        "scenarios": scenarios,
        "wave_summary": wave_summary,
        "trend": trend,
        "confidence": confidence,
        "probability": probability,
        "indicator_context": indicator_context,
        "report": report,
    }


def build_timeframe_analysis(symbol: str, interval: str, limit: int = 200) -> dict:
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
    )


def run_single_timeframe(symbol: str, interval: str, limit: int = 200) -> str:
    analysis = build_timeframe_analysis(symbol, interval, limit)
    return analysis["report"]


def run_multi_timeframe(symbol: str = "BTCUSDT") -> str:
    reports = [
        run_single_timeframe(symbol, "1d", 200),
        run_single_timeframe(symbol, "4h", 200),
    ]
    return "\n\n" + ("\n" + "=" * 80 + "\n\n").join(reports)


if __name__ == "__main__":
    print(run_multi_timeframe())
