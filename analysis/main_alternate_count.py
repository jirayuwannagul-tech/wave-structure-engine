from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from analysis.rule_validator import RuleValidationResult


@dataclass
class CountCandidate:
    name: str
    pattern_type: str
    pattern: Any
    validation: RuleValidationResult
    fib_score: float
    structure_score: float

    @property
    def total_score(self) -> float:
        valid_bonus = 100.0 if self.validation.is_valid else 0.0
        return valid_bonus + self.fib_score + self.structure_score


@dataclass
class CountRanking:
    main_count: Optional[CountCandidate]
    alternate_count: Optional[CountCandidate]
    all_counts: List[CountCandidate]


def rank_counts(candidates: List[CountCandidate]) -> CountRanking:
    if not candidates:
        return CountRanking(
            main_count=None,
            alternate_count=None,
            all_counts=[],
        )

    ranked = sorted(candidates, key=lambda x: x.total_score, reverse=True)

    main_count = ranked[0] if len(ranked) >= 1 else None
    alternate_count = ranked[1] if len(ranked) >= 2 else None

    return CountRanking(
        main_count=main_count,
        alternate_count=alternate_count,
        all_counts=ranked,
    )


if __name__ == "__main__":
    import pandas as pd
    from analysis.pivot_detector import detect_pivots
    from analysis.rule_validator import validate_abc_rules, validate_impulse_rules
    from analysis.wave_detector import detect_latest_abc, detect_latest_impulse

    df = pd.read_csv("data/BTCUSDT_1d.csv")
    df["open_time"] = pd.to_datetime(df["open_time"])

    pivots = detect_pivots(df)

    candidates: List[CountCandidate] = []

    impulse = detect_latest_impulse(pivots)
    if impulse is not None:
        candidates.append(
            CountCandidate(
                name="latest_impulse",
                pattern_type="impulse",
                pattern=impulse,
                validation=validate_impulse_rules(impulse),
                fib_score=20.0,
                structure_score=25.0,
            )
        )

    abc = detect_latest_abc(pivots)
    if abc is not None:
        candidates.append(
            CountCandidate(
                name="latest_abc",
                pattern_type="abc",
                pattern=abc,
                validation=validate_abc_rules(abc),
                fib_score=15.0,
                structure_score=20.0,
            )
        )

    ranking = rank_counts(candidates)

    print("MAIN:", ranking.main_count)
    print("ALT :", ranking.alternate_count)