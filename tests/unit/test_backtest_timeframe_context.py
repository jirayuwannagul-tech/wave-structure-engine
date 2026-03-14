from types import SimpleNamespace

import pandas as pd

from analysis.backtest_timeframe_context import resolve_backtest_higher_timeframe_context


def test_resolve_backtest_higher_timeframe_context_returns_manual_weekly_for_1d(monkeypatch):
    sample_df = pd.DataFrame(
        [
            {"open_time": pd.Timestamp("2026-01-01T00:00:00Z"), "close": 100.0},
            {"open_time": pd.Timestamp("2026-01-02T00:00:00Z"), "close": 101.0},
        ]
    )

    monkeypatch.setattr(
        "analysis.backtest_timeframe_context.get_manual_wave_context",
        lambda symbol, timeframe: SimpleNamespace(
            symbol=symbol,
            timeframe="1W",
            bias="BEARISH",
            wave_number="5",
            structure="IMPULSE",
            position="WAVE_5_COMPLETE",
            note="seed",
            source="manual",
        ),
    )

    bias, context, allow_analysis = resolve_backtest_higher_timeframe_context(
        symbol="BTCUSDT",
        timeframe="1D",
        sample_df=sample_df,
    )

    assert allow_analysis is True
    assert bias == "BEARISH"
    assert context["timeframe"] == "1W"
    assert context["wave_number"] == "5"


def test_resolve_backtest_higher_timeframe_context_blocks_4h_when_daily_is_not_tradeable(monkeypatch):
    sample_df = pd.DataFrame(
        [
            {"open_time": pd.Timestamp("2026-01-01T00:00:00Z"), "close": 100.0},
            {"open_time": pd.Timestamp("2026-01-02T00:00:00Z"), "close": 101.0},
            {"open_time": pd.Timestamp("2026-01-03T00:00:00Z"), "close": 102.0},
        ]
    )
    higher_df = sample_df.copy()

    monkeypatch.setattr(
        "analysis.backtest_timeframe_context.get_manual_wave_context",
        lambda symbol, timeframe: SimpleNamespace(
            symbol=symbol,
            timeframe="1W",
            bias="BEARISH",
            wave_number="5",
            structure="IMPULSE",
            position="WAVE_5_COMPLETE",
            note="seed",
            source="manual",
        ),
    )
    monkeypatch.setattr(
        "analysis.backtest_timeframe_context.build_dataframe_analysis",
        lambda **kwargs: {
            "timeframe": "1D",
            "has_pattern": True,
            "primary_pattern_type": "ABC_CORRECTION",
            "position": SimpleNamespace(bias="BULLISH", wave_number="B", structure="ABC_CORRECTION", position="IN_WAVE_B"),
            "wave_summary": {"bias": "BULLISH", "current_wave": "B"},
            "scenarios": [SimpleNamespace(name="Main Bullish", bias="BULLISH")],
        },
    )
    monkeypatch.setattr(
        "analysis.backtest_timeframe_context.apply_trade_filters",
        lambda analysis, **kwargs: {**analysis, "scenarios": [], "trade_filter": {"scenario_count_after": 0}},
    )

    bias, context, allow_analysis = resolve_backtest_higher_timeframe_context(
        symbol="BTCUSDT",
        timeframe="4H",
        sample_df=sample_df,
        higher_timeframe_df=higher_df,
        higher_timeframe_min_window=2,
    )

    assert bias == "BULLISH"
    assert context["timeframe"] == "1D"
    assert context["is_tradeable"] is False
    assert context["parent"]["timeframe"] == "1W"
    assert allow_analysis is False
