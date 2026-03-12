from analysis.patterns.family_registry import get_family, list_families


def test_get_family_known_pattern():
    assert get_family("IMPULSE") == "motive"
    assert get_family("ABC_CORRECTION") == "corrective"
    assert get_family("WXY") == "combination"


def test_get_family_unknown_pattern():
    assert get_family("UNKNOWN") is None


def test_list_families():
    families = list_families()

    assert "motive" in families
    assert "corrective" in families
    assert "combination" in families
    assert "diagonal" in families