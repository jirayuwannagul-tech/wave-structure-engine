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
# Post-impulse correction detection (6 and 7 pivot patterns)
# ---------------------------------------------------------------------------
# After a 5-wave impulse completes, the corrective ABC pattern begins.
# These functions detect the two earliest states of that correction:
#   6 pivots [L,H,L,H,L,H]   → bullish impulse W5 just confirmed, Wave A starting
#   7 pivots [L,H,L,H,L,H,L] → Wave A done, now building bullish Wave B
# Mirror sequences for bearish impulse → bullish correction.


def _validate_full_bullish_impulse(pivots: list[Pivot]) -> tuple[bool, dict[str, bool]]:
    """Validate a complete 6-pivot bullish impulse [L,H,L,H,L,H] (W1-W5)."""
    checks: dict[str, bool] = {}
    # Monotonic: higher highs and higher lows in the impulse legs (indices 0-5)
    # H[1]>L[0], L[2]>L[0], H[3]>H[1], L[4]>L[2], H[5]>H[3]
    checks["monotonic"] = (
        pivots[1].price > pivots[0].price  # H1 above L0
        and pivots[2].price > pivots[0].price  # L2 above L0 (higher low)
        and pivots[3].price > pivots[1].price  # H3 above H1 (higher high)
        and pivots[4].price > pivots[2].price  # L4 above L2 (higher low)
        and pivots[5].price > pivots[3].price  # H5 above H3 (W5 new high)
    )
    if not checks["monotonic"]:
        return False, checks
    # EW Rule 1: W2 never retraces beyond W1 origin
    checks["w2_not_beyond_w1"] = pivots[2].price > pivots[0].price
    # EW Rule 2: W3 not shortest of W1, W3, W5
    w1 = pivots[1].price - pivots[0].price
    w3 = pivots[3].price - pivots[2].price
    w5 = pivots[5].price - pivots[4].price
    checks["w3_not_shortest"] = w3 >= min(w1, w5)
    # EW Rule 3: W4 never enters W1 territory
    checks["w4_no_w1_overlap"] = pivots[4].price > pivots[1].price
    valid = all(checks.values())
    return valid, checks


def _validate_full_bearish_impulse(pivots: list[Pivot]) -> tuple[bool, dict[str, bool]]:
    """Validate a complete 6-pivot bearish impulse [H,L,H,L,H,L] (W1-W5)."""
    checks: dict[str, bool] = {}
    checks["monotonic"] = (
        pivots[1].price < pivots[0].price
        and pivots[2].price < pivots[0].price
        and pivots[3].price < pivots[1].price
        and pivots[4].price < pivots[2].price
        and pivots[5].price < pivots[3].price
    )
    if not checks["monotonic"]:
        return False, checks
    checks["w2_not_beyond_w1"] = pivots[2].price < pivots[0].price
    w1 = pivots[0].price - pivots[1].price
    w3 = pivots[2].price - pivots[3].price
    w5 = pivots[4].price - pivots[5].price
    checks["w3_not_shortest"] = w3 >= min(w1, w5)
    checks["w4_no_w1_overlap"] = pivots[4].price < pivots[1].price
    valid = all(checks.values())
    return valid, checks


def _try_complete_bullish_impulse_correction(pivots: list[Pivot]) -> Optional[InProgressWave]:
    """Detect post-bullish-impulse correction state.

    6 pivots [L,H,L,H,L,H] → 5-wave up complete, building Wave A (bearish).
    7 pivots [L,H,L,H,L,H,L] → Wave A done, building Wave B (bullish bounce).
    """
    n = len(pivots)
    if n not in (6, 7):
        return None

    expected = ["L", "H", "L", "H", "L", "H"] if n == 6 else ["L", "H", "L", "H", "L", "H", "L"]
    if [p.type for p in pivots] != expected:
        return None

    # Validate the impulse portion (first 6 pivots = W0 through W5 top)
    valid, checks = _validate_full_bullish_impulse(pivots[:6])
    if not valid:
        return None

    if n == 6:
        # W5 confirmed, Wave A about to begin (no Wave A pivot confirmed yet)
        return InProgressWave(
            structure="CORRECTION",
            direction="bearish",
            wave_number="A",
            completed_waves=5,
            pivots=list(pivots),
            last_pivot=pivots[-1],
            current_wave_start=pivots[-1].price,   # Wave A starts from W5 top
            invalidation=pivots[-1].price,           # can't make new ATH
            fib_targets={},
            rule_checks=checks,
            is_valid=True,
            confidence=0.72,
        )
    else:
        # Wave A confirmed (L[6] < H[5]), building Wave B
        wave_a_size = pivots[5].price - pivots[6].price
        b_target_0382 = round(pivots[6].price + wave_a_size * 0.382, 6)
        b_target_0618 = round(pivots[6].price + wave_a_size * 0.618, 6)
        return InProgressWave(
            structure="CORRECTION",
            direction="bearish",
            wave_number="B",
            completed_waves=6,
            pivots=list(pivots),
            last_pivot=pivots[-1],
            current_wave_start=pivots[-1].price,   # Wave B starts from Wave A low
            invalidation=pivots[5].price,            # Wave B can't exceed W5 high
            fib_targets={"0.382": b_target_0382, "0.618": b_target_0618},
            rule_checks=checks,
            is_valid=True,
            confidence=0.78,
        )


