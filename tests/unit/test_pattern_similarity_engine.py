from analysis.pattern_similarity_engine import (
    build_pattern_report,
    build_pattern_label,
    compute_similarity_score,
)


def test_build_pattern_label():
    label = build_pattern_label(
        pattern_type="IMPULSE",
        direction="bullish",
        timeframe="1D",
    )

    assert label["family"] == "motive"
    assert label["subtype"] == "standard_impulse"
    assert label["direction"] == "BULLISH"
    assert label["degree"] == "intermediate"


def test_compute_similarity_score():
    score = compute_similarity_score(0.9, 0.5)

    assert score > 0
    assert score <= 1


def test_build_pattern_report_preserves_indicator_context():
    pattern = {
        "type": "ABC_CORRECTION",
        "pattern": type("Pattern", (), {"direction": "bullish"})(),
        "confidence": 0.8,
        "probability": 0.4,
        "indicator_context": {"rsi_divergence": "BULLISH_RSI_DIVERGENCE"},
    }

    report = build_pattern_report(pattern, "4H")

    assert report["indicator_context"]["rsi_divergence"] == "BULLISH_RSI_DIVERGENCE"
