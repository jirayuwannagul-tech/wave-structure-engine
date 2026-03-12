from analysis.fibonacci_engine import measure_extension, measure_retracement


def test_measure_retracement_up_move():
    result = measure_retracement(100.0, 200.0)

    assert result.direction == "up"
    assert round(result.levels[0.5], 2) == 150.00
    assert round(result.levels[1.0], 2) == 100.00


def test_measure_extension_up_move():
    result = measure_extension(100.0, 200.0, 150.0)

    assert result.direction == "up"
    assert round(result.levels[1.0], 2) == 250.00
    assert round(result.levels[1.618], 2) == 311.80