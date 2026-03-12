from analysis.future_projection import project_next_wave
from analysis.key_levels import KeyLevels
from analysis.wave_position import WavePosition


def test_project_next_wave_from_bullish_abc():
    position = WavePosition(
        structure="ABC_CORRECTION",
        position="WAVE_C_END",
        bias="BULLISH",
        confidence="medium",
    )

    key_levels = KeyLevels(
        structure_type="abc",
        support=65618.49,
        resistance=74050.0,
        invalidation=65618.49,
        confirmation=74050.0,
        wave_start=63030.0,
        wave_end=65618.49,
        b_level=74050.0,
        c_level=65618.49,
    )

    result = project_next_wave(position, key_levels)

    assert result.expected_structure == "NEW_BULLISH_IMPULSE"
    assert result.expected_direction == "UP"
    assert result.target_1 is not None
    assert result.target_1 > key_levels.confirmation
    assert result.invalidation == 65618.49
    assert result.confirmation == 74050.0


def test_project_next_wave_from_bearish_impulse():
    position = WavePosition(
        structure="IMPULSE",
        position="WAVE_5_COMPLETE",
        bias="BEARISH",
        confidence="medium",
    )

    key_levels = KeyLevels(
        structure_type="impulse",
        support=65118.0,
        resistance=72271.41,
        invalidation=91224.99,
        confirmation=65118.0,
        wave_start=91224.99,
        wave_end=65118.0,
    )

    result = project_next_wave(position, key_levels)

    assert result.expected_structure == "ABC_CORRECTION"
    assert result.expected_direction == "UP"
    assert result.target_1 is not None
    assert result.target_1 > key_levels.resistance
    assert result.target_2 is not None


def test_project_next_wave_from_triangle():
    position = WavePosition(
        structure="TRIANGLE",
        position="CONSOLIDATION_END",
        bias="NEUTRAL",
        confidence="medium",
    )

    key_levels = KeyLevels(
        structure_type="triangle",
        support=100.0,
        resistance=120.0,
        invalidation=100.0,
        confirmation=120.0,
        wave_start=120.0,
        wave_end=110.0,
    )

    result = project_next_wave(position, key_levels)

    assert result.expected_structure == "BREAKOUT"
    assert result.expected_direction == "NEUTRAL"
    assert result.target_1 == 120.0
    assert result.target_2 == 100.0
