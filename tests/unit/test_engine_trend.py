import pandas as pd

from analysis.pivot_detector import Pivot
from core.engine import build_dataframe_analysis
from scenarios.scenario_engine import Scenario


class PositionStub:
    structure = "ABC_CORRECTION"
    position = "WAVE_C_END"
    bias = "BULLISH"
    confidence = "medium"
    wave_number = "C"
    building_wave = False


class KeyLevelsStub:
    support = 95.0
    resistance = 120.0
    confirmation = 100.0
    invalidation = 95.0
    c_level = 95.0


class ProjectionStub:
    target_1 = 110.0
    target_2 = 120.0
    target_3 = 130.0
    confirmation = 100.0
    invalidation = 95.0
    stop_loss = 95.0
    expected_direction = "UP"


class PatternStub:
    a = type("A", (), {"price": 90.0})()
    b = type("B", (), {"price": 110.0})()
    c = type("C", (), {"price": 95.0})()
    direction = "bullish"
    bc_vs_ab_ratio = 0.75


def test_build_dataframe_analysis_includes_trend_classification(monkeypatch):
    df = pd.DataFrame(
        {
            "open_time": pd.date_range("2026-01-01", periods=8, freq="D"),
            "open": [100] * 8,
            "high": [102, 110, 106, 118, 112, 125, 120, 130],
            "low": [98, 101, 99, 103, 101, 105, 103, 107],
            "close": [101, 108, 104, 116, 110, 123, 118, 128],
            "volume": [1000] * 8,
        }
    )
    pivots = [
        Pivot(index=1, price=100.0, type="L", timestamp=pd.Timestamp("2026-01-01")),
        Pivot(index=2, price=120.0, type="H", timestamp=pd.Timestamp("2026-01-02")),
        Pivot(index=3, price=108.0, type="L", timestamp=pd.Timestamp("2026-01-03")),
        Pivot(index=4, price=130.0, type="H", timestamp=pd.Timestamp("2026-01-04")),
    ]

    monkeypatch.setattr("core.engine.detect_pivots", lambda data, **kwargs: pivots)
    monkeypatch.setattr(
        "core.engine.build_wave_sequence",
        lambda pivots, inprogress=None: {
            "completed_legs": [],
            "patterns": [],
            "current_leg": {
                "label": "3",
                "structure": "IMPULSE",
                "direction": "bullish",
                "position": "IN_WAVE_3",
                "building": True,
            },
            "last_completed_leg": {"label": "2", "structure": "IMPULSE"},
            "pattern_count": 0,
        },
    )
    monkeypatch.setattr("core.engine.generate_wave_counts", lambda pivots, df=None: ["count"])
    monkeypatch.setattr(
        "core.engine.generate_labeled_wave_counts",
        lambda pivots, timeframe, df=None: [
            {
                "pattern_type": "ABC_CORRECTION",
                "pattern": PatternStub(),
                "probability": 0.2,
                "confidence": 0.8,
                "indicator_context": {
                    "trend_ok": True,
                    "momentum_ok": True,
                    "atr_ok": True,
                    "indicator_validation": True,
                    "rsi_divergence": "BULLISH_RSI_DIVERGENCE",
                    "rsi_divergence_message": "price made a lower low while RSI made a higher low",
                },
            }
        ],
    )
    monkeypatch.setattr("core.engine.extract_pattern_key_levels", lambda pattern_type, pattern: KeyLevelsStub())
    monkeypatch.setattr("core.engine.build_wave_summary", lambda reports: {"current_wave": "ABC_CORRECTION"})
    monkeypatch.setattr("core.engine.detect_wave_position", lambda pattern_type=None, pattern=None, inprogress=None, **kw: PositionStub())
    monkeypatch.setattr("core.engine.project_next_wave", lambda position, key_levels, **kwargs: ProjectionStub())
    monkeypatch.setattr(
        "core.engine.generate_scenarios",
        lambda position, key_levels, projection, **kwargs: [
            Scenario(
                name="Main Bullish",
                condition="test",
                interpretation="test",
                target="test",
                bias="BULLISH",
                invalidation=95.0,
                confirmation=100.0,
                stop_loss=95.0,
                targets=[110.0, 120.0, 130.0],
            )
        ],
    )

    result = build_dataframe_analysis(
        symbol="BTCUSDT",
        timeframe="4H",
        df=df,
        current_price=128.0,
    )

    assert result["has_pattern"] is True
    assert result["trend"].state == "UPTREND"
    assert result["wave_sequence"]["current_leg"]["label"] == "3"
    assert result["position"].wave_number == "3"
    assert "UPTREND" in result["report"]
    assert "HH_HL" in result["report"]
    assert "BULLISH_RSI_DIVERGENCE" in result["report"]


