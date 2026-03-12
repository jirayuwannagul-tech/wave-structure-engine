from analysis.wave_probability import normalize_probabilities, rank_wave_counts


class DummyPattern:
    def __init__(self, direction: str):
        self.direction = direction


def test_normalize_probabilities_applies_pattern_bonus():
    counts = [
        {
            "type": "IMPULSE",
            "pattern": DummyPattern("bullish"),
            "confidence": 0.80,
        },
        {
            "type": "TRIANGLE",
            "pattern": DummyPattern("bullish"),
            "confidence": 0.80,
        },
    ]

    normalized = normalize_probabilities(counts)

    assert normalized[0]["adjusted_confidence"] > normalized[1]["adjusted_confidence"]
    assert normalized[0]["probability"] > normalized[1]["probability"]


def test_rank_wave_counts_sorts_by_probability_desc():
    counts = [
        {
            "type": "ABC_CORRECTION",
            "pattern": DummyPattern("bullish"),
            "confidence": 0.78,
        },
        {
            "type": "IMPULSE",
            "pattern": DummyPattern("bullish"),
            "confidence": 0.78,
        },
    ]

    ranked = rank_wave_counts(counts)

    assert ranked[0]["type"] == "IMPULSE"
    assert ranked[0]["probability"] >= ranked[1]["probability"]
