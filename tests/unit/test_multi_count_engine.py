import pandas as pd

from analysis.multi_count_engine import generate_wave_counts
from analysis.pivot_detector import Pivot
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


def test_generate_wave_counts_attaches_indicator_context(monkeypatch):
    dummy_abc = DummyABC()

    def fake_detect_abc(pivots):
        return dummy_abc

    def fake_validate_pattern_rules(pattern_type, pattern):
        return RuleValidationResult(
            pattern_type=pattern_type.lower(),
            is_valid=True,
            correction_rule=True,
            message=f"valid {pattern_type.lower()}",
        )

    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_abc", fake_detect_abc)
    monkeypatch.setattr("analysis.multi_count_engine.detect_latest_impulse", lambda pivots: None)
    monkeypatch.setattr(
        "analysis.multi_count_engine.validate_pattern_rules",
        fake_validate_pattern_rules,
    )

    df = pd.DataFrame(
        {
            "close": [100.0] * 19 + [110.0],
            "high": [101.0] * 20,
            "low": [99.0] * 20,
            "volume": [1000.0] * 20,
            "ema50": [99.0] * 19 + [100.0],
            "rsi": [50.0] * 18 + [30.0, 38.0],
            "atr": [10.0] * 19 + [12.0],
        }
    )
    pivots = [
        Pivot(index=18, price=100.0, type="L", timestamp=pd.Timestamp("2026-01-01")),
        Pivot(index=19, price=95.0, type="L", timestamp=pd.Timestamp("2026-01-02")),
    ]

    counts = generate_wave_counts(pivots, df=df)

    assert counts
    assert counts[0]["indicator_context"]["rsi_divergence"] == "BULLISH_RSI_DIVERGENCE"
