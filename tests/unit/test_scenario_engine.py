from analysis.future_projection import FutureProjection
from analysis.key_levels import KeyLevels
from analysis.wave_position import WavePosition
from scenarios.scenario_engine import Scenario, generate_inprogress_scenarios, generate_scenarios, prioritize_scenarios


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
    assert len(scenarios[0].targets) == 1
    assert scenarios[0].targets == [76271.5]


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
    assert scenarios[1].bias == "BULLISH"
    assert scenarios[1].targets == [85070.0, 88067.44, 91880.36]


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
    assert scenarios[0].stop_loss < scenarios[0].confirmation


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


def test_generate_scenarios_for_generic_correction_uses_corrective_branch():
    position = WavePosition(
        structure="CORRECTION",
        position="IN_WAVE_A",
        bias="BEARISH",
        confidence="medium",
    )

    key_levels = KeyLevels(
        structure_type="correction",
        support=80.0,
        resistance=100.0,
        invalidation=105.0,
        confirmation=80.0,
        wave_start=100.0,
        wave_end=85.0,
        c_level=100.0,
    )

    projection = FutureProjection(
        expected_structure="NEW_BEARISH_IMPULSE",
        expected_direction="DOWN",
        target_1=72.0,
        target_2=68.0,
        target_3=64.0,
        invalidation=105.0,
        confirmation=80.0,
        stop_loss=105.0,
        message="correction likely finished",
    )

    scenarios = generate_scenarios(position, key_levels, projection)

    assert scenarios
    assert scenarios[0].bias == "BEARISH"
    assert scenarios[0].confirmation == 80.0
    assert scenarios[0].stop_loss > scenarios[0].confirmation


def test_generate_inprogress_scenarios_bearish_geometry_is_valid():
    from types import SimpleNamespace

    inprogress = SimpleNamespace(
        is_valid=True,
        fib_targets={"0.236": 97.0, "0.382": 95.0, "0.5": 92.0},
        invalidation=90.0,
        current_wave_start=100.0,
        current_wave_direction="bearish",
        wave_number="4",
    )

    scenarios = generate_inprogress_scenarios(inprogress, current_price=110.0)

    assert scenarios
    scenario = scenarios[0]
    assert scenario.bias == "BEARISH"
    assert scenario.stop_loss > scenario.confirmation
    assert all(target < scenario.confirmation for target in scenario.targets)


def test_generate_inprogress_scenarios_bullish_geometry_is_valid():
    from types import SimpleNamespace

    inprogress = SimpleNamespace(
        is_valid=True,
        fib_targets={"1.0": 104.0, "1.272": 108.0, "1.618": 112.0},
        invalidation=90.0,
        current_wave_start=100.0,
        current_wave_direction="bullish",
        wave_number="3",
    )

    scenarios = generate_inprogress_scenarios(inprogress, current_price=95.0)

    assert scenarios
    scenario = scenarios[0]
    assert scenario.bias == "BULLISH"
    assert scenario.stop_loss < scenario.confirmation
    assert all(target > scenario.confirmation for target in scenario.targets)


def test_prioritize_scenarios_prefers_positive_scenario_edge(monkeypatch):
    class Edge:
        sample_count = 5
        win_rate = 0.6
        avg_r = 0.4
        positive = True
        negative = False
        severe_negative = False

    monkeypatch.setattr("scenarios.scenario_engine.get_pair_edge", lambda *args, **kwargs: None)
    monkeypatch.setattr("scenarios.scenario_engine.get_pattern_edge", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "scenarios.scenario_engine.get_scenario_edge",
        lambda *args, **kwargs: Edge() if args[3] == "Alternate Bullish" else None,
    )

    scenarios = [
        Scenario(
            name="Main Bearish",
            condition="price breaks below 90.0",
            interpretation="downside continuation",
            target="80.0",
            bias="BEARISH",
            invalidation=105.0,
            confirmation=90.0,
            stop_loss=105.0,
            targets=[82.0, 78.0, 74.0],
        ),
        Scenario(
            name="Alternate Bullish",
            condition="price breaks above 100.0",
            interpretation="bullish recovery",
            target="112.0",
            bias="BULLISH",
            invalidation=92.0,
            confirmation=100.0,
            stop_loss=92.0,
            targets=[112.0, 118.0, 124.0],
        ),
    ]

    prioritized = prioritize_scenarios(
        symbol="BTCUSDT",
        timeframe="1D",
        structure="EXPANDED_FLAT",
        projection=None,
        scenarios=scenarios,
    )

    assert prioritized
    assert prioritized[0].name == "Alternate Bullish"


