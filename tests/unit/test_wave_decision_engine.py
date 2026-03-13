from analysis.wave_decision_engine import (
    choose_primary_and_alternate,
    build_wave_summary,
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
        {"pattern_type": "IMPULSE", "direction": "BULLISH", "similarity_score": 0.8},
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
