from analysis.main_alternate_count import CountCandidate, CountRanking, rank_counts
from analysis.rule_validator import RuleValidationResult


def _make_candidate(name: str, fib: float, structure: float, is_valid: bool = True):
    return CountCandidate(
        name=name,
        pattern_type="impulse",
        pattern={"id": name},
        validation=RuleValidationResult(
            pattern_type="impulse",
            is_valid=is_valid,
            message="valid" if is_valid else "invalid",
        ),
        fib_score=fib,
        structure_score=structure,
    )


def test_rank_counts_returns_main_and_alternate():
    c1 = CountCandidate(
        name="impulse_main",
        pattern_type="impulse",
        pattern={"id": 1},
        validation=RuleValidationResult(pattern_type="impulse", is_valid=True, message="valid"),
        fib_score=20.0,
        structure_score=25.0,
    )
    c2 = CountCandidate(
        name="abc_alt",
        pattern_type="abc",
        pattern={"id": 2},
        validation=RuleValidationResult(pattern_type="abc", is_valid=True, message="valid"),
        fib_score=15.0,
        structure_score=20.0,
    )

    ranking = rank_counts([c2, c1])

    assert ranking.main_count is not None
    assert ranking.alternate_count is not None
    assert ranking.main_count.name == "impulse_main"
    assert ranking.alternate_count.name == "abc_alt"
    assert len(ranking.all_counts) == 2


def test_rank_counts_empty():
    ranking = rank_counts([])
    assert ranking.main_count is None
    assert ranking.alternate_count is None
    assert ranking.all_counts == []


def test_rank_counts_single_candidate():
    c = _make_candidate("only", fib=10.0, structure=10.0)
    ranking = rank_counts([c])
    assert ranking.main_count is not None
    assert ranking.alternate_count is None


def test_total_score_valid_gets_bonus():
    valid = _make_candidate("valid", fib=10.0, structure=10.0, is_valid=True)
    invalid = _make_candidate("invalid", fib=50.0, structure=50.0, is_valid=False)
    # valid gets 100 bonus → 120 total; invalid gets 0 → 100 total
    assert valid.total_score > invalid.total_score


def test_rank_counts_sorted_by_score():
    low = _make_candidate("low", fib=5.0, structure=5.0)
    high = _make_candidate("high", fib=30.0, structure=30.0)
    mid = _make_candidate("mid", fib=15.0, structure=15.0)
    ranking = rank_counts([low, mid, high])
    assert ranking.main_count.name == "high"
    assert ranking.alternate_count.name == "mid"


def test_count_ranking_all_counts_length():
    candidates = [_make_candidate(f"c{i}", fib=float(i), structure=float(i)) for i in range(5)]
    ranking = rank_counts(candidates)
    assert len(ranking.all_counts) == 5


def test_total_score_invalid_no_bonus():
    c = _make_candidate("inv", fib=0.0, structure=0.0, is_valid=False)
    assert c.total_score == 0.0