def _try_complete_bearish_impulse_correction(pivots: list[Pivot]) -> Optional[InProgressWave]:
    """Detect post-bearish-impulse correction state.

    6 pivots [H,L,H,L,H,L] → 5-wave down complete, building Wave A (bullish).
    7 pivots [H,L,H,L,H,L,H] → Wave A done, building Wave B (bearish).
    """
    n = len(pivots)
    if n not in (6, 7):
        return None

    expected = ["H", "L", "H", "L", "H", "L"] if n == 6 else ["H", "L", "H", "L", "H", "L", "H"]
    if [p.type for p in pivots] != expected:
        return None

    valid, checks = _validate_full_bearish_impulse(pivots[:6])
    if not valid:
        return None

    if n == 6:
        return InProgressWave(
            structure="CORRECTION",
            direction="bullish",
            wave_number="A",
            completed_waves=5,
            pivots=list(pivots),
            last_pivot=pivots[-1],
            current_wave_start=pivots[-1].price,
            invalidation=pivots[-1].price,
            fib_targets={},
            rule_checks=checks,
            is_valid=True,
            confidence=0.72,
        )
    else:
        wave_a_size = pivots[6].price - pivots[5].price
        b_target_0382 = round(pivots[6].price - wave_a_size * 0.382, 6)
        b_target_0618 = round(pivots[6].price - wave_a_size * 0.618, 6)
        return InProgressWave(
            structure="CORRECTION",
            direction="bullish",
            wave_number="B",
            completed_waves=6,
            pivots=list(pivots),
            last_pivot=pivots[-1],
            current_wave_start=pivots[-1].price,
            invalidation=pivots[5].price,
            fib_targets={"0.382": b_target_0382, "0.618": b_target_0618},
            rule_checks=checks,
            is_valid=True,
            confidence=0.78,
        )


# ---------------------------------------------------------------------------
# Non-consecutive Primary-degree impulse detection
# ---------------------------------------------------------------------------
# Standard consecutive matching fails for Primary (1W) degree because many
# intermediate pivots exist between the true Primary turning points
# (bear bottom → W1 → W2 → W3 → W4 → W5).  These functions search ALL
# combinations of non-consecutive pivots that form valid EW patterns.
#
# Selection rule: among all valid patterns ending at the last pivot, pick the
# one with the LARGEST price span (max_price - min_price).  This equals the
# one with the LOWEST W0, which is always the Primary degree count because:
#   • Sub-waves have higher W0 → smaller span
#   • Pre-cycle patterns fail EW validation (2022 bear broke below 2021 lows)


_NC_MAX_SPAN_BARS = 260   # 5 years of weekly bars — excludes pre-cycle lows


