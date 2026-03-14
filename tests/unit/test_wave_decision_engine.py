import pytest

from analysis.wave_decision_engine import (
    _build_trade_levels,
    _fails_minimum_confidence,
    _is_ambiguous,
    _score_margin,
    build_wave_summary,
    choose_primary_and_alternate,
)


def test_choose_primary_and_alternate():
    patterns = [
        {"pattern_type": "IMPULSE", "direction": "BULLISH", "similarity_score": 0.8},
        {"pattern_type": "ABC_CORRECTION", "direction": "BEARISH", "similarity_score": 0.7},
    ]

    result = choose_primary_and_alternate(patterns)

    assert result["primary"]["pattern_type"] == "IMPULSE"
    assert result["alternate"]["pattern_type"] == "ABC_CORRECTION"


def test_build_wave_summary():
    patterns = [
        {"pattern_type": "IMPULSE", "direction": "BULLISH", "similarity_score": 0.8, "confidence": 0.85},
        {"pattern_type": "ABC_CORRECTION", "direction": "BEARISH", "similarity_score": 0.7},
    ]

    summary = build_wave_summary(patterns)

    assert summary["current_wave"] == "IMPULSE"
    assert summary["bias"] == "BULLISH"
    assert summary["alternate_wave"] == "ABC_CORRECTION"


def test_build_wave_summary_marks_near_tie_as_ambiguous():
    patterns = [
        {
            "pattern_type": "IMPULSE",
            "direction": "BULLISH",
            "similarity_score": 0.82,
            "probability": 0.145,
        },
        {
            "pattern_type": "ABC_CORRECTION",
            "direction": "BEARISH",
            "similarity_score": 0.815,
            "probability": 0.139,
        },
    ]

    summary = build_wave_summary(patterns)

    assert summary["current_wave"] == "IMPULSE"
    assert summary["alternate_wave"] == "ABC_CORRECTION"
    assert summary["bias"] is None
    assert summary["confirm"] is None
    assert summary["stop_loss"] is None
    assert summary["targets"] == []
    assert summary["is_ambiguous"] is True


def test_build_wave_summary_requires_stronger_impulse_margin():
    # IMPULSE threshold = 0.008; margin here = 0.150 - 0.144 = 0.006 < 0.008 → still ambiguous
    patterns = [
        {
            "pattern_type": "IMPULSE",
            "direction": "BULLISH",
            "similarity_score": 0.84,
            "probability": 0.150,
            "confidence": 0.90,
        },
        {
            "pattern_type": "ABC_CORRECTION",
            "direction": "BEARISH",
            "similarity_score": 0.82,
            "probability": 0.144,
            "confidence": 0.82,
        },
    ]

    summary = build_wave_summary(patterns)

    assert summary["bias"] is None
    assert summary["is_ambiguous"] is True


def test_build_wave_summary_rejects_low_confidence_abc():
    # ABC_CORRECTION min confidence = 0.72; confidence 0.68 < 0.72 → rejected
    patterns = [
        {
            "pattern_type": "ABC_CORRECTION",
            "direction": "BULLISH",
            "similarity_score": 0.86,
            "probability": 0.190,
            "confidence": 0.68,
        },
        {
            "pattern_type": "IMPULSE",
            "direction": "BEARISH",
            "similarity_score": 0.75,
            "probability": 0.140,
            "confidence": 0.88,
        },
    ]

    summary = build_wave_summary(patterns)

    assert summary["bias"] is None
    assert summary["confidence_too_low"] is True
    assert summary["confirm"] is None


# ---------- choose_primary_and_alternate empty ----------

def test_choose_primary_empty_returns_none():
    result = choose_primary_and_alternate([])
    assert result["primary"] is None
    assert result["alternate"] is None


# ---------- _score_margin edge cases ----------

def test_score_margin_no_alternate():
    assert _score_margin({"probability": 0.8}, None) == 1.0


def test_score_margin_no_primary():
    assert _score_margin(None, {"probability": 0.6}) == 1.0


def test_score_margin_uses_similarity_when_no_probability():
    p1 = {"similarity_score": 0.8}
    p2 = {"similarity_score": 0.6}
    assert _score_margin(p1, p2) == pytest.approx(0.2)


# ---------- _is_ambiguous edge cases ----------

def test_is_ambiguous_no_alternate():
    assert _is_ambiguous({"pattern_type": "IMPULSE"}, None, 0.05) is False


def test_is_ambiguous_no_primary():
    assert _is_ambiguous(None, {"pattern_type": "FLAT"}, 0.05) is False


# ---------- _fails_minimum_confidence ----------

def test_fails_minimum_confidence_no_primary():
    assert _fails_minimum_confidence(None) is False


def test_fails_minimum_confidence_no_min_conf_pattern():
    # TRIANGLE has no entry in PATTERN_MIN_CONFIDENCE → min=0.0, always passes
    p = {"pattern_type": "TRIANGLE", "confidence": 0.1}
    assert _fails_minimum_confidence(p) is False


# ---------- _build_trade_levels ----------

def test_build_trade_levels_bullish():
    pattern = {
        "direction": "BULLISH",
        "support": 90.0,
        "resistance": 110.0,
    }
    levels = _build_trade_levels(pattern)
    assert levels["confirm"] == 110.0
    assert levels["stop_loss"] == 90.0
    assert levels["targets"] == [110.0]


def test_build_trade_levels_bearish():
    pattern = {
        "direction": "BEARISH",
        "support": 80.0,
        "resistance": 120.0,
    }
    levels = _build_trade_levels(pattern)
    assert levels["confirm"] == 80.0
    assert levels["stop_loss"] == 120.0
    assert levels["targets"] == [80.0]


def test_build_trade_levels_neutral():
    pattern = {"direction": "NEUTRAL", "support": 90.0, "resistance": 110.0}
    levels = _build_trade_levels(pattern)
    assert levels["confirm"] is None
    assert levels["targets"] == []
