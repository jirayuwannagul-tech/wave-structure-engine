"""Wave Duration / Time Analysis for Elliott Wave Engine.

Measures how many bars each completed wave took, then projects
Fibonacci time targets for the wave currently building.

Fibonacci time ratios:
  Wave 2 duration ≈ 0.382–0.618 × Wave 1 duration
  Wave 3 duration ≈ 1.000–2.618 × Wave 1 duration  (often longest)
  Wave 4 duration ≈ 0.382–0.618 × Wave 3 duration  (often ≈ Wave 2)
  Wave 5 duration ≈ 0.618–1.000 × Wave 1 duration  (often ≈ Wave 1)

Overdue detection:
  If current wave has already exceeded its upper Fibonacci time target,
  it may be exhausted and about to reverse.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from analysis.pivot_detector import Pivot


@dataclass
class WaveDuration:
    wave_number: str          # "1","2","3","4","5" or "A","B","C"
    bars: int                 # number of bars from start to end pivot
    start_index: int
    end_index: int
    start_price: float
    end_price: float


@dataclass
class WaveTimeProjection:
    building_wave: str                          # wave currently forming
    expected_min_bars: int                      # lower bound
    expected_max_bars: int                      # upper bound
    elapsed_bars: int                           # bars since wave started
    is_overdue: bool                            # elapsed > expected_max
    progress_pct: float                         # elapsed / expected_max (0.0–1.0+)
    fib_time_targets: dict[str, int] = field(default_factory=dict)  # {"0.618": 14, ...}


_IMPULSE_TIME_RATIOS: dict[str, list[float]] = {
    "2": [0.236, 0.382, 0.618],          # W2 is usually shorter than W1
    "3": [1.000, 1.618, 2.618],          # W3 is usually longest
    "4": [0.382, 0.618, 1.000],          # W4 ≈ W2 in time
    "5": [0.618, 1.000, 1.618],          # W5 often equals W1
}

_CORRECTIVE_TIME_RATIOS: dict[str, list[float]] = {
    "B": [0.382, 0.618, 1.000],          # B retracement of A
    "C": [1.000, 1.272, 1.618],          # C extension
}


def _bars_between(p1: Pivot, p2: Pivot) -> int:
    """Number of bars (candles) between two pivots."""
    return max(0, p2.index - p1.index)


def measure_impulse_wave_durations(pivots: list[Pivot]) -> list[WaveDuration]:
    """Measure duration of each completed impulse wave from pivot list.

    Expects a bullish sequence [L,H,L,H,L,H] or bearish [H,L,H,L,H,L].
    Returns durations for W1–W5 if all 6 pivots are present.
    """
    if len(pivots) < 2:
        return []

    durations = []
    wave_labels = ["1", "2", "3", "4", "5"]

    for i in range(min(len(pivots) - 1, 5)):
        p_start = pivots[i]
        p_end = pivots[i + 1]
        durations.append(WaveDuration(
            wave_number=wave_labels[i],
            bars=_bars_between(p_start, p_end),
            start_index=p_start.index,
            end_index=p_end.index,
            start_price=float(p_start.price),
            end_price=float(p_end.price),
        ))

    return durations


def project_wave_time(
    completed_durations: list[WaveDuration],
    building_wave: str,
    current_bar_index: int,
    wave_start_index: int,
) -> WaveTimeProjection | None:
    """Project how long the current wave should take.

    Args:
        completed_durations: WaveDuration list for already-finished waves.
        building_wave: "2","3","4","5" (impulse) or "B","C" (corrective).
        current_bar_index: current candle index in the DataFrame.
        wave_start_index: bar index where the current wave began.

    Returns:
        WaveTimeProjection or None if insufficient data.
    """
    ratios = _IMPULSE_TIME_RATIOS.get(building_wave) or _CORRECTIVE_TIME_RATIOS.get(building_wave)
    if ratios is None or not completed_durations:
        return None

    # Reference wave for time projection
    ref_map = {"2": "1", "3": "1", "4": "3", "5": "1", "B": "A", "C": "A"}
    ref_wave = ref_map.get(building_wave, "1")

    ref_duration = next(
        (d for d in completed_durations if d.wave_number == ref_wave), None
    )
    if ref_duration is None or ref_duration.bars == 0:
        return None

    fib_targets = {
        str(round(r, 3)): max(1, round(ref_duration.bars * r))
        for r in ratios
    }

    elapsed = max(0, current_bar_index - wave_start_index)
    expected_min = min(fib_targets.values())
    expected_max = max(fib_targets.values())
    is_overdue = elapsed > expected_max
    progress_pct = round(elapsed / expected_max, 3) if expected_max > 0 else 0.0

    return WaveTimeProjection(
        building_wave=building_wave,
        expected_min_bars=expected_min,
        expected_max_bars=expected_max,
        elapsed_bars=elapsed,
        is_overdue=is_overdue,
        progress_pct=progress_pct,
        fib_time_targets=fib_targets,
    )


def score_time_confidence(projection: WaveTimeProjection | None) -> float:
    """Adjust confidence based on wave time progress.

    Returns an adjustment between -0.05 and +0.03:
    - Wave within expected time window: +0.02
    - Wave just entering window (fresh signal): +0.03
    - Wave overdue (>100% of expected max): -0.02
    - Wave very overdue (>150%): -0.05
    """
    if projection is None:
        return 0.0

    p = projection.progress_pct

    if p > 1.5:
        return -0.05   # very overdue — wave may have already reversed
    if p > 1.0:
        return -0.02   # overdue
    if 0.382 <= p <= 0.786:
        return 0.02    # healthy midpoint of expected range
    if p < 0.382:
        return 0.03    # early entry — maximum opportunity
    return 0.0         # near end of range — neutral
