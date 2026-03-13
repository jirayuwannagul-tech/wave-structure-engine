"""Labels Elliott Wave numbers with degree notation based on timeframe.

Degree mapping (from degree_registry):
    1W  → primary       [1] [2] [3] [4] [5]   /  [A] [B] [C]
    1D  → intermediate  (1) (2) (3) (4) (5)   /  (A) (B) (C)
    4H  → minor          1   2   3   4   5    /   A   B   C
    1H  → minute         i  ii  iii  iv  v    /   a   b   c
"""

from __future__ import annotations

from dataclasses import dataclass

from analysis.patterns.degree_registry import get_degree

# ---------------------------------------------------------------------------
# Label tables
# ---------------------------------------------------------------------------

_IMPULSE_LABELS: dict[str, dict[str, str]] = {
    "primary": {
        "1": "[1]", "2": "[2]", "3": "[3]", "4": "[4]", "5": "[5]",
    },
    "intermediate": {
        "1": "(1)", "2": "(2)", "3": "(3)", "4": "(4)", "5": "(5)",
    },
    "minor": {
        "1": "1", "2": "2", "3": "3", "4": "4", "5": "5",
    },
    "minute": {
        "1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v",
    },
}

_CORRECTION_LABELS: dict[str, dict[str, str]] = {
    "primary": {
        "A": "[A]", "B": "[B]", "C": "[C]",
        "W": "[W]", "X": "[X]", "Y": "[Y]",
    },
    "intermediate": {
        "A": "(A)", "B": "(B)", "C": "(C)",
        "W": "(W)", "X": "(X)", "Y": "(Y)",
    },
    "minor": {
        "A": "A", "B": "B", "C": "C",
        "W": "W", "X": "X", "Y": "Y",
    },
    "minute": {
        "A": "a", "B": "b", "C": "c",
        "W": "w", "X": "x", "Y": "y",
    },
}

_DEGREE_DISPLAY: dict[str, str] = {
    "primary":      "Primary",
    "intermediate": "Intermediate",
    "minor":        "Minor",
    "minute":       "Minute",
    "unknown":      "Unknown",
}

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class WaveLabel:
    """Fully-labeled Elliott Wave number."""

    wave_number: str   # raw: "1".."5" or "A","B","C"
    degree: str        # "primary", "intermediate", "minor", "minute"
    formatted: str     # e.g., "(4)", "iii", "[A]"
    timeframe: str     # e.g., "1D", "4H"

    @property
    def degree_display(self) -> str:
        return _DEGREE_DISPLAY.get(self.degree, self.degree.capitalize())

    @property
    def full_label(self) -> str:
        """e.g. 'Wave (4) of Intermediate'"""
        return f"Wave {self.formatted} of {self.degree_display}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def label_wave(wave_number: str, timeframe: str) -> WaveLabel:
    """Return a WaveLabel for a wave number at a given timeframe.

    Args:
        wave_number: "1","2","3","4","5" for impulse waves;
                     "A","B","C","W","X","Y" for corrective waves.
        timeframe:   "1W", "1D", "4H", "1H", etc.

    Returns:
        WaveLabel with formatted notation and degree info.
    """
    degree = get_degree(timeframe.upper())
    wave_upper = wave_number.upper()

    is_corrective = wave_upper in ("A", "B", "C", "W", "X", "Y")
    table = _CORRECTION_LABELS if is_corrective else _IMPULSE_LABELS
    labels = table.get(degree, table.get("minor", {}))
    formatted = labels.get(wave_upper, wave_upper)

    return WaveLabel(
        wave_number=wave_upper,
        degree=degree,
        formatted=formatted,
        timeframe=timeframe.upper(),
    )


def format_current_wave(wave_number: str, timeframe: str) -> str:
    """Short label like 'Wave (4)' or 'Wave iii'."""
    wl = label_wave(wave_number, timeframe)
    return f"Wave {wl.formatted}"


def format_wave_with_degree(wave_number: str, timeframe: str) -> str:
    """Full label like 'Wave (4) of Intermediate'."""
    return label_wave(wave_number, timeframe).full_label


def phase_description(wave_number: str, direction: str) -> str:
    """Human-readable phase for a wave number.

    Returns e.g. "Corrective Pullback", "Impulse Extension", etc.
    """
    n = str(wave_number).upper()
    if n in ("2", "4", "B"):
        return "Corrective Pullback" if direction == "bullish" else "Corrective Rebound"
    if n in ("1", "3", "5"):
        return "Impulse Move"
    if n == "A":
        return "Corrective Wave A"
    if n == "C":
        return "Corrective Wave C — Final Leg"
    return "Wave in Progress"