def test_build_dataframe_analysis_keeps_display_scenarios_when_execution_prunes(monkeypatch):
    df = pd.DataFrame(
        {
            "open_time": pd.date_range("2026-01-01", periods=8, freq="D"),
            "open": [100] * 8,
            "high": [102, 110, 106, 118, 112, 125, 120, 130],
            "low": [98, 101, 99, 103, 101, 105, 103, 107],
            "close": [101, 108, 104, 116, 110, 123, 118, 128],
            "volume": [1000] * 8,
        }
    )
    pivots = [
        Pivot(index=1, price=100.0, type="L", timestamp=pd.Timestamp("2026-01-01")),
        Pivot(index=2, price=120.0, type="H", timestamp=pd.Timestamp("2026-01-02")),
        Pivot(index=3, price=108.0, type="L", timestamp=pd.Timestamp("2026-01-03")),
        Pivot(index=4, price=130.0, type="H", timestamp=pd.Timestamp("2026-01-04")),
    ]

    monkeypatch.setattr("core.engine.detect_pivots", lambda data, **kwargs: pivots)
    monkeypatch.setattr("core.engine.build_wave_sequence", lambda pivots, inprogress=None: {"current_leg": {}, "last_completed_leg": {}})
    monkeypatch.setattr("core.engine.generate_wave_counts", lambda pivots, df=None: ["count"])
    monkeypatch.setattr(
        "core.engine.generate_labeled_wave_counts",
        lambda pivots, timeframe, df=None: [{"pattern_type": "ABC_CORRECTION", "pattern": PatternStub(), "probability": 0.2, "confidence": 0.8, "indicator_context": {}}],
    )
    monkeypatch.setattr("core.engine.extract_pattern_key_levels", lambda pattern_type, pattern: KeyLevelsStub())
    monkeypatch.setattr("core.engine.build_wave_summary", lambda reports: {"current_wave": "ABC_CORRECTION"})
    monkeypatch.setattr("core.engine.detect_wave_position", lambda pattern_type=None, pattern=None, inprogress=None, **kw: PositionStub())
    monkeypatch.setattr("core.engine.project_next_wave", lambda position, key_levels, **kwargs: ProjectionStub())
    raw_scenario = Scenario(
        name="Raw Bullish",
        condition="test",
        interpretation="test",
        target="test",
        bias="BULLISH",
        invalidation=95.0,
        confirmation=100.0,
        stop_loss=95.0,
        targets=[110.0],
    )
    monkeypatch.setattr("core.engine.generate_scenarios", lambda position, key_levels, projection, **kwargs: [raw_scenario])
    monkeypatch.setattr("core.engine.prioritize_scenarios", lambda **kwargs: [])

    result = build_dataframe_analysis(
        symbol="BTCUSDT",
        timeframe="4H",
        df=df,
        current_price=128.0,
    )

    assert raw_scenario in result["scenarios"]
    assert result["execution_scenarios"] == []
    assert raw_scenario in result["all_scenarios"]


def test_build_dataframe_analysis_aligns_corrective_levels_to_inprogress_bias(monkeypatch):
    df = pd.DataFrame(
        {
            "open_time": pd.date_range("2026-01-01", periods=8, freq="D"),
            "open": [100] * 8,
            "high": [102, 110, 106, 118, 112, 125, 120, 130],
            "low": [98, 101, 99, 103, 101, 105, 103, 107],
            "close": [101, 108, 104, 116, 110, 123, 118, 128],
            "volume": [1000] * 8,
        }
    )
    pivots = [
        Pivot(index=1, price=100.0, type="L", timestamp=pd.Timestamp("2026-01-01")),
        Pivot(index=2, price=120.0, type="H", timestamp=pd.Timestamp("2026-01-02")),
        Pivot(index=3, price=108.0, type="L", timestamp=pd.Timestamp("2026-01-03")),
        Pivot(index=4, price=130.0, type="H", timestamp=pd.Timestamp("2026-01-04")),
    ]
    captured = {}

    class BearishCorrectiveLevels:
        structure_type = "abc"
        support = 90.0
        resistance = 98.0
        confirmation = 90.0
        invalidation = 98.0
        wave_start = 100.0
        wave_end = 98.0
        b_level = 90.0
        c_level = 98.0

    class InProgressBullishPosition:
        structure = "ABC_CORRECTION"
        position = "IN_WAVE_4"
        bias = "BULLISH"
        confidence = "medium"
        wave_number = "4"
        building_wave = True

    monkeypatch.setattr("core.engine.detect_pivots", lambda data, **kwargs: pivots)
    monkeypatch.setattr("core.engine.build_wave_sequence", lambda pivots, inprogress=None: {"current_leg": {}, "last_completed_leg": {}})
    monkeypatch.setattr("core.engine.generate_wave_counts", lambda pivots, df=None: ["count"])
    monkeypatch.setattr(
        "core.engine.generate_labeled_wave_counts",
        lambda pivots, timeframe, df=None: [{"pattern_type": "ABC_CORRECTION", "pattern": PatternStub(), "probability": 0.2, "confidence": 0.8, "indicator_context": {}}],
    )
    monkeypatch.setattr("core.engine.extract_pattern_key_levels", lambda pattern_type, pattern: BearishCorrectiveLevels())
    monkeypatch.setattr("core.engine.build_wave_summary", lambda reports: {"current_wave": "ABC_CORRECTION"})
    monkeypatch.setattr(
        "core.engine.detect_wave_position",
        lambda pattern_type=None, pattern=None, inprogress=None, **kw: InProgressBullishPosition(),
    )

    def _capture_projection(position, key_levels, **kwargs):
        captured["confirmation"] = key_levels.confirmation
        captured["invalidation"] = key_levels.invalidation
        return ProjectionStub()

    monkeypatch.setattr("core.engine.project_next_wave", _capture_projection)
    monkeypatch.setattr("core.engine.generate_scenarios", lambda position, key_levels, projection, **kwargs: [])

    build_dataframe_analysis(
        symbol="BTCUSDT",
        timeframe="4H",
        df=df,
        current_price=95.0,
    )

    assert captured["confirmation"] == 98.0
    assert captured["invalidation"] == 90.0
