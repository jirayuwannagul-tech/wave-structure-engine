from __future__ import annotations


FAMILIES = {
    "IMPULSE": "motive",
    "ABC_CORRECTION": "corrective",
    "ZIGZAG": "corrective",
    "FLAT": "corrective",
    "EXPANDED_FLAT": "corrective",
    "RUNNING_FLAT": "corrective",
    "TRIANGLE": "corrective",
    "WXY": "combination",
    "LEADING_DIAGONAL": "diagonal",
    "ENDING_DIAGONAL": "diagonal",
}


def get_family(pattern_type: str) -> str | None:
    return FAMILIES.get((pattern_type or "").upper())


def list_families() -> list[str]:
    return sorted(set(FAMILIES.values()))