def _nc_bullish_cw3(
    pivots: list[Pivot],
    last_idx: int,
    h_idx: list[int],
    l_idx: list[int],
) -> Optional[InProgressWave]:
    """4-pivot [L,H,L,H] non-consecutive, ending at last_idx (H). cw=3.

    Iterates W0 in FORWARD order (oldest first) so the first valid W0 found
    for each (i1,i2) combo is the OLDEST = largest span = Primary degree.
    """
    w3 = pivots[last_idx]
    best_span = -1.0
    best: Optional[InProgressWave] = None
    last_bar = pivots[last_idx].index

    for i2 in reversed([i for i in l_idx if i < last_idx]):
        w2 = pivots[i2]
        if w2.price >= w3.price:
            continue
        for i1 in reversed([i for i in h_idx if i < i2]):
            w1 = pivots[i1]
            if w1.price >= w3.price:
                continue
            if w2.price >= w1.price:
                continue
            # Early exit: can this (i1,i2) combo beat current best_span?
            # Max possible span = w3.price - (smallest L before i1)
            # Skip if no improvement possible (w3 - w1 <= best_span as proxy)
            for i0 in [i for i in l_idx if i < i1]:  # forward = oldest first
                w0 = pivots[i0]
                if last_bar - w0.index > _NC_MAX_SPAN_BARS:
                    continue  # too old — skip, newer pivots may still qualify
                if w0.price >= w2.price:
                    continue
                sub = [w0, w1, w2, w3]
                ok, checks = _validate_bullish_partial(sub)
                if ok:
                    span = w3.price - w0.price
                    if span > best_span:
                        best_span = span
                        durations = measure_impulse_wave_durations(sub)
                        time_proj = project_wave_time(
                            completed_durations=durations,
                            building_wave="4",
                            current_bar_index=w3.index,
                            wave_start_index=w3.index,
                        )
                        time_adj = score_time_confidence(time_proj)
                        best = InProgressWave(
                            structure="IMPULSE",
                            direction="bullish",
                            wave_number="4",
                            completed_waves=3,
                            pivots=sub,
                            last_pivot=w3,
                            current_wave_start=w3.price,
                            invalidation=_bullish_invalidation(sub),
                            fib_targets=_bullish_fib_targets(sub),
                            rule_checks=checks,
                            is_valid=True,
                            confidence=round(
                                min(0.95, _confidence(checks, 4) + time_adj), 3
                            ),
                            time_projection=time_proj,
                        )
                    break  # forward order: first valid = oldest = max span for this combo
    return best


def _nc_bullish_cw4(
    pivots: list[Pivot],
    last_idx: int,
    h_idx: list[int],
    l_idx: list[int],
) -> Optional[InProgressWave]:
    """5-pivot [L,H,L,H,L] non-consecutive, ending at last_idx (L). cw=4."""
    w4 = pivots[last_idx]
    best_span = -1.0
    best: Optional[InProgressWave] = None
    last_bar = pivots[last_idx].index

    for i3 in reversed([i for i in h_idx if i < last_idx]):
        w3 = pivots[i3]
        if w4.price >= w3.price:
            continue
        for i2 in reversed([i for i in l_idx if i < i3]):
            w2 = pivots[i2]
            if w2.price >= w3.price:
                continue
            if w4.price <= w2.price:
                continue
            for i1 in reversed([i for i in h_idx if i < i2]):
                w1 = pivots[i1]
                if w1.price >= w3.price:
                    continue
                if w2.price >= w1.price:
                    continue
                if w4.price <= w1.price:
                    continue
                for i0 in [i for i in l_idx if i < i1]:  # forward = oldest first
                    w0 = pivots[i0]
                    if last_bar - w0.index > _NC_MAX_SPAN_BARS:
                        continue
                    if w0.price >= w2.price:
                        continue
                    sub = [w0, w1, w2, w3, w4]
                    ok, checks = _validate_bullish_partial(sub)
                    if ok:
                        span = w3.price - w0.price
                        if span > best_span:
                            best_span = span
                            durations = measure_impulse_wave_durations(sub)
                            time_proj = project_wave_time(
                                completed_durations=durations,
                                building_wave="5",
                                current_bar_index=w4.index,
                                wave_start_index=w4.index,
                            )
                            time_adj = score_time_confidence(time_proj)
                            best = InProgressWave(
                                structure="IMPULSE",
                                direction="bullish",
                                wave_number="5",
                                completed_waves=4,
                                pivots=sub,
                                last_pivot=w4,
                                current_wave_start=w4.price,
                                invalidation=_bullish_invalidation(sub),
                                fib_targets=_bullish_fib_targets(sub),
                                rule_checks=checks,
                                is_valid=True,
                                confidence=round(
                                    min(0.95, _confidence(checks, 5) + time_adj), 3
                                ),
                                time_projection=time_proj,
                            )
                        break  # first valid in forward order = oldest = max span
    return best


