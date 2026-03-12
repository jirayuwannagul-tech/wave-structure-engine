from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from analysis.wave_position import WavePosition


@dataclass
class MTFAlignmentResult:
    state: str
    biases: Dict[str, str]
    message: str


def evaluate_mtf_alignment(positions: Dict[str, WavePosition]) -> MTFAlignmentResult:
    biases = {tf: pos.bias for tf, pos in positions.items()}

    unique_biases = set(biases.values())

    if unique_biases == {"BULLISH"}:
        return MTFAlignmentResult(
            state="full_bullish_alignment",
            biases=biases,
            message="all tracked timeframes are bullish",
        )

    if unique_biases == {"BEARISH"}:
        return MTFAlignmentResult(
            state="full_bearish_alignment",
            biases=biases,
            message="all tracked timeframes are bearish",
        )

    return MTFAlignmentResult(
        state="mixed_alignment",
        biases=biases,
        message="timeframes are mixed",
    )


if __name__ == "__main__":
    positions = {
        "1W": WavePosition(structure="ABC_CORRECTION", position="WAVE_C_END", bias="BEARISH", confidence="medium"),
        "1D": WavePosition(structure="ABC_CORRECTION", position="WAVE_C_END", bias="BULLISH", confidence="medium"),
        "4H": WavePosition(structure="ABC_CORRECTION", position="WAVE_C_END", bias="BULLISH", confidence="medium"),
    }

    print(evaluate_mtf_alignment(positions))