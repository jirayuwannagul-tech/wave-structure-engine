from types import SimpleNamespace

from storage.experience_store import clear_experience_store_cache, save_experience_store

from analysis.setup_filter import (
    apply_trade_filters,
    extract_trade_bias,
)


def _analysis_with(
    *,
    timeframe="4H",
    confidence=0.9,
    probability=0.6,
    trend_state="UPTREND",
    indicator_validation=True,
    atr_ok=True,
    rsi_divergence="NONE",
    is_ambiguous=False,
    scenarios=None,
):
    return {
        "symbol": "BTCUSDT",
        "timeframe": timeframe,
        "primary_pattern_type": "ABC_CORRECTION",
        "confidence": confidence,
        "probability": probability,
        "trend": SimpleNamespace(state=trend_state),
        "indicator_context": {
            "indicator_validation": indicator_validation,
            "atr_ok": atr_ok,
            "rsi_divergence": rsi_divergence,
        },
        "wave_summary": {"is_ambiguous": is_ambiguous},
        "position": SimpleNamespace(bias="BULLISH"),
        "scenarios": scenarios
        or [
            SimpleNamespace(name="Main Bullish", bias="BULLISH"),
            SimpleNamespace(name="Alternate Bearish", bias="BEARISH"),
        ],
    }


def test_extract_trade_bias_prefers_filtered_scenario_bias():
    analysis = _analysis_with(
        scenarios=[SimpleNamespace(name="Main Bearish", bias="BEARISH")],
    )

    assert extract_trade_bias(analysis) == "BEARISH"


def test_apply_trade_filters_blocks_countertrend_4h_setup():
    analysis = _analysis_with(
        scenarios=[SimpleNamespace(name="Main Bullish", bias="BULLISH")],
    )

    filtered = apply_trade_filters(analysis, higher_timeframe_bias="BEARISH")

    assert filtered["scenarios"] == []
    assert "counter-trend against 1D context" in filtered["trade_filter"]["notes"]


def test_apply_trade_filters_blocks_sideway_without_expansion():
    analysis = _analysis_with(
        trend_state="SIDEWAY",
        indicator_validation=False,
        atr_ok=False,
        rsi_divergence="NONE",
        scenarios=[SimpleNamespace(name="Main Bullish", bias="BULLISH")],
    )

    filtered = apply_trade_filters(analysis)

    assert filtered["scenarios"] == []
    assert filtered["trade_filter"]["regime_blocked"] is True


def test_apply_trade_filters_requires_higher_quality_for_alternate():
    analysis = _analysis_with(
        confidence=0.8,
        probability=0.45,
        indicator_validation=False,
        scenarios=[SimpleNamespace(name="Alternate Bullish", bias="BULLISH")],
    )

    filtered = apply_trade_filters(analysis)

    assert filtered["scenarios"] == []


def test_apply_trade_filters_blocks_negative_pattern_edge_for_4h(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPERIENCE_STORE_PATH", str(tmp_path / "experience_store.json"))
    clear_experience_store_cache()
    save_experience_store(
        {
            "version": 1,
            "patterns": {
                "BTCUSDT|4H|ABC_CORRECTION|LONG": {
                    "sample_count": 8,
                    "win_count": 1,
                    "loss_count": 7,
                    "win_rate": 0.125,
                    "avg_r": -0.42,
                    "total_r": -3.36,
                }
            },
        }
    )

    analysis = _analysis_with(
        scenarios=[SimpleNamespace(name="Main Bullish", bias="BULLISH")],
    )

    filtered = apply_trade_filters(analysis)

    assert filtered["scenarios"] == []
    assert "experience store blocked negative pattern edge" in filtered["trade_filter"]["notes"]


def test_apply_trade_filters_relaxes_threshold_for_positive_pattern_edge(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPERIENCE_STORE_PATH", str(tmp_path / "experience_store.json"))
    clear_experience_store_cache()
    save_experience_store(
        {
            "version": 1,
            "patterns": {
                "BTCUSDT|4H|ABC_CORRECTION|LONG": {
                    "sample_count": 5,
                    "win_count": 3,
                    "loss_count": 2,
                    "win_rate": 0.6,
                    "avg_r": 0.13,
                    "total_r": 0.65,
                }
            },
        }
    )

    analysis = _analysis_with(
        confidence=0.68,
        scenarios=[SimpleNamespace(name="Main Bullish", bias="BULLISH")],
    )

    filtered = apply_trade_filters(analysis)

    assert len(filtered["scenarios"]) == 1
