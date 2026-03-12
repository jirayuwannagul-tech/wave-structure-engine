import pandas as pd

from live.wave_recount_engine import recount_wave


def test_wave_recount_engine_runs():

    df = pd.read_csv("data/BTCUSDT_1d.csv")

    result = recount_wave(df)

    assert result is None or "bias" in result


def test_wave_recount_engine_uses_primary_pattern(monkeypatch):
    monkeypatch.setattr(
        "live.wave_recount_engine.detect_pivots",
        lambda df: ["dummy-pivots"],
    )
    monkeypatch.setattr(
        "live.wave_recount_engine.generate_labeled_wave_counts",
        lambda pivots, timeframe, df=None: [
            {
                "pattern_type": "WXY",
                "direction": "BULLISH",
                "pattern": type("Pattern", (), {"direction": "bullish"})(),
                "confidence": 0.82,
                "probability": 0.15,
            }
        ],
    )
    monkeypatch.setattr(
        "live.wave_recount_engine.build_wave_summary",
        lambda labeled_counts: {"bias": "BULLISH"},
    )
    monkeypatch.setattr(
        "live.wave_recount_engine.detect_wave_position",
        lambda pattern_type, pattern: type(
            "Position",
            (),
            {"structure": pattern_type, "bias": "BULLISH"},
        )(),
    )

    result = recount_wave(pd.DataFrame({"close": [1.0, 2.0]}))

    assert result == {"structure": "WXY", "bias": "BULLISH"}
