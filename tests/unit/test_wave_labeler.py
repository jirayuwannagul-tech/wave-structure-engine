"""Tests for analysis/wave_labeler.py"""

import pytest

from analysis.wave_labeler import (
    WaveLabel,
    format_current_wave,
    format_wave_with_degree,
    label_wave,
    phase_description,
)


# ---------------------------------------------------------------------------
# Degree mapping
# ---------------------------------------------------------------------------


def test_1d_maps_to_intermediate():
    label = label_wave("4", "1D")
    assert label.degree == "intermediate"
    assert label.formatted == "(4)"


def test_1w_maps_to_primary():
    label = label_wave("3", "1W")
    assert label.degree == "primary"
    assert label.formatted == "[3]"


def test_4h_maps_to_minor():
    label = label_wave("3", "4H")
    assert label.degree == "minor"
    assert label.formatted == "3"


def test_1h_maps_to_minute():
    label = label_wave("3", "1H")
    assert label.degree == "minute"
    assert label.formatted == "iii"


# ---------------------------------------------------------------------------
# Impulse wave labels
# ---------------------------------------------------------------------------


def test_intermediate_wave_1_to_5():
    expected = {"1": "(1)", "2": "(2)", "3": "(3)", "4": "(4)", "5": "(5)"}
    for num, fmt in expected.items():
        label = label_wave(num, "1D")
        assert label.formatted == fmt, f"Wave {num} expected {fmt}, got {label.formatted}"


def test_minute_wave_labels():
    expected = {"1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v"}
    for num, fmt in expected.items():
        label = label_wave(num, "1H")
        assert label.formatted == fmt, f"Wave {num} expected {fmt}, got {label.formatted}"


def test_primary_wave_labels():
    expected = {"1": "[1]", "2": "[2]", "3": "[3]", "4": "[4]", "5": "[5]"}
    for num, fmt in expected.items():
        label = label_wave(num, "1W")
        assert label.formatted == fmt


# ---------------------------------------------------------------------------
# Corrective wave labels
# ---------------------------------------------------------------------------


def test_intermediate_abc():
    assert label_wave("A", "1D").formatted == "(A)"
    assert label_wave("B", "1D").formatted == "(B)"
    assert label_wave("C", "1D").formatted == "(C)"


def test_minute_abc():
    assert label_wave("A", "1H").formatted == "a"
    assert label_wave("B", "1H").formatted == "b"
    assert label_wave("C", "1H").formatted == "c"


def test_primary_abc():
    assert label_wave("A", "1W").formatted == "[A]"
    assert label_wave("B", "1W").formatted == "[B]"
    assert label_wave("C", "1W").formatted == "[C]"


def test_wxy_labels():
    assert label_wave("W", "1D").formatted == "(W)"
    assert label_wave("X", "1D").formatted == "(X)"
    assert label_wave("Y", "1D").formatted == "(Y)"


# ---------------------------------------------------------------------------
# Case insensitivity
# ---------------------------------------------------------------------------


def test_lowercase_input_handled():
    label = label_wave("a", "1D")
    assert label.formatted == "(A)"

    label = label_wave("c", "1H")
    assert label.formatted == "c"


# ---------------------------------------------------------------------------
# Unknown timeframe falls back to minor
# ---------------------------------------------------------------------------


def test_unknown_timeframe_falls_back():
    label = label_wave("3", "15M")
    # Falls back to "minor" (the default in wave_labeler)
    assert label.formatted == "3"


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def test_format_current_wave():
    result = format_current_wave("4", "1D")
    assert result == "Wave (4)"


def test_format_wave_with_degree():
    result = format_wave_with_degree("4", "1D")
    assert "Wave (4)" in result
    assert "Intermediate" in result


def test_format_current_wave_minute():
    result = format_current_wave("3", "1H")
    assert result == "Wave iii"


# ---------------------------------------------------------------------------
# WaveLabel properties
# ---------------------------------------------------------------------------


def test_wave_label_full_label():
    label = label_wave("4", "1D")
    assert label.full_label == "Wave (4) of Intermediate"


def test_wave_label_degree_display():
    label = label_wave("5", "1W")
    assert label.degree_display == "Primary"


# ---------------------------------------------------------------------------
# Phase descriptions
# ---------------------------------------------------------------------------


def test_phase_corrective_waves():
    assert "Corrective" in phase_description("2", "bullish")
    assert "Corrective" in phase_description("4", "bullish")
    assert "Corrective" in phase_description("B", "bearish")


def test_phase_impulse_waves():
    assert "Impulse" in phase_description("1", "bullish")
    assert "Impulse" in phase_description("3", "bullish")
    assert "Impulse" in phase_description("5", "bullish")


def test_phase_wave_c():
    assert "Final" in phase_description("C", "bearish")


def test_phase_wave_a():
    assert "Corrective Wave A" in phase_description("A", "bearish")


def test_phase_unknown_wave():
    assert phase_description("X", "bullish") == "Wave in Progress"
