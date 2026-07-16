from __future__ import annotations


SUBTYPES = {
    "IMPULSE": "standard_impulse",
    "ABC_CORRECTION": "abc",
    "ZIGZAG": "zigzag",
    "FLAT": "regular_flat",
    "EXPANDED_FLAT": "expanded_flat",
    "RUNNING_FLAT": "running_flat",
    "TRIANGLE": "contracting_triangle",
    "WXY": "complex_correction",
    "LEADING_DIAGONAL": "leading_diagonal",
    "ENDING_DIAGONAL": "ending_diagonal",
}


def get_subtype(pattern_type: str) -> str | None:
    return SUBTYPES.get((pattern_type or "").upper())


def list_subtypes() -> list[str]:
    return sorted(set(SUBTYPES.values()))