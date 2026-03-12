from analysis.main_alternate_count import CountCandidate, rank_counts
from analysis.rule_validator import RuleValidationResult


def test_rank_counts_returns_main_and_alternate():
    c1 = CountCandidate(
        name="impulse_main",
        pattern_type="impulse",
        pattern={"id": 1},
        validation=RuleValidationResult(
            pattern_type="impulse",
            is_valid=True,
            message="valid",
        ),
        fib_score=20.0,
        structure_score=25.0,
    )

    c2 = CountCandidate(
        name="abc_alt",
        pattern_type="abc",
        pattern={"id": 2},
        validation=RuleValidationResult(
            pattern_type="abc",
            is_valid=True,
            message="valid",
        ),
        fib_score=15.0,
        structure_score=20.0,
    )

    ranking = rank_counts([c2, c1])

    assert ranking.main_count is not None
    assert ranking.alternate_count is not None
    assert ranking.main_count.name == "impulse_main"
    assert ranking.alternate_count.name == "abc_alt"
    assert len(ranking.all_counts) == 2