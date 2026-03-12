from analysis.wave_position import WavePosition
from monitor.mtf_alignment import evaluate_mtf_alignment


def test_all_bullish_alignment():
    positions = {
        "1W": WavePosition(structure="ABC_CORRECTION", position="WAVE_C_END", bias="BULLISH", confidence="medium"),
        "1D": WavePosition(structure="ABC_CORRECTION", position="WAVE_C_END", bias="BULLISH", confidence="medium"),
        "4H": WavePosition(structure="ABC_CORRECTION", position="WAVE_C_END", bias="BULLISH", confidence="medium"),
    }

    result = evaluate_mtf_alignment(positions)

    assert result.state == "full_bullish_alignment"


def test_all_bearish_alignment():
    positions = {
        "1W": WavePosition(structure="ABC_CORRECTION", position="WAVE_C_END", bias="BEARISH", confidence="medium"),
        "1D": WavePosition(structure="ABC_CORRECTION", position="WAVE_C_END", bias="BEARISH", confidence="medium"),
        "4H": WavePosition(structure="ABC_CORRECTION", position="WAVE_C_END", bias="BEARISH", confidence="medium"),
    }

    result = evaluate_mtf_alignment(positions)

    assert result.state == "full_bearish_alignment"


def test_mixed_alignment():
    positions = {
        "1W": WavePosition(structure="ABC_CORRECTION", position="WAVE_C_END", bias="BEARISH", confidence="medium"),
        "1D": WavePosition(structure="ABC_CORRECTION", position="WAVE_C_END", bias="BULLISH", confidence="medium"),
        "4H": WavePosition(structure="ABC_CORRECTION", position="WAVE_C_END", bias="BULLISH", confidence="medium"),
    }

    result = evaluate_mtf_alignment(positions)

    assert result.state == "mixed_alignment"