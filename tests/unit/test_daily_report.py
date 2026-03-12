from monitor.breakout_detector import BreakoutEvent
from monitor.market_context import MarketContext
from monitor.price_confirmation import PriceConfirmation
from monitor.rejection_detector import RejectionEvent
from output.daily_report import build_daily_report


def test_build_daily_report_contains_expected_text():
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

    assert report.symbol == "BTCUSDT"
    assert "Symbol: BTCUSDT" in report.full_text
    assert "Timeframes: 1W=BEARISH, 1D=BULLISH, 4H=BULLISH" in report.full_text
    assert "Market Context:" in report.full_text
    assert "Breakout:" in report.full_text
    assert "Rejection:" in report.full_text