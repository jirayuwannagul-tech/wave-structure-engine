from analysis.wave_confidence import compute_wave_confidence


def test_wave_confidence_range():
    score = compute_wave_confidence(
        rule_score=1,
        fib_score=0.8,
        structure_score=1,
        momentum_score=0.7,
    )

    assert 0 <= score <= 1


def test_wave_confidence_high_score():
    score = compute_wave_confidence(
        rule_score=1,
        fib_score=1,
        structure_score=1,
        momentum_score=1,
    )

    assert score >= 0.9