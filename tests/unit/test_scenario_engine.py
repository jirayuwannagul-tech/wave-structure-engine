from analysis.future_projection import FutureProjection
from analysis.key_levels import KeyLevels
from analysis.wave_position import WavePosition
from scenarios.scenario_engine import generate_scenarios


def test_generate_scenarios_for_bullish_abc():
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

    projection = FutureProjection(
        expected_structure="NEW_BULLISH_IMPULSE",
        expected_direction="UP",
        target_1=74050.0,
        target_2=74050.0,
        target_3=76271.5,
        invalidation=65618.49,
        confirmation=74050.0,
        stop_loss=65618.49,
        message="if price holds above C, upside continuation becomes more likely",
    )

    scenarios = generate_scenarios(position, key_levels, projection)

    assert len(scenarios) >= 1
    assert scenarios[0].bias == "BULLISH"
    assert scenarios[0].confirmation == 74050.0
    assert scenarios[0].stop_loss == 65618.49
    assert scenarios[0].condition == "price breaks above 74050.0"
    assert len(scenarios[0].targets) == 2
    assert scenarios[0].targets == [74050.0, 76271.5]


def test_generate_scenarios_for_bearish_corrective_uses_confirmation_break():
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

    projection = FutureProjection(
        expected_structure="NEW_BEARISH_IMPULSE",
        expected_direction="DOWN",
        target_1=52010.0,
        target_2=49012.56,
        target_3=45199.64,
        invalidation=74050.0,
        confirmation=63030.0,
        stop_loss=74050.0,
        message="if price breaks below confirmation, bearish continuation becomes more likely",
    )

    scenarios = generate_scenarios(position, key_levels, projection)

    assert scenarios[0].bias == "BEARISH"
    assert scenarios[0].condition == "price breaks below 63030.0"
    assert scenarios[0].targets == [52010.0, 49012.56, 45199.64]


def test_generate_scenarios_for_bearish_impulse():
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

    projection = FutureProjection(
        expected_structure="ABC_CORRECTION",
        expected_direction="UP",
        target_1=72271.41,
        target_2=91224.99,
        target_3=93961.74,
        invalidation=91224.99,
        confirmation=65118.0,
        stop_loss=65118.0,
        message="after completed bearish impulse, corrective rebound is likely",
    )

    scenarios = generate_scenarios(position, key_levels, projection)

    assert len(scenarios) >= 1
    assert scenarios[0].bias == "BULLISH"
    assert scenarios[0].confirmation == 65118.0
    assert scenarios[0].stop_loss == 65118.0


def test_generate_scenarios_for_triangle():
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

    projection = FutureProjection(
        expected_structure="BREAKOUT",
        expected_direction="NEUTRAL",
        target_1=120.0,
        target_2=100.0,
        target_3=None,
        invalidation=100.0,
        confirmation=120.0,
        stop_loss=None,
        message="triangle usually resolves with a breakout from the range",
    )

    scenarios = generate_scenarios(position, key_levels, projection)

    assert len(scenarios) == 2
    assert scenarios[0].bias == "BULLISH"
    assert scenarios[1].bias == "BEARISH"
