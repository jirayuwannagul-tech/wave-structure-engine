from analysis.pattern_similarity_engine import (
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