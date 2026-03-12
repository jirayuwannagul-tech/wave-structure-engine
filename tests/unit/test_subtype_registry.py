from analysis.patterns.subtype_registry import get_subtype, list_subtypes


def test_get_subtype_known_pattern():
    assert get_subtype("IMPULSE") == "standard_impulse"
    assert get_subtype("EXPANDED_FLAT") == "expanded_flat"
    assert get_subtype("WXY") == "complex_correction"


def test_get_subtype_unknown_pattern():
    assert get_subtype("UNKNOWN") is None


def test_list_subtypes():
    subtypes = list_subtypes()

    assert "standard_impulse" in subtypes
    assert "expanded_flat" in subtypes
    assert "complex_correction" in subtypes