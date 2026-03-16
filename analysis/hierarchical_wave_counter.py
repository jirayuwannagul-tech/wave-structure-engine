"""Hierarchical Elliott Wave Counter.

Counts waves across multiple degrees:
  - Primary degree    (1W timeframe)
  - Intermediate degree (1D timeframe)
  - Minor degree      (4H timeframe)
  - Sub-minor degree  (1H timeframe) — assessment only, not entry

Uses inprogress_detector at each degree and nests the results into a
unified HierarchicalCount, then generates trade scenarios based on the
current wave position at each degree.

Core principle:
  - In a bullish Primary impulse, Intermediate waves 2/4 are pullbacks → LONG
  - In a bearish Primary impulse, Intermediate waves 2/4 are pullbacks → SHORT
  - ABC corrections: wave B is tradeable, wave C bottom/top is high-quality entry
  - Entry at every wave type — not just at pattern completion
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from analysis.inprogress_detector import InProgressWave, detect_inprogress_wave
from analysis.pivot_detector import Pivot, compress_pivots, detect_pivots
from scenarios.scenario_engine import Scenario


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class DegreePosition:
    """Wave position at a single Elliott Wave degree."""

    degree: str          # "Primary", "Intermediate", "Minor"
    timeframe: str       # "1W", "1D", "4H"
    structure: str       # "IMPULSE", "ABC_CORRECTION", etc.
    wave_number: str     # "1"-"5" or "A"-"C"
    direction: str       # "bullish" or "bearish" (overall structure direction)
    completed_waves: int
    confidence: float
    fib_targets: dict
    invalidation: float | None = None
    current_wave_start: float | None = None  # price where current wave began
    parent_wave_number: str | None = None     # wave number of parent degree


@dataclass
class HierarchicalCount:
    """Nested Elliott Wave count across Primary, Intermediate, and Minor degrees."""

    symbol: str
    as_of: object = None           # pd.Timestamp or None

    primary: DegreePosition | None = None      # 1W
    intermediate: DegreePosition | None = None # 1D
    minor: DegreePosition | None = None        # 4H
    sub_minor: DegreePosition | None = None    # 1H (assessment only)

    trade_bias: str | None = None          # "BULLISH" or "BEARISH"
    entry_wave_desc: str | None = None     # human-readable entry rationale
    hierarchical_confidence: float = 0.0

    is_consistent: bool = True
    consistency_note: str = ""

    scenarios: list = field(default_factory=list)

    # Wave fingerprint: identifies the specific wave instance.
    # Changes only when the wave START changes (new wave begins).
    # Used for deduplication: enter at most once per wave instance.
    wave_fingerprint: str = ""


# ---------------------------------------------------------------------------
# Direction inference
# ---------------------------------------------------------------------------


def _current_wave_move_direction(structure: str, wave_number: str, overall_direction: str) -> str | None:
    """Return the direction the current wave is MOVING.

    Different from overall structure direction: in a bullish impulse,
    Wave 2 moves bearish (correction), Wave 3 moves bullish (extension).
    """
    wn = str(wave_number).upper()

    if structure == "IMPULSE":
        if overall_direction == "bullish":
            return "bullish" if wn in ("1", "3", "5") else "bearish"
        else:
            return "bearish" if wn in ("1", "3", "5") else "bullish"

    if structure in ("ABC_CORRECTION", "EXPANDED_FLAT", "RUNNING_FLAT", "WXY"):
        # ABC: in a bearish ABC (A goes down, B goes up, C goes down)
        if overall_direction == "bearish":
            if wn in ("A", "C", "W", "Y"):
                return "bearish"
            if wn in ("B", "X"):
                return "bullish"
        else:
            if wn in ("A", "C", "W", "Y"):
                return "bullish"
            if wn in ("B", "X"):
                return "bearish"

    return None


def _expected_child_move_direction(parent_wave_number: str, parent_direction: str) -> str | None:
    """Given parent's current wave number and overall direction, what direction should
    the child structure be MOVING in?"""
    wn = str(parent_wave_number).upper()

    # Impulse parent
    if parent_direction == "bullish":
        if wn in ("1", "3", "5"):
            return "bullish"   # child sub-waves go up
        if wn in ("2", "4"):
            return "bearish"   # child sub-waves (corrections) go down
        if wn == "A":
            return "bearish"
        if wn == "B":
            return "bullish"
        if wn in ("C", "W", "Y"):
            return "bearish"
    else:
        if wn in ("1", "3", "5"):
            return "bearish"
        if wn in ("2", "4"):
            return "bullish"
        if wn == "A":
            return "bullish"
        if wn == "B":
            return "bearish"
        if wn in ("C", "W", "Y"):
            return "bullish"

    return None


def _check_consistency(
    primary: DegreePosition | None,
    intermediate: DegreePosition | None,
) -> tuple[bool, str]:
    """Check if Intermediate degree is consistent with Primary degree."""
    if primary is None or intermediate is None:
        return True, ""

    expected = _expected_child_move_direction(primary.wave_number, primary.direction)
    if expected is None:
        return True, ""

    actual = _current_wave_move_direction(
        intermediate.structure, intermediate.wave_number, intermediate.direction
    )
    if actual is None:
        return True, ""

    if actual != expected:
        return False, (
            f"Primary Wave {primary.wave_number} ({primary.direction}) expects child moving {expected}, "
            f"Intermediate building Wave {intermediate.wave_number} ({actual})"
        )
    return True, "consistent"


# ---------------------------------------------------------------------------
# Scenario generation from wave position
# ---------------------------------------------------------------------------


_MAX_STOP_PCT = 0.12   # reject if stop is more than 12% from entry
_MAX_TARGET_MULT = 5.0  # reject Fibonacci targets further than 5x risk


def _build_exit_targets(
    bias: str,
    entry: float,
    stop: float,
    fib_targets: dict,
    structure: str,
    wave_number: str,
) -> list[float]:
    """Build exit targets from Fibonacci data or R-multiples.

    Rejects targets that are:
    - Negative or zero (impossible price)
    - Further than _MAX_TARGET_MULT × risk from entry (likely bad Fib data)
    Always falls back to R-multiples if Fibonacci data is unusable.
    """
    risk = abs(entry - stop)
    if risk <= 0:
        risk = entry * 0.02  # fallback 2%

    max_target_dist = risk * _MAX_TARGET_MULT

    def _valid_bullish(v: float) -> bool:
        return v > entry and v > 0 and (v - entry) <= max_target_dist

    def _valid_bearish(v: float) -> bool:
        return v < entry and v > 0 and (entry - v) <= max_target_dist

    # Try to use Fibonacci targets from the wave data
    if bias == "BULLISH":
        candidates = []
        for key in ("1.618", "2.618", "1.000", "w1_equal", "0.618xW1W3", "1.272xW1", "C=A", "C=1.272A", "C=1.618A"):
            v = fib_targets.get(key)
            if v is not None and _valid_bullish(float(v)):
                candidates.append(float(v))
        if len(candidates) >= 2:
            candidates.sort()
            return [round(t, 6) for t in candidates[:3]]
        # Fallback: R-multiples
        return [
            round(entry + risk * 1.0, 6),
            round(entry + risk * 1.618, 6),
            round(entry + risk * 2.618, 6),
        ]
    else:  # BEARISH
        candidates = []
        for key in ("1.618", "2.618", "1.000", "w1_equal", "0.618xW1W3", "1.272xW1", "C=A", "C=1.272A", "C=1.618A"):
            v = fib_targets.get(key)
            if v is not None and _valid_bearish(float(v)):
                candidates.append(float(v))
        if len(candidates) >= 2:
            candidates.sort(reverse=True)
            return [round(t, 6) for t in candidates[:3]]
        return [
            round(entry - risk * 1.0, 6),
            round(entry - risk * 1.618, 6),
            round(entry - risk * 2.618, 6),
        ]


def _scenarios_from_position(pos: DegreePosition, current_price: float) -> list[Scenario]:
    """Generate trade scenarios based on the current wave position."""
    scenarios: list[Scenario] = []
    wn = str(pos.wave_number).upper()
    structure = str(pos.structure).upper()
    direction = str(pos.direction).lower()
    fib = pos.fib_targets or {}
    invalidation = pos.invalidation

    # ----------------------------------------------------------------
    # IMPULSE: wave 2 and 4 are pullbacks (best entries)
    # Only generate when price has actually REACHED the Fibonacci support
    # zone — not at the start of the correction when price is far above.
    # ----------------------------------------------------------------
    if structure == "IMPULSE" and wn in ("2", "4"):
        if direction == "bullish":
            bias = "BULLISH"
            # Common W2/W4 support levels (0.500–0.618 retracement)
            fib_618 = fib.get("0.618") or fib.get("0.500")
            fib_382 = fib.get("0.382")
            support = float(fib_618) if fib_618 else current_price * 0.96

            # Only enter if price is AT or NEAR the support zone.
            # If price is still far above (e.g., just finished Wave 1 high),
            # the correction hasn't reached the entry zone yet.
            if current_price > support * 1.03:   # more than 3% above support → skip
                return []

            entry = current_price   # use current close as confirmation (bounce)
            stop = float(invalidation) if invalidation else round(support * 0.96, 6)
        else:
            bias = "BEARISH"
            fib_618 = fib.get("0.618") or fib.get("0.500")
            resistance = float(fib_618) if fib_618 else current_price * 1.04

            if current_price < resistance * 0.97:   # more than 3% below resistance
                return []

            entry = current_price
            stop = float(invalidation) if invalidation else round(resistance * 1.04, 6)

        risk = abs(entry - stop)
        if risk < entry * 0.005:
            return []

        targets = _build_exit_targets(bias, entry, stop, fib, structure, wn)
        if not targets:
            return []

        next_wave = str(int(wn) + 1)
        scenarios.append(Scenario(
            name=f"Wave {wn} Pullback → Wave {next_wave} ({pos.degree})",
            condition=f"Price at Wave {wn} Fibonacci support/resistance zone",
            interpretation=(
                f"Wave {wn} correction of {direction} impulse completing near Fibonacci level. "
                f"Wave {next_wave} expected to extend toward {targets[0]:.2f}"
            ),
            target=f"Wave {next_wave} extension",
            bias=bias,
            invalidation=float(invalidation) if invalidation else None,
            confirmation=round(entry, 6),
            stop_loss=round(stop, 6),
            targets=targets,
        ))

    # ----------------------------------------------------------------
    # IMPULSE: wave 3 momentum entry
    # ----------------------------------------------------------------
    elif structure == "IMPULSE" and wn == "3":
        if direction == "bullish":
            bias = "BULLISH"
            entry = current_price
            # Stop: 5% below entry (ATR-independent tight stop for momentum)
            stop = round(current_price * 0.95, 6)
            if invalidation and float(invalidation) < stop:
                stop = float(invalidation)
        else:
            bias = "BEARISH"
            entry = current_price
            # Stop: 5% above entry
            stop = round(current_price * 1.05, 6)
            if invalidation and float(invalidation) > stop:
                stop = float(invalidation)

        risk = abs(entry - stop)
        # Hard reject: stop too far from entry
        if risk > entry * _MAX_STOP_PCT or risk < entry * 0.005:
            return []

        targets = _build_exit_targets(bias, entry, stop, fib, structure, wn)
        if not targets:
            return []

        scenarios.append(Scenario(
            name=f"Wave 3 Momentum ({pos.degree})",
            condition=f"Price in Wave 3 of {direction} impulse",
            interpretation=(
                f"Wave 3 — strongest wave — of {direction} impulse at {pos.timeframe}. "
                f"Momentum entry targeting {targets[-1]:.2f}"
            ),
            target="Wave 3 extension",
            bias=bias,
            invalidation=float(invalidation) if invalidation else None,
            confirmation=round(entry, 6),
            stop_loss=round(stop, 6),
            targets=targets,
        ))

    # ----------------------------------------------------------------
    # IMPULSE: wave 5 final leg
    # ----------------------------------------------------------------
    elif structure == "IMPULSE" and wn == "5":
        if direction == "bullish":
            bias = "BULLISH"
            entry = current_price
            stop = round(current_price * 0.95, 6)
            if invalidation and float(invalidation) < stop:
                stop = float(invalidation)
        else:
            bias = "BEARISH"
            entry = current_price
            stop = round(current_price * 1.05, 6)
            if invalidation and float(invalidation) > stop:
                stop = float(invalidation)

        risk = abs(entry - stop)
        if risk > entry * _MAX_STOP_PCT or risk < entry * 0.005:
            return []

        targets = _build_exit_targets(bias, entry, stop, fib, structure, wn)
        if not targets:
            return []

        scenarios.append(Scenario(
            name=f"Wave 5 Final ({pos.degree})",
            condition=f"Price in final Wave 5 of {direction} impulse",
            interpretation=(
                f"Wave 5 final leg of {direction} impulse. "
                f"Targeting {targets[0]:.2f} but expect reversal after completion."
            ),
            target="Wave 5 target",
            bias=bias,
            invalidation=float(invalidation) if invalidation else None,
            confirmation=round(entry, 6),
            stop_loss=round(stop, 6),
            targets=targets,
        ))

    # ----------------------------------------------------------------
    # ABC: wave B — enter in direction of the correction (toward C)
    # ----------------------------------------------------------------
    elif structure in ("ABC_CORRECTION", "EXPANDED_FLAT") and wn == "B":
        if direction == "bearish":
            # Bearish ABC: A↓ B↑ C↓. At Wave B top → SHORT for Wave C
            bias = "BEARISH"
            entry = current_price
            stop = float(invalidation) if invalidation else round(current_price * 1.03, 6)
        else:
            # Bullish ABC: A↑ B↓ C↑. At Wave B bottom → LONG for Wave C
            bias = "BULLISH"
            entry = current_price
            stop = float(invalidation) if invalidation else round(current_price * 0.97, 6)

        risk = abs(entry - stop)
        if risk < entry * 0.005:
            return []

        targets = _build_exit_targets(bias, entry, stop, fib, structure, wn)
        if not targets:
            return []

        scenarios.append(Scenario(
            name=f"Wave B → Wave C Entry ({pos.degree})",
            condition=f"Wave B of {direction} correction completing",
            interpretation=(
                f"Wave B of {direction} {structure} near completion. "
                f"Wave C expected in same direction as Wave A targeting {targets[0]:.2f}"
            ),
            target="Wave C target",
            bias=bias,
            invalidation=float(invalidation) if invalidation else None,
            confirmation=round(entry, 6),
            stop_loss=round(stop, 6),
            targets=targets,
        ))

    # ----------------------------------------------------------------
    # ABC: wave C — trend resumes after correction
    # ----------------------------------------------------------------
    elif structure in ("ABC_CORRECTION", "EXPANDED_FLAT") and wn == "C":
        if direction == "bearish":
            # C going DOWN → anticipate LONG (trend resumes UP after correction)
            bias = "BULLISH"
            # Entry at C=A level (common C target / support)
            entry = fib.get("C=A") or fib.get("C=1.272A") or current_price
            entry = float(entry)
            if entry > current_price:
                entry = current_price
            stop = float(invalidation) if invalidation else round(entry * 0.96, 6)
        else:
            # C going UP → anticipate SHORT (trend resumes DOWN after correction)
            bias = "BEARISH"
            entry = fib.get("C=A") or fib.get("C=1.272A") or current_price
            entry = float(entry)
            if entry < current_price:
                entry = current_price
            stop = float(invalidation) if invalidation else round(entry * 1.04, 6)

        risk = abs(entry - stop)
        if risk < entry * 0.005:
            return []

        targets = _build_exit_targets(bias, entry, stop, fib, structure, wn)
        if not targets:
            return []

        scenarios.append(Scenario(
            name=f"Wave C Completion → Trend Resumption ({pos.degree})",
            condition=f"Wave C of {direction} correction near Fibonacci target",
            interpretation=(
                f"Wave C of {direction} {structure} reaching Fibonacci target at {entry:.2f}. "
                f"Expect trend resumption after correction completes."
            ),
            target="Post-correction trend target",
            bias=bias,
            invalidation=float(invalidation) if invalidation else None,
            confirmation=round(entry, 6),
            stop_loss=round(stop, 6),
            targets=targets,
        ))

    return scenarios


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------


def _ip_to_degree(
    ip: InProgressWave,
    degree: str,
    timeframe: str,
    parent_wave: str | None = None,
) -> DegreePosition:
    return DegreePosition(
        degree=degree,
        timeframe=timeframe,
        structure=ip.structure,
        wave_number=ip.wave_number,
        direction=ip.direction,
        completed_waves=ip.completed_waves,
        confidence=ip.confidence,
        fib_targets=dict(ip.fib_targets or {}),
        invalidation=ip.invalidation,
        current_wave_start=ip.current_wave_start,
        parent_wave_number=parent_wave,
    )


def build_hierarchical_count(
    symbol: str,
    primary_pivots: list[Pivot],
    intermediate_pivots: list[Pivot],
    minor_pivots: list[Pivot] | None = None,
    sub_minor_pivots: list[Pivot] | None = None,
    current_price: float | None = None,
    as_of: object = None,
) -> HierarchicalCount:
    """Build hierarchical Elliott Wave count from multi-timeframe pivot lists.

    Args:
        symbol: Trading symbol, e.g. "BTCUSDT".
        primary_pivots: Pivots from the weekly (Primary degree) data.
        intermediate_pivots: Pivots from the daily (Intermediate degree) data.
        minor_pivots: Pivots from 4H (Minor degree), optional.
        sub_minor_pivots: Pivots from 1H (Sub-minor degree), optional. Assessment only.
        current_price: Most recent close price.
        as_of: Timestamp (for reference / logging).

    Returns:
        HierarchicalCount with nested wave positions and trade scenarios.
    """
    # ---- Primary degree (1W) ----
    # Compress weekly pivots to strictly alternating H/L so that major degree
    # turning points (e.g. 2020 low → 2021 high → 2022 low → 2025 high) can be
    # matched by the impulse detector regardless of intermediate minor pivots.
    # Scan the entire compressed history so the Primary degree count is found
    # even when its anchor is far back in time.
    primary_pos: DegreePosition | None = None
    if len(primary_pivots) >= 2:
        compressed_primary = compress_pivots(primary_pivots)
        primary_ip = detect_inprogress_wave(
            compressed_primary,
            search_window=len(compressed_primary),  # scan full history
        )
        if primary_ip and primary_ip.is_valid:
            primary_pos = _ip_to_degree(primary_ip, "Primary", "1W")

    # ---- Intermediate degree (1D) ----
    # Use last 80 compressed pivots — covers ~6-9 months of daily data which is
    # enough to capture the intermediate degree pattern without going back to
    # multi-year history.
    intermediate_pos: DegreePosition | None = None
    if len(intermediate_pivots) >= 2:
        compressed_intermediate = compress_pivots(intermediate_pivots)
        intermediate_ip = detect_inprogress_wave(
            compressed_intermediate,
            search_window=80,
        )
        if intermediate_ip and intermediate_ip.is_valid:
            parent_wn = primary_pos.wave_number if primary_pos else None
            intermediate_pos = _ip_to_degree(intermediate_ip, "Intermediate", "1D", parent_wn)

    # ---- Minor degree (4H) ----
    minor_pos: DegreePosition | None = None
    if minor_pivots and len(minor_pivots) >= 2:
        compressed_minor = compress_pivots(minor_pivots)
        minor_ip = detect_inprogress_wave(
            compressed_minor,
            search_window=50,
        )
        if minor_ip and minor_ip.is_valid:
            parent_wn = intermediate_pos.wave_number if intermediate_pos else None
            minor_pos = _ip_to_degree(minor_ip, "Minor", "4H", parent_wn)

    # ---- Sub-minor degree (1H) — assessment only, not used for entry ----
    sub_minor_pos: DegreePosition | None = None
    if sub_minor_pivots and len(sub_minor_pivots) >= 2:
        compressed_sub = compress_pivots(sub_minor_pivots)
        sub_minor_ip = detect_inprogress_wave(
            compressed_sub,
            search_window=30,
        )
        if sub_minor_ip and sub_minor_ip.is_valid:
            parent_wn = minor_pos.wave_number if minor_pos else None
            sub_minor_pos = _ip_to_degree(sub_minor_ip, "Sub-minor", "1H", parent_wn)

    # ---- Consistency check (Primary → Intermediate, Minor → Sub-minor) ----
    is_consistent, consistency_note = _check_consistency(primary_pos, intermediate_pos)
    if is_consistent and minor_pos is not None and sub_minor_pos is not None:
        minor_consistent, minor_note = _check_consistency(minor_pos, sub_minor_pos)
        if not minor_consistent:
            # Sub-minor inconsistency lowers confidence but doesn't block trade
            consistency_note = f"Sub-minor note: {minor_note}"

    # ---- Trade signal: use intermediate first (most actionable) ----
    active = intermediate_pos or primary_pos
    trade_bias: str | None = None
    entry_wave_desc: str | None = None
    hier_confidence: float = 0.0

    if active:
        wn = str(active.wave_number).upper()
        direction = active.direction
        structure = active.structure

        if structure == "IMPULSE":
            if wn in ("2", "4"):
                trade_bias = "BULLISH" if direction == "bullish" else "BEARISH"
                entry_wave_desc = (
                    f"Wave {wn} pullback of {active.degree} {direction} impulse — "
                    f"enter {trade_bias}"
                )
                hier_confidence = active.confidence * 0.9
            elif wn in ("1", "3", "5"):
                trade_bias = "BULLISH" if direction == "bullish" else "BEARISH"
                entry_wave_desc = (
                    f"Wave {wn} of {active.degree} {direction} impulse — "
                    f"momentum entry {trade_bias}"
                )
                hier_confidence = active.confidence

        elif structure in ("ABC_CORRECTION", "EXPANDED_FLAT", "WXY", "RUNNING_FLAT"):
            if wn == "C":
                # Trade opposite to correction direction (trend resumes)
                trade_bias = "BULLISH" if direction == "bearish" else "BEARISH"
                entry_wave_desc = (
                    f"Wave C of {active.degree} {direction} correction near target — "
                    f"enter {trade_bias} for trend resumption"
                )
                hier_confidence = active.confidence * 0.85
            elif wn == "B":
                # Trade in the direction of the correction (toward C)
                trade_bias = "BEARISH" if direction == "bearish" else "BULLISH"
                entry_wave_desc = (
                    f"Wave B of {active.degree} {direction} correction — "
                    f"enter {trade_bias} toward Wave C"
                )
                hier_confidence = active.confidence * 0.7

    # ---- Generate scenarios ----
    scenarios: list[Scenario] = []
    if current_price is not None and active is not None:
        scenarios = _scenarios_from_position(active, current_price)

    # Build wave fingerprint from the active position's wave START price.
    # This is unique per wave instance — changes when Wave 2 completes and
    # Wave 3 begins (different start price).  Used for deduplication.
    fingerprint = ""
    if active is not None:
        start = int(active.current_wave_start or 0)
        fingerprint = f"{active.structure}_{active.direction}_{active.wave_number}_{start}"

    return HierarchicalCount(
        symbol=symbol,
        as_of=as_of,
        primary=primary_pos,
        intermediate=intermediate_pos,
        minor=minor_pos,
        sub_minor=sub_minor_pos,
        trade_bias=trade_bias,
        entry_wave_desc=entry_wave_desc,
        hierarchical_confidence=hier_confidence,
        is_consistent=is_consistent,
        consistency_note=consistency_note,
        scenarios=scenarios,
        wave_fingerprint=fingerprint,
    )


# ---------------------------------------------------------------------------
# DataFrame-based convenience wrapper
# ---------------------------------------------------------------------------


def build_hierarchical_count_from_dfs(
    symbol: str,
    primary_df: pd.DataFrame,
    intermediate_df: pd.DataFrame,
    minor_df: pd.DataFrame | None = None,
    sub_minor_df: pd.DataFrame | None = None,
    current_price: float | None = None,
) -> HierarchicalCount:
    """Build hierarchical count from DataFrames (handles ATR/pivot calculation).

    Args:
        symbol: Trading symbol.
        primary_df: Weekly DataFrame, already filtered to backtest cutoff.
        intermediate_df: Daily DataFrame, already filtered to backtest cutoff.
        minor_df: 4H DataFrame, already filtered to backtest cutoff, optional.
        sub_minor_df: 1H DataFrame, already filtered to backtest cutoff, optional.
                      Used for assessing where the Minor (4H) wave is in its sub-waves.
                      NOT used for entry signals.
        current_price: Latest close price.

    Returns:
        HierarchicalCount.
    """
    from analysis.indicator_engine import calculate_atr

    def _add_atr(df: pd.DataFrame) -> pd.DataFrame:
        if "atr" not in df.columns:
            df = df.copy()
            df["atr"] = calculate_atr(df, period=14)
        return df

    primary_df = _add_atr(primary_df)
    intermediate_df = _add_atr(intermediate_df)

    # Timeframe-appropriate pivot parameters.
    # Primary degree (1W) uses atr_mult=2.0 to capture the full 5-wave cycle
    # including W3, W4, W5, and the subsequent correction pivots, while still
    # filtering out minor intra-cycle noise.
    primary_pivots = detect_pivots(primary_df, right=2, min_swing_atr_mult=2.0)
    intermediate_pivots = detect_pivots(intermediate_df, right=1, min_swing_atr_mult=0.5)

    minor_pivots: list[Pivot] | None = None
    if minor_df is not None and len(minor_df) >= 10:
        minor_df = _add_atr(minor_df)
        minor_pivots = detect_pivots(minor_df, right=1, min_swing_atr_mult=0.3)

    sub_minor_pivots: list[Pivot] | None = None
    if sub_minor_df is not None and len(sub_minor_df) >= 10:
        sub_minor_df = _add_atr(sub_minor_df)
        sub_minor_pivots = detect_pivots(sub_minor_df, right=1, min_swing_atr_mult=0.2)

    if current_price is None and len(intermediate_df) > 0:
        current_price = float(intermediate_df.iloc[-1]["close"])

    as_of = None
    if len(intermediate_df) > 0 and "open_time" in intermediate_df.columns:
        as_of = intermediate_df.iloc[-1]["open_time"]

    return build_hierarchical_count(
        symbol=symbol,
        primary_pivots=primary_pivots,
        intermediate_pivots=intermediate_pivots,
        minor_pivots=minor_pivots,
        sub_minor_pivots=sub_minor_pivots,
        current_price=current_price,
        as_of=as_of,
    )
