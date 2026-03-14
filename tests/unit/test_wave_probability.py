import pytest

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


# ── _score_alternation_bonus (lines 44, 47) ───────────────────────────────────

class _ImpulsePattern:
    def __init__(self, w2, w4):
        self.wave2_retrace_ratio = w2
        self.wave4_retrace_ratio = w4


def test_alternation_bonus_good():
    """W2 sharp (>0.618) + W4 flat (<0.382) → +0.02 bonus (line 44)."""
    pattern = _ImpulsePattern(w2=0.70, w4=0.30)
    counts = [{"type": "IMPULSE", "pattern": pattern, "confidence": 0.80}]
    result = normalize_probabilities(counts)
    # Bonus = _pattern_bonus(IMPULSE)=0.005 + _direction_bonus=0.0 + alternation=0.02
    assert result[0]["adjusted_confidence"] == pytest.approx(0.80 + 0.005 + 0.02, abs=1e-4)


def test_alternation_bonus_poor():
    """W2 sharp + W4 sharp → -0.02 penalty (line 47)."""
    pattern = _ImpulsePattern(w2=0.70, w4=0.70)
    counts = [{"type": "IMPULSE", "pattern": pattern, "confidence": 0.80}]
    result = normalize_probabilities(counts)
    # Bonus = 0.005 + 0.0 - 0.02 = -0.015; max(0, 0.8-0.015) = 0.785
    assert result[0]["adjusted_confidence"] == pytest.approx(max(0.0, 0.80 + 0.005 - 0.02), abs=1e-4)


def test_alternation_bonus_flat_and_flat():
    """W2 flat + W4 flat → -0.02 penalty."""
    pattern = _ImpulsePattern(w2=0.30, w4=0.30)
    counts = [{"type": "IMPULSE", "pattern": pattern, "confidence": 0.80}]
    result = normalize_probabilities(counts)
    assert result[0]["adjusted_confidence"] == pytest.approx(max(0.0, 0.80 + 0.005 - 0.02), abs=1e-4)


def test_alternation_bonus_indeterminate():
    """Both ratios in 0.382-0.618 zone → 0.0 bonus."""
    pattern = _ImpulsePattern(w2=0.50, w4=0.50)
    counts = [{"type": "IMPULSE", "pattern": pattern, "confidence": 0.80}]
    result = normalize_probabilities(counts)
    assert result[0]["adjusted_confidence"] == pytest.approx(0.80 + 0.005, abs=1e-4)


# ── total==0 branch (lines 89-91) ─────────────────────────────────────────────

def test_normalize_probabilities_zero_total():
    """All adjusted_confidences clamped to 0 → probability=0.0 for all (lines 89-91)."""
    counts = [
        {"type": "TRIANGLE", "pattern": None, "confidence": 0.0},
    ]
    result = normalize_probabilities(counts)
    assert result[0]["probability"] == 0.0
