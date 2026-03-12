from __future__ import annotations

from dataclasses import dataclass

from monitor.market_context import MarketContext
from monitor.breakout_detector import BreakoutEvent
from monitor.rejection_detector import RejectionEvent
from monitor.price_confirmation import PriceConfirmation


@dataclass
class DailyReport:
    symbol: str
    timeframe_summary: str
    market_summary: str
    price_summary: str
    breakout_summary: str
    rejection_summary: str
    full_text: str


def build_daily_report(
    symbol: str,
    timeframe_summary: str,
    market_context: MarketContext,
    price_confirmation: PriceConfirmation,
    breakout_event: BreakoutEvent,
    rejection_event: RejectionEvent,
) -> DailyReport:
    market_summary = market_context.summary
    price_summary = price_confirmation.message
    breakout_summary = breakout_event.message
    rejection_summary = rejection_event.message

    full_text = "\n".join(
        [
            f"Symbol: {symbol}",
            f"Timeframes: {timeframe_summary}",
            f"Market Context: {market_summary}",
            f"Price Confirmation: {price_summary}",
            f"Breakout: {breakout_summary}",
            f"Rejection: {rejection_summary}",
        ]
    )

    return DailyReport(
        symbol=symbol,
        timeframe_summary=timeframe_summary,
        market_summary=market_summary,
        price_summary=price_summary,
        breakout_summary=breakout_summary,
        rejection_summary=rejection_summary,
        full_text=full_text,
    )


if __name__ == "__main__":
    from monitor.market_context import MarketContext
    from monitor.price_confirmation import PriceConfirmation
    from monitor.breakout_detector import BreakoutEvent
    from monitor.rejection_detector import RejectionEvent

    report = build_daily_report(
        symbol="BTCUSDT",
        timeframe_summary="1W=BEARISH, 1D=BULLISH, 4H=BULLISH",
        market_context=MarketContext(
            trend_context="bullish_rebound_inside_mixed_context",
            wave_structure="ABC_CORRECTION",
            wave_bias="BULLISH",
            scenario_state="waiting_confirmation",
            price_state="inside_range",
            mtf_state="mixed_alignment",
            summary="ABC_CORRECTION | bias=BULLISH | scenario=waiting_confirmation | price=inside_range | mtf=mixed_alignment",
        ),
        price_confirmation=PriceConfirmation(
            state="inside_range",
            price=69597.46,
            confirmation=74050.0,
            invalidation=65618.49,
            message="price is between invalidation and confirmation",
        ),
        breakout_event=BreakoutEvent(
            state="no_breakout",
            level=74050.0,
            price=69597.46,
            bias="BULLISH",
            message="price has not broken bullish confirmation",
        ),
        rejection_event=RejectionEvent(
            state="no_rejection",
            level=65618.49,
            price=69597.46,
            bias="BULLISH",
            message="no bullish rejection detected",
        ),
    )

    print(report.full_text)