def _nc_bullish_cw5(
    pivots: list[Pivot],
    last_idx: int,
    h_idx: list[int],
    l_idx: list[int],
) -> Optional[InProgressWave]:
    """6-pivot [L,H,L,H,L,H] non-consecutive, ending at last_idx (H). cw=5."""
    w5 = pivots[last_idx]
    best_span = -1.0
    best: Optional[InProgressWave] = None
    last_bar = pivots[last_idx].index

    for i4 in reversed([i for i in l_idx if i < last_idx]):
        w4 = pivots[i4]
        if w4.price >= w5.price:
            continue
        for i3 in reversed([i for i in h_idx if i < i4]):
            w3 = pivots[i3]
            if w3.price >= w5.price:
                continue
            if w4.price >= w3.price:
                continue
            for i2 in reversed([i for i in l_idx if i < i3]):
                w2 = pivots[i2]
                if w2.price >= w3.price:
                    continue
                if w4.price <= w2.price:
                    continue
                for i1 in reversed([i for i in h_idx if i < i2]):
                    w1 = pivots[i1]
                    if w1.price >= w3.price:
                        continue
                    if w2.price >= w1.price:
                        continue
                    if w4.price <= w1.price:
                        continue
                    for i0 in [i for i in l_idx if i < i1]:  # forward = oldest first
                        w0 = pivots[i0]
                        if last_bar - w0.index > _NC_MAX_SPAN_BARS:
                            continue
                        if w0.price >= w2.price:
                            continue
                        sub = [w0, w1, w2, w3, w4, w5]
                        ok, checks = _validate_full_bullish_impulse(sub)
                        if ok:
                            span = w5.price - w0.price
                            if span > best_span:
                                best_span = span
                                best = InProgressWave(
                                    structure="CORRECTION",
                                    direction="bearish",
                                    wave_number="A",
                                    completed_waves=5,
                                    pivots=sub,
                                    last_pivot=w5,
                                    current_wave_start=w5.price,
                                    invalidation=w5.price,
                                    fib_targets={},
                                    rule_checks=checks,
                                    is_valid=True,
                                    confidence=0.72,
                                )
                            break  # first valid in forward order = oldest = max span
    return best


def _nc_bullish_cw6(
    pivots: list[Pivot],
    last_idx: int,
    h_idx: list[int],
    l_idx: list[int],
) -> Optional[InProgressWave]:
    """7-pivot [L,H,L,H,L,H,L] non-consecutive, ending at last_idx (L). cw=6."""
    wa = pivots[last_idx]
    # W5 = most recent H before the WA low
    h_before_wa = [i for i in h_idx if i < last_idx]
    if not h_before_wa:
        return None
    i5 = h_before_wa[-1]

    # W5 must be above WA low (Wave A went down from W5)
    if pivots[i5].price <= wa.price:
        return None

    # Find best 6-pivot ending at W5
    result6 = _nc_bullish_cw5(pivots, i5, h_idx, l_idx)
    if result6 is None:
        return None

    # Build 7-pivot result
    sub7 = result6.pivots + [wa]
    w5_pivot = result6.pivots[5]
    wave_a_size = w5_pivot.price - wa.price
    b_target_0382 = round(wa.price + wave_a_size * 0.382, 6)
    b_target_0618 = round(wa.price + wave_a_size * 0.618, 6)

    return InProgressWave(
        structure="CORRECTION",
        direction="bearish",
        wave_number="B",
        completed_waves=6,
        pivots=sub7,
        last_pivot=wa,
        current_wave_start=wa.price,
        invalidation=w5_pivot.price,
        fib_targets={"0.382": b_target_0382, "0.618": b_target_0618},
        rule_checks=result6.rule_checks,
        is_valid=True,
        confidence=0.78,
    )


