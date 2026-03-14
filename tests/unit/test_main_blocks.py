"""Tests that execute __main__ blocks via runpy to increase coverage.

These tests use runpy.run_module with mocked file I/O so the __main__ blocks
can run without needing real data files.
"""
from __future__ import annotations

import runpy
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


def _make_dummy_df():
    """Create a minimal OHLCV DataFrame that detect_pivots can work with."""
    n = 20
    return pd.DataFrame(
        {
            "open_time": pd.date_range("2026-01-01", periods=n, freq="D", tz="UTC"),
            "high": [100 + i % 5 for i in range(n)],
            "low": [95 + i % 5 for i in range(n)],
            "close": [98 + i % 5 for i in range(n)],
            "volume": [1000.0] * n,
        }
    )


def test_fibonacci_engine_main_block():
    """fibonacci_engine.__main__ has no file I/O — just run it directly."""
    runpy.run_module("analysis.fibonacci_engine", run_name="__main__")


def test_swing_builder_main_block():
    """Run swing_builder.__main__ with mocked CSV."""
    dummy_df = _make_dummy_df()
    with patch("pandas.read_csv", return_value=dummy_df):
        runpy.run_module("analysis.swing_builder", run_name="__main__")


def test_wave_degree_main_block():
    """Run wave_degree.__main__ with mocked CSV."""
    dummy_df = _make_dummy_df()
    with patch("pandas.read_csv", return_value=dummy_df):
        runpy.run_module("analysis.wave_degree", run_name="__main__")


def test_pivot_detector_main_block():
    """Run pivot_detector.__main__ with mocked CSV."""
    dummy_df = _make_dummy_df()
    with patch("pandas.read_csv", return_value=dummy_df):
        runpy.run_module("analysis.pivot_detector", run_name="__main__")


def test_future_projection_main_block():
    """Run future_projection.__main__ with mocked CSV and dependencies."""
    dummy_df = _make_dummy_df()
    from analysis.pivot_detector import Pivot
    from analysis.wave_detector import ABCPattern

    dummy_abc = ABCPattern(
        a=Pivot(index=1, price=100.0, type="L", timestamp="2026-01-01"),
        b=Pivot(index=2, price=110.0, type="H", timestamp="2026-01-02"),
        c=Pivot(index=3, price=105.0, type="L", timestamp="2026-01-03"),
        direction="bullish",
        ab_length=10.0,
        bc_length=5.0,
        bc_vs_ab_ratio=0.5,
    )

    with (
        patch("pandas.read_csv", return_value=dummy_df),
        patch("analysis.wave_detector.detect_latest_abc", return_value=dummy_abc),
        patch("analysis.wave_detector.detect_latest_impulse", return_value=None),
    ):
        runpy.run_module("analysis.future_projection", run_name="__main__")


def test_main_alternate_count_main_block():
    """Run main_alternate_count.__main__ with mocked CSV and detectors."""
    dummy_df = _make_dummy_df()
    with (
        patch("pandas.read_csv", return_value=dummy_df),
        patch("analysis.wave_detector.detect_latest_abc", return_value=None),
        patch("analysis.wave_detector.detect_latest_impulse", return_value=None),
    ):
        runpy.run_module("analysis.main_alternate_count", run_name="__main__")


def test_corrective_detector_main_block():
    """Run corrective_detector.__main__ with mocked CSV."""
    dummy_df = _make_dummy_df()
    with patch("pandas.read_csv", return_value=dummy_df):
        runpy.run_module("analysis.corrective_detector", run_name="__main__")


def test_wave_detector_main_block():
    """Run wave_detector.__main__ with mocked CSV."""
    dummy_df = _make_dummy_df()
    with patch("pandas.read_csv", return_value=dummy_df):
        runpy.run_module("analysis.wave_detector", run_name="__main__")
