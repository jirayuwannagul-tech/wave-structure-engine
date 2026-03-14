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


def test_measure_retracement_down_move():
    result = measure_retracement(200.0, 100.0)
    assert result.direction == "down"
    # Down move: retracement levels are above end_price
    assert round(result.levels[0.5], 2) == 150.00
    assert round(result.levels[1.0], 2) == 200.00


def test_measure_retracement_all_levels_present():
    result = measure_retracement(100.0, 200.0)
    from analysis.fibonacci_engine import FIB_LEVELS
    for level in FIB_LEVELS:
        assert level in result.levels


def test_measure_extension_down_move():
    result = measure_extension(200.0, 100.0, 150.0)
    assert result.direction == "down"
    # Down extension from anchor 150.0: levels go downward
    assert round(result.levels[1.0], 2) == 50.00


def test_measure_extension_stores_start_end():
    result = measure_extension(100.0, 150.0, 120.0)
    assert result.start_price == 100.0
    assert result.end_price == 150.0