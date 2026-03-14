"""Detects which Elliott Wave is currently in progress (being formed).

Scans recent pivots to determine if price is building an impulse or
corrective wave, and estimates Fibonacci targets for the wave's completion.

Algorithm:
    1. Scan last N pivots (N=5 down to 2) for partial impulse sequences
    2. Validate applicable Elliott rules for completed sub-waves
    3. Score confidence based on rule compliance and pivot count
    4. Return InProgressWave with Fibonacci targets and invalidation level

Partial bullish impulse sequences (pivot types):
    [L, H]             → Wave 1 done,    building Wave 2 ↓
    [L, H, L]          → Waves 1+2 done, building Wave 3 ↑
    [L, H, L, H]       → Waves 1-3 done, building Wave 4 ↓
    [L, H, L, H, L]    → Waves 1-4 done, building Wave 5 ↑

Reversed for bearish impulse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from analysis.pivot_detector import Pivot
from analysis.wave_timer import (
    WaveTimeProjection,
    measure_impulse_wave_durations,
    project_wave_time,
    score_time_confidence,
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class InProgressWave:
    """Represents an Elliott Wave structure that is currently forming."""

    structure: str       # "IMPULSE" or "CORRECTION"
    direction: str       # "bullish" or "bearish"
    wave_number: str     # "2","3","4","5" for impulse; "A","B","C" for correction
    completed_waves: int  # how many waves are confirmed complete

    pivots: list[Pivot]         # confirmed pivots in this structure
    last_pivot: Pivot            # most recent confirmed turning point

    current_wave_start: float   # price where current wave began
    invalidation: float         # price that would invalidate this count

    fib_targets: dict[str, float] = field(default_factory=dict)
    rule_checks: dict[str, bool] = field(default_factory=dict)
    is_valid: bool = True
    confidence: float = 0.5
    time_projection: WaveTimeProjection | None = None

    @property
    def current_wave_direction(self) -> str:
        """Direction of the wave being built (not the overall structure)."""
        n = self.wave_number
        if self.direction == "bullish":
            # Odd waves move up, even waves correct down
            return "bullish" if n in ("1", "3", "5") else "bearish"
        else:
            # Odd waves move down, even waves correct up
            return "bearish" if n in ("1", "3", "5") else "bullish"

    @property
    def label(self) -> str:
        arrow = "↑" if self.current_wave_direction == "bullish" else "↓"
        return f"Building Wave {self.wave_number} {arrow}"

    @property
    def summary(self) -> str:
        rules_ok = all(self.rule_checks.values()) if self.rule_checks else True
        return (
            f"{self.structure} | Wave {self.wave_number} forming | "
            f"{self.direction} | rules_ok={rules_ok} | conf={self.confidence:.2f}"
        )


# ---------------------------------------------------------------------------
# Pivot type sequences for partial patterns
# ---------------------------------------------------------------------------

_BULLISH_SEQUENCES: dict[int, list[str]] = {
    2: ["L", "H"],
    3: ["L", "H", "L"],
    4: ["L", "H", "L", "H"],
    5: ["L", "H", "L", "H", "L"],
}

_BEARISH_SEQUENCES: dict[int, list[str]] = {
    2: ["H", "L"],
    3: ["H", "L", "H"],
    4: ["H", "L", "H", "L"],
    5: ["H", "L", "H", "L", "H"],
}

_BULLISH_CORRECTIVE_SEQUENCES: dict[int, list[str]] = {
    # Bullish ABC: ends at C (bullish rebound expected)
    2: ["H", "L"],         # Wave A done (down), building Wave B (up)
    3: ["H", "L", "H"],    # Waves A+B done, building Wave C (down) — expect bounce at C
}

_BEARISH_CORRECTIVE_SEQUENCES: dict[int, list[str]] = {
    2: ["L", "H"],         # Wave A done (up), building Wave B (down)
    3: ["L", "H", "L"],    # Waves A+B done, building Wave C (up) — expect reversal at C
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wave_number_from_pivot_count(n: int) -> str:
    """Map confirmed pivot count → wave number currently being built."""
    # n confirmed pivots means n waves completed (each pivot ends a wave)
    # except we start counting from wave 1:
    # 2 pivots: wave 1 start + wave 1 end → wave 1 done → building wave 2
    # 3 pivots: waves 1+2 done → building wave 3
    return str(min(n, 5))


def _validate_bullish_partial(
    pivots: list[Pivot],
) -> tuple[bool, dict[str, bool]]:
    """Validate applicable Elliott rules for a partial bullish impulse."""
    n = len(pivots)
    checks: dict[str, bool] = {}

    if n >= 3:
        # Rule 1: Wave 2 never retraces beyond Wave 1 origin
        # p0=L(W1_start), p1=H(W1_end), p2=L(W2_end) → p2.price > p0.price
        checks["rule1_w2_not_beyond_w1"] = pivots[2].price > pivots[0].price

    if n >= 4:
        # Rule 2 (partial): Wave 3 should not be shorter than Wave 1
        # Can't fully check without Wave 5, but w3 >= w1 is a necessary condition
        w1 = pivots[1].price - pivots[0].price
        w3 = pivots[3].price - pivots[2].price
        checks["rule2_w3_not_shorter_than_w1"] = w3 > 0 and w3 >= w1

    if n >= 5:
        # Rule 3: Wave 4 never enters Wave 1 price territory
        # p4=L(W4_end) must be above p1=H(W1_end)
        checks["rule3_w4_no_overlap"] = pivots[4].price > pivots[1].price

    is_valid = all(checks.values()) if checks else True
    return is_valid, checks


def _validate_bearish_partial(
    pivots: list[Pivot],
) -> tuple[bool, dict[str, bool]]:
    """Validate applicable Elliott rules for a partial bearish impulse."""
    n = len(pivots)
    checks: dict[str, bool] = {}

    if n >= 3:
        # Rule 1: Wave 2 never retraces beyond Wave 1 origin
        # p0=H(W1_start), p1=L(W1_end), p2=H(W2_end) → p2.price < p0.price
        checks["rule1_w2_not_beyond_w1"] = pivots[2].price < pivots[0].price

    if n >= 4:
        # Rule 2 (partial): Wave 3 not shorter than Wave 1
        w1 = pivots[0].price - pivots[1].price
        w3 = pivots[2].price - pivots[3].price
        checks["rule2_w3_not_shorter_than_w1"] = w3 > 0 and w3 >= w1

    if n >= 5:
        # Rule 3: Wave 4 never enters Wave 1 price territory
        # p4=H(W4_end) must be below p1=L(W1_end)
        checks["rule3_w4_no_overlap"] = pivots[4].price < pivots[1].price

    is_valid = all(checks.values()) if checks else True
    return is_valid, checks


def _bullish_fib_targets(pivots: list[Pivot]) -> dict[str, float]:
    """Fibonacci targets for the wave currently being built (bullish impulse)."""
    n = len(pivots)
    targets: dict[str, float] = {}

    if n == 2:
        # Building Wave 2: retracement targets of Wave 1
        w1_start = pivots[0].price
        w1_end = pivots[1].price
        w1_size = w1_end - w1_start
        targets["0.382"] = round(w1_end - w1_size * 0.382, 2)
        targets["0.500"] = round(w1_end - w1_size * 0.500, 2)
        targets["0.618"] = round(w1_end - w1_size * 0.618, 2)
        targets["0.786"] = round(w1_end - w1_size * 0.786, 2)

    elif n == 3:
        # Building Wave 3: extension from Wave 2 end
        w1_size = pivots[1].price - pivots[0].price
        w2_end = pivots[2].price
        targets["1.000"] = round(w2_end + w1_size * 1.000, 2)
        targets["1.618"] = round(w2_end + w1_size * 1.618, 2)
        targets["2.618"] = round(w2_end + w1_size * 2.618, 2)

    elif n == 4:
        # Building Wave 4: retracement of Wave 3
        w3_start = pivots[2].price
        w3_end = pivots[3].price
        w3_size = w3_end - w3_start
        targets["0.236"] = round(w3_end - w3_size * 0.236, 2)
        targets["0.382"] = round(w3_end - w3_size * 0.382, 2)
        targets["0.500"] = round(w3_end - w3_size * 0.500, 2)
        targets["0.618"] = round(w3_end - w3_size * 0.618, 2)

    elif n == 5:
        # Building Wave 5: from Wave 4 end
        w1_size = pivots[1].price - pivots[0].price
        w3_size = pivots[3].price - pivots[2].price
        w4_end = pivots[4].price
        targets["w1_equal"] = round(w4_end + w1_size, 2)
        targets["0.618xW1W3"] = round(w4_end + 0.618 * (w1_size + w3_size), 2)
        targets["1.272xW1"] = round(w4_end + w1_size * 1.272, 2)

    return targets


def _bearish_fib_targets(pivots: list[Pivot]) -> dict[str, float]:
    """Fibonacci targets for the wave currently being built (bearish impulse)."""
    n = len(pivots)
    targets: dict[str, float] = {}

    if n == 2:
        # Building Wave 2: retracement targets (upward) of Wave 1 (downward)
        w1_start = pivots[0].price
        w1_end = pivots[1].price
        w1_size = w1_start - w1_end
        targets["0.382"] = round(w1_end + w1_size * 0.382, 2)
        targets["0.500"] = round(w1_end + w1_size * 0.500, 2)
        targets["0.618"] = round(w1_end + w1_size * 0.618, 2)
        targets["0.786"] = round(w1_end + w1_size * 0.786, 2)

    elif n == 3:
        # Building Wave 3: extension downward from Wave 2 end
        w1_size = pivots[0].price - pivots[1].price
        w2_end = pivots[2].price
        targets["1.000"] = round(w2_end - w1_size * 1.000, 2)
        targets["1.618"] = round(w2_end - w1_size * 1.618, 2)
        targets["2.618"] = round(w2_end - w1_size * 2.618, 2)

    elif n == 4:
        # Building Wave 4: retracement (upward) of Wave 3 (downward)
        w3_start = pivots[2].price
        w3_end = pivots[3].price
        w3_size = w3_start - w3_end
        targets["0.236"] = round(w3_end + w3_size * 0.236, 2)
        targets["0.382"] = round(w3_end + w3_size * 0.382, 2)
        targets["0.500"] = round(w3_end + w3_size * 0.500, 2)
        targets["0.618"] = round(w3_end + w3_size * 0.618, 2)

    elif n == 5:
        # Building Wave 5: final leg downward
        w1_size = pivots[0].price - pivots[1].price
        w3_size = pivots[2].price - pivots[3].price
        w4_end = pivots[4].price
        targets["w1_equal"] = round(w4_end - w1_size, 2)
        targets["0.618xW1W3"] = round(w4_end - 0.618 * (w1_size + w3_size), 2)
        targets["1.272xW1"] = round(w4_end - w1_size * 1.272, 2)

    return targets


def _bullish_invalidation(pivots: list[Pivot]) -> float:
    """Price that invalidates the bullish impulse count."""
    n = len(pivots)
    if n <= 3:
        return pivots[0].price   # Wave 1 start — wave 2 cannot breach this
    return pivots[1].price       # Wave 1 end — wave 4 cannot overlap (rule 3)


def _bearish_invalidation(pivots: list[Pivot]) -> float:
    """Price that invalidates the bearish impulse count."""
    n = len(pivots)
    if n <= 3:
        return pivots[0].price   # Wave 1 start
    return pivots[1].price       # Wave 1 end


def _confidence(checks: dict[str, bool], n_pivots: int) -> float:
    """Derive confidence score from rule checks and pivot count."""
    base = {2: 0.35, 3: 0.45, 4: 0.55, 5: 0.65}.get(n_pivots, 0.40)
    if not checks:
        return base
    rule_ratio = sum(1 for v in checks.values() if v) / len(checks)
    return round(base * (0.5 + 0.5 * rule_ratio), 3)


# ---------------------------------------------------------------------------
# Core builders
# ---------------------------------------------------------------------------


def _try_partial_bullish_impulse(pivots: list[Pivot]) -> Optional[InProgressWave]:
    n = len(pivots)
    if n < 2 or n > 5:
        return None

    if [p.type for p in pivots] != _BULLISH_SEQUENCES[n]:
        return None

    # Monotonic direction check:
    # i=1 (H): first H above first L
    # i>=2: each pivot above the previous pivot of the SAME type (higher highs, higher lows)
    for i in range(1, n):
        curr = pivots[i]
        if i == 1:
            if curr.price <= pivots[0].price:
                return None
        else:
            if curr.price <= pivots[i - 2].price:
                return None

    is_valid, rule_checks = _validate_bullish_partial(pivots)
    if not is_valid:
        return None

    wave_number = _wave_number_from_pivot_count(n)

    durations = measure_impulse_wave_durations(pivots)
    time_proj = project_wave_time(
        completed_durations=durations,
        building_wave=wave_number,
        current_bar_index=pivots[-1].index,
        wave_start_index=pivots[-1].index,
    )
    time_adj = score_time_confidence(time_proj)
    final_confidence = round(min(0.95, _confidence(rule_checks, n) + time_adj), 3)

    return InProgressWave(
        structure="IMPULSE",
        direction="bullish",
        wave_number=wave_number,
        completed_waves=n - 1,
        pivots=list(pivots),
        last_pivot=pivots[-1],
        current_wave_start=pivots[-1].price,
        invalidation=_bullish_invalidation(pivots),
        fib_targets=_bullish_fib_targets(pivots),
        rule_checks=rule_checks,
        is_valid=is_valid,
        confidence=final_confidence,
        time_projection=time_proj,
    )


def _try_partial_bearish_impulse(pivots: list[Pivot]) -> Optional[InProgressWave]:
    n = len(pivots)
    if n < 2 or n > 5:
        return None

    if [p.type for p in pivots] != _BEARISH_SEQUENCES[n]:
        return None

    # Monotonic direction check:
    # i=1 (L): first L below first H
    # i>=2: each pivot below the previous pivot of the SAME type (lower highs, lower lows)
    for i in range(1, n):
        curr = pivots[i]
        if i == 1:
            if curr.price >= pivots[0].price:
                return None
        else:
            if curr.price >= pivots[i - 2].price:
                return None

    is_valid, rule_checks = _validate_bearish_partial(pivots)
    if not is_valid:
        return None

    wave_number = _wave_number_from_pivot_count(n)

    durations = measure_impulse_wave_durations(pivots)
    time_proj = project_wave_time(
        completed_durations=durations,
        building_wave=wave_number,
        current_bar_index=pivots[-1].index,
        wave_start_index=pivots[-1].index,
    )
    time_adj = score_time_confidence(time_proj)
    final_confidence = round(min(0.95, _confidence(rule_checks, n) + time_adj), 3)

    return InProgressWave(
        structure="IMPULSE",
        direction="bearish",
        wave_number=wave_number,
        completed_waves=n - 1,
        pivots=list(pivots),
        last_pivot=pivots[-1],
        current_wave_start=pivots[-1].price,
        invalidation=_bearish_invalidation(pivots),
        fib_targets=_bearish_fib_targets(pivots),
        rule_checks=rule_checks,
        is_valid=is_valid,
        confidence=final_confidence,
        time_projection=time_proj,
    )


# ---------------------------------------------------------------------------
# Corrective wave helpers
# ---------------------------------------------------------------------------


def _bullish_corrective_targets(pivots: list[Pivot]) -> dict[str, float]:
    """Fibonacci targets for bullish ABC correction."""
    n = len(pivots)
    targets: dict[str, float] = {}

    if n == 2:
        # Building Wave B: retracement of Wave A (A went down)
        a_start = pivots[0].price  # H (top of A)
        a_end = pivots[1].price    # L (bottom of A)
        a_size = a_start - a_end
        targets["0.382"] = round(a_end + a_size * 0.382, 2)  # B targets
        targets["0.500"] = round(a_end + a_size * 0.500, 2)
        targets["0.618"] = round(a_end + a_size * 0.618, 2)
        targets["0.786"] = round(a_end + a_size * 0.786, 2)

    elif n == 3:
        # Building Wave C: extension from Wave B end (C goes DOWN)
        a_start = pivots[0].price
        a_end = pivots[1].price
        b_end = pivots[2].price
        a_size = a_start - a_end
        targets["C=A"] = round(b_end - a_size * 1.000, 2)      # C equals A
        targets["C=1.272A"] = round(b_end - a_size * 1.272, 2) # C = 1.272×A
        targets["C=1.618A"] = round(b_end - a_size * 1.618, 2) # C = 1.618×A

    return targets


def _bearish_corrective_targets(pivots: list[Pivot]) -> dict[str, float]:
    """Fibonacci targets for bearish ABC correction."""
    n = len(pivots)
    targets: dict[str, float] = {}

    if n == 2:
        # Building Wave B: retracement of Wave A (A went up)
        a_start = pivots[0].price  # L (bottom of A)
        a_end = pivots[1].price    # H (top of A)
        a_size = a_end - a_start
        targets["0.382"] = round(a_end - a_size * 0.382, 2)
        targets["0.500"] = round(a_end - a_size * 0.500, 2)
        targets["0.618"] = round(a_end - a_size * 0.618, 2)
        targets["0.786"] = round(a_end - a_size * 0.786, 2)

    elif n == 3:
        # Building Wave C: extension from Wave B end (C goes UP)
        a_start = pivots[0].price
        a_end = pivots[1].price
        b_end = pivots[2].price
        a_size = a_end - a_start
        targets["C=A"] = round(b_end + a_size * 1.000, 2)
        targets["C=1.272A"] = round(b_end + a_size * 1.272, 2)
        targets["C=1.618A"] = round(b_end + a_size * 1.618, 2)

    return targets


def _corrective_wave_number(n: int, direction: str) -> str:
    """Map pivot count to ABC wave label."""
    if n == 2:
        return "B"   # A done, building B
    return "C"        # A+B done, building C


def _try_partial_bullish_corrective(pivots: list[Pivot]) -> Optional[InProgressWave]:
    """Detect bullish ABC correction in progress (expect bullish bounce at C)."""
    n = len(pivots)
    if n < 2 or n > 3:
        return None
    if [p.type for p in pivots] != _BULLISH_CORRECTIVE_SEQUENCES[n]:
        return None

    # Validate basic structure
    if n >= 2:
        # A went DOWN: first pivot is H (a_start) > second pivot L (a_end)
        if pivots[0].price <= pivots[1].price:
            return None
    if n == 3:
        # B went UP: third pivot H above second pivot L
        if pivots[2].price <= pivots[1].price:
            return None
        # B should not exceed A start (B retraces less than 100% of A)
        if pivots[2].price >= pivots[0].price:
            return None

    wave_number = _corrective_wave_number(n, "bullish")
    invalidation = pivots[0].price  # A start — if price exceeds A top, correction is over

    return InProgressWave(
        structure="CORRECTION",
        direction="bullish",
        wave_number=wave_number,
        completed_waves=n - 1,
        pivots=list(pivots),
        last_pivot=pivots[-1],
        current_wave_start=pivots[-1].price,
        invalidation=invalidation,
        fib_targets=_bullish_corrective_targets(pivots),
        rule_checks={},
        is_valid=True,
        confidence=round(0.35 + 0.10 * (n - 1), 3),
    )


def _try_partial_bearish_corrective(pivots: list[Pivot]) -> Optional[InProgressWave]:
    """Detect bearish ABC correction in progress (expect bearish drop at C)."""
    n = len(pivots)
    if n < 2 or n > 3:
        return None
    if [p.type for p in pivots] != _BEARISH_CORRECTIVE_SEQUENCES[n]:
        return None

    if n >= 2:
        # A went UP: first pivot is L < second pivot H
        if pivots[0].price >= pivots[1].price:
            return None
    if n == 3:
        # B went DOWN: third pivot L below second pivot H
        if pivots[2].price >= pivots[1].price:
            return None
        # B should not go below A start
        if pivots[2].price <= pivots[0].price:
            return None

    wave_number = _corrective_wave_number(n, "bearish")
    invalidation = pivots[0].price  # A start

    return InProgressWave(
        structure="CORRECTION",
        direction="bearish",
        wave_number=wave_number,
        completed_waves=n - 1,
        pivots=list(pivots),
        last_pivot=pivots[-1],
        current_wave_start=pivots[-1].price,
        invalidation=invalidation,
        fib_targets=_bearish_corrective_targets(pivots),
        rule_checks={},
        is_valid=True,
        confidence=round(0.35 + 0.10 * (n - 1), 3),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_inprogress_wave(pivots: list[Pivot]) -> Optional[InProgressWave]:
    """Detect which Elliott Wave is currently in progress.

    Scans recent pivots from the most recent, trying window sizes 5→2.
    Returns the first (longest) valid partial impulse found, or None.

    Args:
        pivots: List of Pivot objects ordered chronologically.

    Returns:
        InProgressWave describing the wave being built, or None if no
        valid partial pattern is found.
    """
    if len(pivots) < 2:
        return None

    # Try impulse first (windows 5→2) — impulse is higher priority
    for window_size in range(5, 1, -1):
        if len(pivots) < window_size:
            continue
        recent = pivots[-window_size:]
        bullish = _try_partial_bullish_impulse(recent)
        bearish = _try_partial_bearish_impulse(recent)
        candidates = [c for c in (bullish, bearish) if c is not None]
        if candidates:
            best = max(candidates, key=lambda c: (c.confidence, c.completed_waves))
            return best

    # If no impulse found, try corrective (windows 3→2)
    for window_size in range(3, 1, -1):
        if len(pivots) < window_size:
            continue
        recent = pivots[-window_size:]
        bull_corr = _try_partial_bullish_corrective(recent)
        bear_corr = _try_partial_bearish_corrective(recent)
        candidates = [c for c in (bull_corr, bear_corr) if c is not None]
        if candidates:
            best = max(candidates, key=lambda c: (c.confidence, c.completed_waves))
            return best

    return None
