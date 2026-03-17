from tests.wave_validation_labels import run_validation


def test_weekly_wave_validation_labels_are_all_correct():
    result = run_validation(verbose=False)

    assert result["total"] == 20
    assert result["passed"] == 20
