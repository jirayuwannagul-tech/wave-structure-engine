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


def test_project_next_wave_from_bearish_corrective_projects_below_confirmation():
    position = WavePosition(
        structure="EXPANDED_FLAT",
        position="CORRECTION_COMPLETE",
        bias="BEARISH",
        confidence="medium",
    )

    key_levels = KeyLevels(
        structure_type="expanded_flat",
        support=63030.0,
        resistance=74050.0,
        invalidation=74050.0,
        confirmation=63030.0,
        wave_start=69988.83,
        wave_end=74050.0,
        b_level=63030.0,
        c_level=74050.0,
    )

    result = project_next_wave(position, key_levels)

    assert result.expected_structure == "NEW_BEARISH_IMPULSE"
    assert result.expected_direction == "DOWN"
    assert result.target_1 is not None
    assert result.target_1 < key_levels.confirmation
    assert result.target_2 is not None
    assert result.target_2 < result.target_1
    assert result.target_3 is not None
    assert result.target_3 < result.target_2


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


def test_project_next_wave_from_bullish_impulse():
    position = WavePosition(
        structure="IMPULSE",
        position="WAVE_5_COMPLETE",
        bias="BULLISH",
        confidence="high",
    )
    key_levels = KeyLevels(
        structure_type="impulse",
        support=100.0,
        resistance=150.0,
        invalidation=80.0,
        confirmation=150.0,
        wave_start=80.0,
        wave_end=150.0,
    )
    result = project_next_wave(position, key_levels)
    assert result.expected_structure == "ABC_CORRECTION"
    assert result.expected_direction == "DOWN"
    assert result.target_1 is not None
    assert result.invalidation == 80.0


def test_project_next_wave_from_ending_diagonal_bullish():
    position = WavePosition(
        structure="ENDING_DIAGONAL",
        position="WAVE_5_COMPLETE",
        bias="BULLISH",
        confidence="medium",
    )
    key_levels = KeyLevels(
        structure_type="ending_diagonal",
        support=90.0,
        resistance=130.0,
        invalidation=85.0,
        confirmation=130.0,
        wave_start=85.0,
        wave_end=130.0,
    )
    result = project_next_wave(position, key_levels)
    assert result.expected_structure == "ABC_CORRECTION"
    assert result.expected_direction == "DOWN"


def test_project_next_wave_unknown_structure():
    position = WavePosition(
        structure="UNKNOWN",
        position="UNKNOWN",
        bias="NEUTRAL",
        confidence="low",
    )
    key_levels = KeyLevels(
        structure_type="unknown",
        support=None,
        resistance=None,
        invalidation=None,
        confirmation=None,
        wave_start=None,
        wave_end=None,
    )
    result = project_next_wave(position, key_levels)
    assert result.expected_structure == "UNKNOWN"
    assert result.expected_direction == "NEUTRAL"
    assert result.target_1 is None
    assert result.message == "structure is currently ambiguous"


def test_project_next_wave_flat_bullish_same_as_corrective():
    position = WavePosition(
        structure="FLAT",
        position="WAVE_C_END",
        bias="BULLISH",
        confidence="medium",
    )
    key_levels = KeyLevels(
        structure_type="flat",
        support=95.0,
        resistance=110.0,
        invalidation=95.0,
        confirmation=110.0,
        wave_start=95.0,
        wave_end=100.0,
    )
    result = project_next_wave(position, key_levels)
    assert result.expected_structure == "NEW_BULLISH_IMPULSE"


def test_project_next_wave_wxy_bearish():
    position = WavePosition(
        structure="WXY",
        position="CORRECTION_COMPLETE",
        bias="BEARISH",
        confidence="medium",
    )
    key_levels = KeyLevels(
        structure_type="wxy",
        support=80.0,
        resistance=100.0,
        invalidation=105.0,
        confirmation=80.0,
        wave_start=100.0,
        wave_end=85.0,
    )
    result = project_next_wave(position, key_levels)
    assert result.expected_structure == "NEW_BEARISH_IMPULSE"
    assert result.expected_direction == "DOWN"
