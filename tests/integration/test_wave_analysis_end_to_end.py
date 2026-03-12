from analysis.future_projection import project_next_wave
from analysis.key_levels import extract_abc_key_levels, extract_pattern_key_levels
from analysis.pivot_detector import detect_pivots
from analysis.wave_detector import detect_latest_abc, detect_latest_impulse
from analysis.wave_position import detect_wave_position
from analysis.wxy_detector import WXYPattern
from analysis.swing_builder import SwingPoint
from data.candle_utils import drop_unclosed_candle
from data.market_data_fetcher import MarketDataFetcher
from output.report_formatter import format_report
from scenarios.scenario_engine import generate_scenarios


class DummyResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_end_to_end_wave_analysis_flow(monkeypatch):
    sample_payload = [
        [1704067200000, "100", "105", "95", "102", "1000", 1704153599000, "100000", 10, "500", "50000", "0"],
        [1704153600000, "102", "120", "100", "118", "1200", 1704239999000, "120000", 12, "600", "60000", "0"],
        [1704240000000, "118", "110", "90", "95", "900", 1704326399000, "90000", 9, "400", "40000", "0"],
        [1704326400000, "95", "130", "94", "128", "1500", 1704412799000, "150000", 15, "700", "70000", "0"],
        [1704412800000, "128", "115", "92", "96", "1100", 1704499199000, "110000", 11, "500", "50000", "0"],
        [1704499200000, "96", "140", "95", "138", "1600", 1704585599000, "160000", 16, "800", "80000", "0"],
        [1704585600000, "138", "118", "98", "105", "1000", 1704671999000, "100000", 10, "500", "50000", "0"],
    ]

    def fake_get(*args, **kwargs):
        return DummyResponse(sample_payload)

    monkeypatch.setattr("data.market_data_fetcher.requests.get", fake_get)

    fetcher = MarketDataFetcher(symbol="BTCUSDT", interval="1d", limit=7)
    df = drop_unclosed_candle(fetcher.fetch_ohlcv())

    pivots = detect_pivots(df, left=1, right=1)
    abc = detect_latest_abc(pivots)
    impulse = detect_latest_impulse(pivots)

    assert len(pivots) >= 3
    assert abc is not None or impulse is not None

    if abc is not None:
        position = detect_wave_position(abc_pattern=abc, impulse_pattern=impulse)
        key_levels = extract_abc_key_levels(abc)
        projection = project_next_wave(position, key_levels)
        scenarios = generate_scenarios(position, key_levels, projection)

        assert position.structure in ["ABC_CORRECTION", "IMPULSE"]
        assert len(scenarios) >= 1


def test_pattern_flow_supports_wxy_end_to_end():
    pattern = WXYPattern(
        pattern_type="WXY",
        direction="bullish",
        w=SwingPoint(index=1, price=100.0, type="L", timestamp="2026-01-01"),
        x=SwingPoint(index=2, price=120.0, type="H", timestamp="2026-01-02"),
        y=SwingPoint(index=3, price=110.0, type="L", timestamp="2026-01-03"),
        wx_length=20.0,
        xy_length=10.0,
        y_vs_w_ratio=0.5,
    )

    position = detect_wave_position(pattern_type="WXY", pattern=pattern)
    key_levels = extract_pattern_key_levels("WXY", pattern)
    projection = project_next_wave(position, key_levels)
    scenarios = generate_scenarios(position, key_levels, projection)
    report = format_report(
        symbol="BTCUSDT",
        timeframe="4H",
        current_price=111.0,
        pattern=pattern,
        pattern_type="WXY",
        position=position,
        scenarios=scenarios,
        confidence=0.82,
        probability=0.15,
        wave_summary={"current_wave": "WXY", "bias": "BULLISH", "alternate_wave": "ABC_CORRECTION"},
    )

    assert position.structure == "WXY"
    assert key_levels is not None
    assert projection.expected_direction == "UP"
    assert len(scenarios) >= 1
    assert "WXY structure detected:" in report
