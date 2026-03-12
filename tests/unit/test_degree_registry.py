from analysis.patterns.degree_registry import get_degree, list_degrees


def test_get_degree_known_timeframes():
    assert get_degree("1W") == "primary"
    assert get_degree("1D") == "intermediate"
    assert get_degree("4H") == "minor"


def test_get_degree_unknown_timeframe():
    assert get_degree("15m") == "unknown"


def test_list_degrees():
    degrees = list_degrees()

    assert "primary" in degrees
    assert "intermediate" in degrees
    assert "minor" in degrees