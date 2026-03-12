from analysis.pattern_labeler import label_patterns


class DummyPattern:
    def __init__(self, direction: str):
        self.direction = direction


def test_label_patterns_sorted_by_similarity():
    patterns = [
        {
            "type": "ABC_CORRECTION",
            "pattern": DummyPattern("bullish"),
            "confidence": 0.8,
            "probability": 0.4,
        },
        {
            "type": "IMPULSE",
            "pattern": DummyPattern("bullish"),
            "confidence": 0.9,
            "probability": 0.6,
        },
    ]

    reports = label_patterns(patterns, "1D")

    assert len(reports) == 2
    assert reports[0]["similarity_score"] >= reports[1]["similarity_score"]
    assert reports[0]["family"] is not None