def _find_nonconsecutive_bullish(
    pivots: list[Pivot],
) -> Optional[InProgressWave]:
    """Find best Primary-degree bullish impulse using non-consecutive pivots.

    All patterns must END at the last pivot.  Among valid patterns, selects
    the one with the LARGEST price span (= lowest W0 = Primary degree count).
    """
    n = len(pivots)
    if n < 4:
        return None

    last = pivots[-1]
    last_idx = n - 1
    h_idx = [i for i, p in enumerate(pivots) if p.type == "H"]
    l_idx = [i for i, p in enumerate(pivots) if p.type == "L"]

    candidates: list[InProgressWave] = []

    if last.type == "H":
        r = _nc_bullish_cw5(pivots, last_idx, h_idx, l_idx)
        if r:
            candidates.append(r)
        r = _nc_bullish_cw3(pivots, last_idx, h_idx, l_idx)
        if r:
            candidates.append(r)
    elif last.type == "L":
        r = _nc_bullish_cw6(pivots, last_idx, h_idx, l_idx)
        if r:
            candidates.append(r)
        r = _nc_bullish_cw4(pivots, last_idx, h_idx, l_idx)
        if r:
            candidates.append(r)

    if not candidates:
        return None

    def _span(iw: InProgressWave) -> float:
        return max(p.price for p in iw.pivots) - min(p.price for p in iw.pivots)

    # Prefer largest span (= Primary degree); tiebreak by highest cw
    return max(candidates, key=lambda iw: (_span(iw), iw.completed_waves))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_inprogress_wave(
    pivots: list[Pivot],
    search_window: int = 60,
) -> Optional[InProgressWave]:
    """Detect which Elliott Wave is currently in progress.

    Scans every possible anchor position in the search window and returns the
    pattern with the MOST completed waves.  This correctly identifies deep
    structures (e.g. a full 5-wave impulse that has already finished and is now
    in Wave A/B of the ABC correction) rather than always anchoring at the most
    recent pivot.

    Algorithm:
      For each candidate anchor (oldest to newest in the window):
        Try fitting the longest valid EW pattern (2–7 pivots) forward from that
        anchor, trying all pattern types (impulse, post-impulse correction,
        ABC correction).
      Return the single result with the highest ``completed_waves``.
      Ties are broken by the more recent anchor (fresher structural context).

    Pattern types and their completed_waves:
      [L,H]           bullish cw=1  building W2
      [L,H,L]         bullish cw=2  building W3
      [L,H,L,H]       bullish cw=3  building W4
      [L,H,L,H,L]     bullish cw=4  building W5
      [L,H,L,H,L,H]   bullish cw=5  W5 done, building Wave A  (CORRECTION)
      [L,H,L,H,L,H,L] bullish cw=6  Wave A done, building Wave B (CORRECTION)
      Mirror sequences for bearish.

    Args:
        pivots: Strictly alternating H/L Pivot objects (compress_pivots output),
                ordered chronologically.
        search_window: How many pivots back from the tail to consider.
                       Pass ``len(pivots)`` to search the full history.

    Returns:
        InProgressWave describing the wave being built, or None.
    """
    if len(pivots) < 2:
        return None

    search = pivots[max(0, len(pivots) - search_window):]
    n = len(search)
    if n < 2:
        return None

    best: Optional[InProgressWave] = None
    best_cw: int = -1
    best_anchor: int = -1   # higher index = more recent = tiebreaker

    # -----------------------------------------------------------------------
    # Step 1 — Non-consecutive Primary-degree impulse search.
    #
    # Finds the largest-span valid EW pattern ending at the most recent pivot.
    # This correctly identifies Primary degree (W0 = bear market bottom) even
    # when many intermediate pivots exist between the true Primary pivots.
    # -----------------------------------------------------------------------
    nc_bull = _find_nonconsecutive_bullish(search)
    if nc_bull is not None and nc_bull.completed_waves > best_cw:
        best = nc_bull
        best_cw = nc_bull.completed_waves
        best_anchor = n - len(nc_bull.pivots)

    if best_cw >= 6:
        return best   # cw=6 Wave B building — nothing better possible

    # -----------------------------------------------------------------------
    # Step 2 — Consecutive 2–5-pivot impulse patterns ending at last pivot.
    #
    # Restricted to windows ending at search[-1] to avoid stale historical
    # matches.  Useful for Intermediate/Minor degree where NC search might
    # not apply.
    # -----------------------------------------------------------------------
    for window_size in range(min(n, 5), 1, -1):
        sub = search[-window_size:]
        for build in (_try_partial_bullish_impulse, _try_partial_bearish_impulse):
            result = build(sub)
            if result is None:
                continue
            cw = result.completed_waves
            anchor = n - window_size
            if cw > best_cw or (cw == best_cw and anchor > best_anchor):
                best = result
                best_cw = cw
                best_anchor = anchor

    if best_cw >= 4:
        return best   # cw=4 W5 building found

    # -----------------------------------------------------------------------
    # Step 3 — Short corrective patterns (2–3 pivots) as last resort.
    #
    # Keep this restricted to truly short histories. On 4+ pivots we prefer
    # falling back to the weaker impulse interpretation rather than relabeling
    # the tail as a fresh ABC too early.
    # -----------------------------------------------------------------------
    if n <= 3:
        for anchor_idx in range(n - 1):
            wave_pivots = search[anchor_idx:]
            max_win = min(len(wave_pivots), 3)
            for window_size in range(max_win, 1, -1):
                sub = wave_pivots[:window_size]
                for build in (_try_partial_bullish_corrective, _try_partial_bearish_corrective):
                    result = build(sub)
                    if result is None:
                        continue
                    cw = result.completed_waves
                    if cw > best_cw or (cw == best_cw and anchor_idx > best_anchor):
                        best = result
                        best_cw = cw
                        best_anchor = anchor_idx

    return best
