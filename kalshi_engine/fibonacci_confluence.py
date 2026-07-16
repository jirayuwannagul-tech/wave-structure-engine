"""Fibonacci Confluence Zone detection.

Finds price zones where multiple Fibonacci levels from different swings
cluster together. Confluence zones are high-probability support/resistance areas.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConfluenceZone:
    """A price zone where multiple Fibonacci levels cluster."""
    center: float          # central price of the zone
    low: float             # lower bound
    high: float            # upper bound
    level_count: int       # how many Fib levels fall in this zone
    levels: list[dict]     # list of {"source": str, "ratio": str, "price": float}
    strength: float        # 0.0-1.0 based on level_count and diversity


def find_confluence_zones(
    fib_level_sets: list[dict[str, float]],
    tolerance_pct: float = 0.01,
    min_levels: int = 2,
) -> list[ConfluenceZone]:
    """Find price zones where multiple Fibonacci levels cluster.

    Args:
        fib_level_sets: list of {"source": str, "ratio": str, "price": float} dicts
        tolerance_pct: price tolerance for clustering (default 1%)
        min_levels: minimum number of levels required for a zone

    Returns:
        List of ConfluenceZone sorted by strength (strongest first)
    """
    if not fib_level_sets:
        return []

    # Sort all levels by price
    all_levels = sorted(fib_level_sets, key=lambda x: x["price"])

    zones: list[ConfluenceZone] = []
    used = set()

    for i, level in enumerate(all_levels):
        if i in used:
            continue

        center = level["price"]
        if center <= 0:
            continue

        tol = center * tolerance_pct
        cluster = [level]
        cluster_indices = {i}

        # Gather all levels within tolerance
        for j, other in enumerate(all_levels):
            if j == i or j in used:
                continue
            if abs(other["price"] - center) <= tol:
                cluster.append(other)
                cluster_indices.add(j)

        if len(cluster) >= min_levels:
            prices = [l["price"] for l in cluster]
            zone_center = sum(prices) / len(prices)
            zone_low = min(prices) * (1 - tolerance_pct / 2)
            zone_high = max(prices) * (1 + tolerance_pct / 2)

            # Strength based on count and source diversity
            sources = {l.get("source", "") for l in cluster}
            diversity = len(sources) / max(len(cluster), 1)
            strength = min(1.0, (len(cluster) / 5) * 0.7 + diversity * 0.3)

            zones.append(ConfluenceZone(
                center=round(zone_center, 4),
                low=round(zone_low, 4),
                high=round(zone_high, 4),
                level_count=len(cluster),
                levels=cluster,
                strength=round(strength, 3),
            ))
            used.update(cluster_indices)

    return sorted(zones, key=lambda z: z.strength, reverse=True)


def build_fib_levels_from_swing(
    source_name: str,
    swing_start: float,
    swing_end: float,
    ratios: list[float] | None = None,
) -> list[dict]:
    """Build Fibonacci levels from a single swing.

    Args:
        source_name: label for this swing (e.g., "W1", "ABC_A")
        swing_start: price where swing began
        swing_end: price where swing ended
        ratios: Fibonacci ratios to calculate (default: standard retracements)

    Returns:
        List of {"source", "ratio", "price"} dicts
    """
    if ratios is None:
        ratios = [0.236, 0.382, 0.500, 0.618, 0.786, 1.0, 1.272, 1.618]

    move = swing_end - swing_start
    if abs(move) == 0:
        return []

    levels = []
    for r in ratios:
        if move > 0:
            # Upswing: retracements go DOWN from swing_end
            price = swing_end - move * r
        else:
            # Downswing: retracements go UP from swing_end
            price = swing_end - move * r

        levels.append({
            "source": source_name,
            "ratio": str(round(r, 3)),
            "price": round(price, 4),
        })

    return levels


def score_entry_vs_confluence(entry_price: float, zones: list[ConfluenceZone]) -> float:
    """Score how well an entry price aligns with confluence zones.

    Returns 0.0-1.0: higher is better (entry at confluence zone).
    """
    if not zones:
        return 0.0

    for zone in zones:
        if zone.low <= entry_price <= zone.high:
            return zone.strength

    # Partial score for being close to a zone
    closest_dist = min(
        abs(entry_price - z.center) / z.center for z in zones if z.center > 0
    )
    if closest_dist < 0.02:  # within 2%
        return 0.3

    return 0.0
