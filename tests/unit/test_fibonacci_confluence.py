import pytest

from analysis.fibonacci_confluence import (
    build_fib_levels_from_swing,
    find_confluence_zones,
    score_entry_vs_confluence,
)


def test_find_confluence_zones_clusters():
    levels = [
        {"source": "W1", "ratio": "0.618", "price": 100.0},
        {"source": "W3", "ratio": "1.618", "price": 100.5},
        {"source": "ABC", "ratio": "0.500", "price": 99.8},
    ]
    zones = find_confluence_zones(levels, tolerance_pct=0.01, min_levels=2)
    assert len(zones) >= 1
    assert zones[0].level_count >= 2


def test_find_confluence_zones_no_cluster():
    levels = [
        {"source": "W1", "ratio": "0.618", "price": 100.0},
        {"source": "W3", "ratio": "1.618", "price": 200.0},
    ]
    zones = find_confluence_zones(levels, tolerance_pct=0.01, min_levels=2)
    assert len(zones) == 0


def test_build_fib_levels_from_swing():
    levels = build_fib_levels_from_swing("W1", 100.0, 150.0, ratios=[0.382, 0.618])
    assert len(levels) == 2
    for l in levels:
        assert l["source"] == "W1"
        assert "price" in l


def test_score_entry_vs_confluence_hit():
    zones = find_confluence_zones([
        {"source": "A", "ratio": "0.618", "price": 100.0},
        {"source": "B", "ratio": "0.500", "price": 100.3},
    ], tolerance_pct=0.01)
    score = score_entry_vs_confluence(100.1, zones)
    assert score > 0.0


def test_score_entry_vs_confluence_miss():
    zones = find_confluence_zones([
        {"source": "A", "ratio": "0.618", "price": 100.0},
        {"source": "B", "ratio": "0.500", "price": 100.3},
    ], tolerance_pct=0.01)
    score = score_entry_vs_confluence(200.0, zones)
    assert score == 0.0


# ── find_confluence_zones edge cases ─────────────────────────────────────────

def test_find_confluence_zones_empty_input():
    """Empty input → return [] (line 38)."""
    assert find_confluence_zones([]) == []


def test_find_confluence_zones_skips_zero_center():
    """Level with price=0 → center<=0 → skip (line 52)."""
    levels = [
        {"source": "X", "ratio": "0.618", "price": 0.0},
        {"source": "Y", "ratio": "0.500", "price": 0.0},
    ]
    assert find_confluence_zones(levels, min_levels=2) == []


# ── build_fib_levels_from_swing edge cases ────────────────────────────────────

def test_build_fib_levels_default_ratios():
    """ratios=None → default list used (line 108)."""
    levels = build_fib_levels_from_swing("W1", 100.0, 120.0)
    assert len(levels) == 8


def test_build_fib_levels_zero_move():
    """swing_start == swing_end → return [] (line 112)."""
    assert build_fib_levels_from_swing("W1", 100.0, 100.0, ratios=[0.618]) == []


def test_build_fib_levels_downswing():
    """move < 0 → else branch (line 121)."""
    levels = build_fib_levels_from_swing("W1", 120.0, 100.0, ratios=[0.618])
    assert len(levels) == 1
    # price = 100 - (100-120)*0.618 = 100 + 12.36 = 112.36
    assert levels[0]["price"] == pytest.approx(112.36, abs=0.01)


# ── score_entry_vs_confluence edge cases ──────────────────────────────────────

def test_score_entry_vs_confluence_no_zones():
    """Empty zones → return 0.0 (line 138)."""
    assert score_entry_vs_confluence(100.0, []) == 0.0


def test_score_entry_vs_confluence_near_zone():
    """Price outside zone but within 2% of center → return 0.3 (line 149)."""
    # Zone centered ~100.05, zone_high ≈ 100.6; entry at 101.5 is outside zone
    # but |101.5 - 100.05| / 100.05 ≈ 0.0145 < 0.02 → near zone → 0.3
    zones = find_confluence_zones([
        {"source": "A", "ratio": "0.618", "price": 100.0},
        {"source": "B", "ratio": "0.500", "price": 100.1},
    ], tolerance_pct=0.01)
    assert len(zones) >= 1
    score = score_entry_vs_confluence(101.5, zones)
    assert score == pytest.approx(0.3)