def test_prioritize_scenarios_skips_trade_when_only_negative_history_exists(monkeypatch):
    class Edge:
        sample_count = 4
        win_rate = 0.0
        avg_r = -0.9
        positive = False
        negative = True
        severe_negative = True

    monkeypatch.setattr("scenarios.scenario_engine.get_pair_edge", lambda *args, **kwargs: None)
    monkeypatch.setattr("scenarios.scenario_engine.get_pattern_edge", lambda *args, **kwargs: None)
    monkeypatch.setattr("scenarios.scenario_engine.get_scenario_edge", lambda *args, **kwargs: Edge())

    scenarios = [
        Scenario(
            name="Bullish Breakout",
            condition="price breaks above 120.0",
            interpretation="triangle resolves upward",
            target="140.0",
            bias="BULLISH",
            invalidation=100.0,
            confirmation=120.0,
            stop_loss=100.0,
            targets=[140.0],
        )
    ]

    prioritized = prioritize_scenarios(
        symbol="ETHUSDT",
        timeframe="4H",
        structure="ASCENDING_BARRIER_TRIANGLE",
        projection=FutureProjection(
            expected_structure="BREAKOUT",
            expected_direction="NEUTRAL",
            target_1=140.0,
            target_2=None,
            target_3=None,
            invalidation=100.0,
            confirmation=120.0,
            stop_loss=100.0,
            message="triangle",
        ),
        scenarios=scenarios,
    )

    assert prioritized == []


def test_prioritize_scenarios_skips_pair_with_negative_pair_edge(monkeypatch):
    class Edge:
        sample_count = 80
        win_rate = 0.42
        avg_r = -0.08
        positive = False
        negative = False
        severe_negative = False

    monkeypatch.setattr("scenarios.scenario_engine.get_pair_edge", lambda *args, **kwargs: Edge())
    monkeypatch.setattr("scenarios.scenario_engine.get_pattern_edge", lambda *args, **kwargs: None)
    monkeypatch.setattr("scenarios.scenario_engine.get_scenario_edge", lambda *args, **kwargs: None)

    scenarios = [
        Scenario(
            name="Main Bearish",
            condition="price breaks below 32.0",
            interpretation="downside continuation",
            target="28.0",
            bias="BEARISH",
            invalidation=35.0,
            confirmation=32.0,
            stop_loss=35.0,
            targets=[30.0, 28.0, 26.0],
        )
    ]

    prioritized = prioritize_scenarios(
        symbol="AVAXUSDT",
        timeframe="4H",
        structure="RUNNING_FLAT",
        projection=None,
        scenarios=scenarios,
    )

    assert prioritized == []


def test_prioritize_scenarios_does_not_pair_prune_1d_history(monkeypatch):
    class Edge:
        sample_count = 80
        win_rate = 0.42
        avg_r = -0.08
        positive = False
        negative = False
        severe_negative = False

    monkeypatch.setattr("scenarios.scenario_engine.get_pair_edge", lambda *args, **kwargs: Edge())
    monkeypatch.setattr("scenarios.scenario_engine.get_pattern_edge", lambda *args, **kwargs: None)
    monkeypatch.setattr("scenarios.scenario_engine.get_scenario_edge", lambda *args, **kwargs: None)

    scenario = Scenario(
        name="Main Bearish",
        condition="price breaks below 32.0",
        interpretation="downside continuation",
        target="28.0",
        bias="BEARISH",
        invalidation=35.0,
        confirmation=32.0,
        stop_loss=35.0,
        targets=[30.0, 28.0, 26.0],
    )

    prioritized = prioritize_scenarios(
        symbol="AVAXUSDT",
        timeframe="1D",
        structure="RUNNING_FLAT",
        projection=None,
        scenarios=[scenario],
    )

    assert prioritized == [scenario]
