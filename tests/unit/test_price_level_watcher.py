from analysis.price_level_watcher import Level, check_levels


def test_check_levels_hit():
    alerts = check_levels(
        69180,
        [
            Level("4H Support", 69266, "support"),
            Level("4H Resistance", 71777, "resistance"),
        ],
    )

    assert len(alerts) == 1
    assert "4H Support" in alerts[0]


def test_check_levels_break_support():
    alerts = check_levels(
        68000,
        [
            Level("4H Support", 69266, "support"),
            Level("4H Resistance", 71777, "resistance"),
        ],
    )

    assert len(alerts) == 1
    assert "BREAK 4H Support" in alerts[0]


def test_check_levels_no_hit():
    alerts = check_levels(
        70500,
        [
            Level("4H Support", 69266, "support"),
            Level("4H Resistance", 71777, "resistance"),
        ],
    )

    assert alerts == []