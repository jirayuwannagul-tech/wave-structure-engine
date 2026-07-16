from __future__ import annotations


DEGREE_BY_TIMEFRAME = {
    "1W": "primary",
    "1D": "intermediate",
    "4H": "minor",
    "1H": "minute",
}


def get_degree(timeframe: str) -> str:
    return DEGREE_BY_TIMEFRAME.get((timeframe or "").upper(), "unknown")


def list_degrees() -> list[str]:
    return sorted(set(DEGREE_BY_TIMEFRAME.values()))