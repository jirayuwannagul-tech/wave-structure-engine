from analysis.multi_count_engine import generate_wave_counts
from analysis.rule_validator import RuleValidationResult


class DummyABC:
    direction = "bullish"
    ab_length = 10.0
    bc_length = 8.0
    bc_vs_ab_ratio = 0.8


class DummyImpulse:
    direction = "bearish"
    wave1_length = 10.0
    wave2_length = 5.0
    wave3_length = 20.0
    wave4_length = 6.0
    wave5_length = 12.0
    wave2_retrace_ratio = 0.5
    wave4_retrace_ratio = 0.3
    wave3_vs_wave1_ratio = 2.0
    wave5_vs_wave1_ratio = 1.2


def test_generate_wave_counts_returns_list():
    pivots = []

    counts = generate_wave_counts(pivots)

    assert isinstance(counts, list)


def test_generate_wave_counts_sorted_by_confidence(monkeypatch):
    dummy_abc = DummyABC()
    dummy_impulse = DummyImpulse()

    def fake_detect_abc(pivots):
        return dummy_abc

    def fake_detect_impulse(pivots):
        return dummy_impulse

    def fake_validate_pattern_rules(pattern_type, pattern):
        return RuleValidationResult(
            pattern_type=pattern_type.lower(),
            is_valid=True,
            correction_rule=True,
            message=f"valid {pattern_type.lower()}",
        )

    monkeypatch.setattr(
        "analysis.multi_count_engine.detect_latest_abc", fake_detect_abc
    )
    monkeypatch.setattr(
        "analysis.multi_count_engine.detect_latest_impulse", fake_detect_impulse
    )
    monkeypatch.setattr(
        "analysis.multi_count_engine.validate_pattern_rules", fake_validate_pattern_rules
    )

    counts = generate_wave_counts([])

    assert len(counts) >= 1
    assert counts[0]["confidence"] >= counts[-1]["confidence"]
