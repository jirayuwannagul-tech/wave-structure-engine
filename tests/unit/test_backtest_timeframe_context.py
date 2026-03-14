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


def test_resolve_backtest_non_4h_non_1d_returns_none(monkeypatch):
    """Timeframe that is not 1D and not 4H → returns None, None, True (line 42)."""
    sample_df = pd.DataFrame([{"open_time": pd.Timestamp("2026-01-01T00:00:00Z"), "close": 100.0}])

    monkeypatch.setattr(
        "analysis.backtest_timeframe_context.get_manual_wave_context",
        lambda symbol, timeframe: None,
    )

    bias, context, allow_analysis = resolve_backtest_higher_timeframe_context(
        symbol="BTCUSDT",
        timeframe="1H",
        sample_df=sample_df,
    )

    assert bias is None
    assert context is None
    assert allow_analysis is True


def test_resolve_backtest_4h_with_higher_df_too_few_rows(monkeypatch):
    """4H with higher_timeframe_df that has fewer rows than min_window → None, None, True (line 46)."""
    cutoff = pd.Timestamp("2026-01-01T00:00:00Z")
    sample_df = pd.DataFrame([{"open_time": cutoff, "close": 100.0}])
    # All rows in higher_df are after cutoff, so filtered df will be empty
    higher_df = pd.DataFrame([
        {"open_time": pd.Timestamp("2026-01-02T00:00:00Z"), "close": 200.0},
    ])

    monkeypatch.setattr(
        "analysis.backtest_timeframe_context.get_manual_wave_context",
        lambda symbol, timeframe: None,
    )

    bias, context, allow_analysis = resolve_backtest_higher_timeframe_context(
        symbol="BTCUSDT",
        timeframe="4H",
        sample_df=sample_df,
        higher_timeframe_df=higher_df,
        higher_timeframe_min_window=5,
    )

    assert bias is None
    assert context is None
    assert allow_analysis is True


def test_resolve_backtest_1d_with_weekly_df_no_manual_context(monkeypatch):
    """1D with parent_timeframe_df and no manual context → builds weekly via build_dataframe_analysis (lines 82-95)."""
    cutoff = pd.Timestamp("2026-01-10T00:00:00Z")
    sample_df = pd.DataFrame([{"open_time": cutoff, "close": 100.0}])
    weekly_df = pd.DataFrame([
        {"open_time": pd.Timestamp("2026-01-0" + str(i) + "T00:00:00Z"), "close": float(95 + i)}
        for i in range(1, 9)
    ])

    monkeypatch.setattr(
        "analysis.backtest_timeframe_context.get_manual_wave_context",
        lambda symbol, timeframe: None,
    )
    monkeypatch.setattr(
        "analysis.backtest_timeframe_context.build_dataframe_analysis",
        lambda **kwargs: {
            "timeframe": "1W",
            "scenarios": [],
            "wave_summary": {"bias": "BEARISH"},
        },
    )
    monkeypatch.setattr(
        "analysis.backtest_timeframe_context.build_higher_timeframe_context",
        lambda analysis: {"timeframe": "1W", "bias": "BEARISH"},
    )

    bias, context, allow_analysis = resolve_backtest_higher_timeframe_context(
        symbol="BTCUSDT",
        timeframe="1D",
        sample_df=sample_df,
        parent_timeframe_df=weekly_df,
        parent_timeframe_min_window=5,
    )

    assert bias == "BEARISH"
    assert context is not None
    assert context["timeframe"] == "1W"


def test_resolve_backtest_weekly_df_too_few_rows(monkeypatch):
    """parent_timeframe_df with fewer rows than min_window → weekly_context=None (line 87)."""
    cutoff = pd.Timestamp("2026-01-10T00:00:00Z")
    sample_df = pd.DataFrame([{"open_time": cutoff, "close": 100.0}])
    # Only 2 rows before cutoff, but min_window=10
    weekly_df = pd.DataFrame([
        {"open_time": pd.Timestamp("2026-01-01T00:00:00Z"), "close": 95.0},
        {"open_time": pd.Timestamp("2026-01-08T00:00:00Z"), "close": 98.0},
    ])

    monkeypatch.setattr(
        "analysis.backtest_timeframe_context.get_manual_wave_context",
        lambda symbol, timeframe: None,
    )

    bias, context, allow_analysis = resolve_backtest_higher_timeframe_context(
        symbol="BTCUSDT",
        timeframe="1D",
        sample_df=sample_df,
        parent_timeframe_df=weekly_df,
        parent_timeframe_min_window=10,
    )

    # weekly_context=None → weekly_bias=None → 1D returns (None, None, True)
    assert bias is None
    assert context is None
    assert allow_analysis is True
