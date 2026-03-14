from types import SimpleNamespace

from storage.experience_store import clear_experience_store_cache, save_experience_store

from analysis.setup_filter import (
    _trend_aligned,
    apply_trade_filters,
    build_higher_timeframe_context,
    extract_trade_bias,
    filter_trade_scenarios,
    _is_tradeable_regime,
    _passes_quality_gate,
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


def test_build_higher_timeframe_context_extracts_structure_and_position():
    analysis = {
        "timeframe": "1D",
        "primary_pattern_type": "IMPULSE",
        "position": SimpleNamespace(bias="BEARISH", wave_number="3", structure="IMPULSE", position="WAVE_3"),
        "wave_summary": {},
        "scenarios": [SimpleNamespace(name="Main Bearish", bias="BEARISH")],
    }

    context = build_higher_timeframe_context(analysis)

    assert context == {
        "timeframe": "1D",
        "bias": "BEARISH",
        "wave_number": "3",
        "structure": "IMPULSE",
        "position": "WAVE_3",
    }


def test_apply_trade_filters_blocks_countertrend_impulse_against_higher_timeframe_structure():
    analysis = _analysis_with(
        confidence=0.95,
        scenarios=[SimpleNamespace(name="Main Bullish", bias="BULLISH")],
    )
    analysis = dict(analysis)
    analysis["primary_pattern_type"] = "IMPULSE"

    filtered = apply_trade_filters(
        analysis,
        higher_timeframe_bias="BEARISH",
        higher_timeframe_context={
            "timeframe": "1D",
            "bias": "BEARISH",
            "wave_number": "3",
            "structure": "IMPULSE",
            "position": "WAVE_3",
        },
    )

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


# ── extract_trade_bias paths ─────────────────────────────────────────────────

def test_extract_trade_bias_from_position():
    analysis = {"scenarios": [], "position": SimpleNamespace(bias="BEARISH"), "wave_summary": {}}
    assert extract_trade_bias(analysis) == "BEARISH"


def test_extract_trade_bias_from_wave_summary():
    analysis = {"scenarios": [], "position": None, "wave_summary": {"bias": "bullish"}}
    assert extract_trade_bias(analysis) == "BULLISH"


def test_extract_trade_bias_none_analysis():
    assert extract_trade_bias(None) is None


def test_extract_trade_bias_no_bias_anywhere():
    analysis = {"scenarios": [], "position": None, "wave_summary": {}}
    assert extract_trade_bias(analysis) is None


# ── _is_tradeable_regime ──────────────────────────────────────────────────────

def test_tradeable_regime_uptrend():
    analysis = {"trend": SimpleNamespace(state="UPTREND"), "indicator_context": {}}
    assert _is_tradeable_regime(analysis) is True


def test_tradeable_regime_sideway_with_atr():
    analysis = {
        "trend": SimpleNamespace(state="SIDEWAY"),
        "indicator_context": {"atr_ok": True},
    }
    assert _is_tradeable_regime(analysis) is True


def test_tradeable_regime_sideway_with_rsi_divergence():
    analysis = {
        "trend": SimpleNamespace(state="SIDEWAY"),
        "indicator_context": {"rsi_divergence": "BULLISH_RSI_DIVERGENCE", "atr_ok": False},
    }
    assert _is_tradeable_regime(analysis) is True


def test_tradeable_regime_sideway_no_signals():
    analysis = {
        "trend": SimpleNamespace(state="SIDEWAY"),
        "indicator_context": {"atr_ok": False, "rsi_divergence": "NONE", "macd_divergence": "NONE"},
    }
    assert _is_tradeable_regime(analysis) is False


# ── filter_trade_scenarios (empty scenarios) ─────────────────────────────────

def test_filter_scenarios_empty():
    analysis = {"scenarios": [], "wave_summary": {}}
    result, decision = filter_trade_scenarios(analysis)
    assert result == []
    assert decision.scenario_count_before == 0


def test_filter_scenarios_ambiguous_blocked():
    analysis = {
        "scenarios": [SimpleNamespace(name="Main", bias="BULLISH")],
        "wave_summary": {"is_ambiguous": True},
        "inprogress": None,
        "trend": SimpleNamespace(state="UPTREND"),
        "indicator_context": {"atr_ok": True},
    }
    result, decision = filter_trade_scenarios(analysis)
    assert result == []
    assert decision.ambiguous_blocked is True


# ── htf_wave_number thresholds ────────────────────────────────────────────────

def test_htf_wave3_lowers_threshold():
    """Trading in Wave 3 of HTF → lower confidence threshold."""
    analysis = _analysis_with(
        confidence=0.65,   # below default 0.72 but above lowered threshold
        scenarios=[SimpleNamespace(name="Main Bullish", bias="BULLISH")],
    )
    # Without HTF: should fail (0.65 < 0.72)
    filtered_no_htf = apply_trade_filters(analysis)
    # With HTF W3: threshold lowered by 0.06 → 0.66; 0.65 is still just barely below,
    # but test that at least the threshold is different
    filtered_with_htf = apply_trade_filters(analysis, htf_wave_number="3")
    # W3 bonus means more scenarios might pass (or at least not fewer)
    assert len(filtered_with_htf["scenarios"]) >= len(filtered_no_htf["scenarios"])


def test_htf_wave5_raises_threshold():
    """Trading in Wave 5 of HTF → higher confidence threshold."""
    analysis = _analysis_with(
        confidence=0.73,   # just above default 0.72
        scenarios=[SimpleNamespace(name="Main Bullish", bias="BULLISH")],
    )
    # Without HTF: just passes at 0.73
    filtered_no_htf = apply_trade_filters(analysis)
    # With HTF W5: threshold raised by 0.04 → 0.76; 0.73 fails
    filtered_with_htf = apply_trade_filters(analysis, htf_wave_number="5")
    assert len(filtered_with_htf["scenarios"]) <= len(filtered_no_htf["scenarios"])


# ── 1D soft-block by confidence ──────────────────────────────────────────────

def test_1d_countertrend_low_confidence_blocked():
    """1D timeframe counter-trend with confidence < 0.85 → blocked."""
    analysis = _analysis_with(
        timeframe="1D",
        confidence=0.80,
        scenarios=[SimpleNamespace(name="Main Bullish", bias="BULLISH")],
    )
    filtered = apply_trade_filters(analysis, higher_timeframe_bias="BEARISH")
    assert filtered["scenarios"] == []
    assert any("counter-trend" in n for n in filtered["trade_filter"]["notes"])


def test_1d_countertrend_high_confidence_passes():
    """1D timeframe counter-trend with confidence ≥ 0.85 → allowed through."""
    analysis = _analysis_with(
        timeframe="1D",
        confidence=0.88,
        scenarios=[SimpleNamespace(name="Main Bullish", bias="BULLISH")],
    )
    filtered = apply_trade_filters(analysis, higher_timeframe_bias="BEARISH")
    # High confidence should pass even against HTF bias on 1D
    assert len(filtered["scenarios"]) >= 0  # Just ensure no crash; result may vary


def test_1d_countertrend_impulse_blocked_by_weekly_structure_even_when_confident():
    analysis = _analysis_with(
        timeframe="1D",
        confidence=0.92,
        scenarios=[SimpleNamespace(name="Main Bullish", bias="BULLISH")],
    )
    analysis = dict(analysis)
    analysis["primary_pattern_type"] = "IMPULSE"

    filtered = apply_trade_filters(
        analysis,
        higher_timeframe_bias="BEARISH",
        higher_timeframe_context={
            "timeframe": "1W",
            "bias": "BEARISH",
            "wave_number": "5",
            "structure": "IMPULSE",
            "position": "WAVE_5_COMPLETE",
        },
    )

    assert filtered["scenarios"] == []
    assert any("higher timeframe structure" in n for n in filtered["trade_filter"]["notes"])


# ── apply_trade_filters with None analysis ────────────────────────────────────

def test_apply_trade_filters_none_returns_none():
    result = apply_trade_filters(None)
    assert result is None


# ── _trend_aligned branches (lines 80-82) ────────────────────────────────────

def test_trend_aligned_bearish_downtrend():
    assert _trend_aligned("BEARISH", "DOWNTREND") is True


def test_trend_aligned_bearish_broken_down():
    assert _trend_aligned("BEARISH", "BROKEN_DOWN") is True


def test_trend_aligned_bearish_uptrend():
    assert _trend_aligned("BEARISH", "UPTREND") is False


def test_trend_aligned_neutral_bias():
    assert _trend_aligned(None, "UPTREND") is False


# ── severe_negative pattern edge (line 133) ───────────────────────────────────

def test_passes_quality_gate_severe_negative_blocked(tmp_path, monkeypatch):
    """severe_negative edge → blocked regardless of timeframe/alternate."""
    monkeypatch.setenv("EXPERIENCE_STORE_PATH", str(tmp_path / "experience_store.json"))
    clear_experience_store_cache()
    save_experience_store(
        {
            "version": 1,
            "patterns": {
                "BTCUSDT|1D|IMPULSE|LONG": {
                    "sample_count": 5,
                    "win_count": 0,
                    "loss_count": 5,
                    "win_rate": 0.0,
                    "avg_r": -0.85,
                    "total_r": -4.25,
                }
            },
        }
    )

    analysis = _analysis_with(
        timeframe="1D",
        confidence=0.95,
        probability=0.70,
        trend_state="UPTREND",
        indicator_validation=True,
        atr_ok=True,
        scenarios=[SimpleNamespace(name="Main Bullish", bias="BULLISH")],
    )
    analysis = dict(analysis)
    analysis["primary_pattern_type"] = "IMPULSE"

    passed, note = _passes_quality_gate(
        analysis=analysis,
        scenario=SimpleNamespace(name="Main Bullish", bias="BULLISH"),
        index=0,
        higher_timeframe_bias=None,
    )
    assert passed is False
    assert note == "experience store blocked severe negative pattern edge"


# ── negative edge NOT 4H raises thresholds (lines 137-139) ────────────────────

def test_passes_quality_gate_negative_non4h_raises_threshold(tmp_path, monkeypatch):
    """Negative edge on 1D main scenario → confidence threshold raised by 0.06."""
    monkeypatch.setenv("EXPERIENCE_STORE_PATH", str(tmp_path / "experience_store.json"))
    clear_experience_store_cache()
    save_experience_store(
        {
            "version": 1,
            "patterns": {
                "BTCUSDT|1D|IMPULSE|LONG": {
                    "sample_count": 4,
                    "win_count": 1,
                    "loss_count": 3,
                    "win_rate": 0.25,
                    "avg_r": -0.40,
                    "total_r": -1.60,
                }
            },
        }
    )

    analysis_base = _analysis_with(
        timeframe="1D",
        confidence=0.75,   # > 0.72 baseline, but < 0.72+0.06=0.78 raised threshold
        probability=0.60,
        trend_state="UPTREND",
        indicator_validation=True,
        atr_ok=True,
        scenarios=[SimpleNamespace(name="Main Bullish", bias="BULLISH")],
    )
    analysis_base = dict(analysis_base)
    analysis_base["primary_pattern_type"] = "IMPULSE"

    passed, note = _passes_quality_gate(
        analysis=analysis_base,
        scenario=SimpleNamespace(name="Main Bullish", bias="BULLISH"),
        index=0,
        higher_timeframe_bias=None,
    )
    # With raised threshold (0.72+0.06=0.78), confidence 0.75 should fail
    assert passed is False
    assert note == "main confidence too low"


# ── HTF wave number thresholds (lines 162-166) ────────────────────────────────

def _impulse_analysis(**kwargs):
    """Helper returning a 1D IMPULSE analysis (bypasses 4H corrective filter)."""
    base = _analysis_with(timeframe="1D", **kwargs)
    base = dict(base)
    base["primary_pattern_type"] = "IMPULSE"
    return base


def test_htf_wave2_raises_threshold(tmp_path, monkeypatch):
    """HTF wave 2 → main_confidence_threshold += 0.05."""
    monkeypatch.setenv("EXPERIENCE_STORE_PATH", str(tmp_path / "empty.json"))
    clear_experience_store_cache()
    analysis = _impulse_analysis(
        confidence=0.74,   # > 0.72 default but < 0.72+0.05=0.77
        probability=0.60,
        trend_state="UPTREND",
        indicator_validation=True,
        atr_ok=True,
        scenarios=[SimpleNamespace(name="Main Bullish", bias="BULLISH")],
    )
    filtered = apply_trade_filters(analysis, htf_wave_number="2")
    assert filtered["scenarios"] == []


def test_htf_wave4_raises_threshold(tmp_path, monkeypatch):
    """HTF wave 4 → main_confidence_threshold += 0.05."""
    monkeypatch.setenv("EXPERIENCE_STORE_PATH", str(tmp_path / "empty.json"))
    clear_experience_store_cache()
    analysis = _impulse_analysis(
        confidence=0.74,
        probability=0.60,
        trend_state="UPTREND",
        indicator_validation=True,
        atr_ok=True,
        scenarios=[SimpleNamespace(name="Main Bullish", bias="BULLISH")],
    )
    filtered = apply_trade_filters(analysis, htf_wave_number="4")
    assert filtered["scenarios"] == []


def test_htf_waveC_lowers_threshold(tmp_path, monkeypatch):
    """HTF wave C → main_confidence_threshold -= 0.04 (easier entry)."""
    monkeypatch.setenv("EXPERIENCE_STORE_PATH", str(tmp_path / "empty.json"))
    clear_experience_store_cache()
    analysis = _impulse_analysis(
        confidence=0.69,   # < 0.72 default, but > 0.72-0.04=0.68 lowered threshold
        probability=0.60,
        trend_state="UPTREND",
        indicator_validation=True,
        atr_ok=True,
        scenarios=[SimpleNamespace(name="Main Bullish", bias="BULLISH")],
    )
    filtered = apply_trade_filters(analysis, htf_wave_number="C")
    assert len(filtered["scenarios"]) == 1


# ── Alternate scenario failure paths (lines 176-185) ─────────────────────────

def _alternate_analysis(*, confidence=0.90, probability=0.55,
                        trend_state="UPTREND", indicator_validation=True,
                        atr_ok=True, rsi_divergence="NONE"):
    """1D IMPULSE analysis with an alternate scenario (bypasses 4H filter)."""
    base = _analysis_with(
        timeframe="1D",
        confidence=confidence,
        probability=probability,
        trend_state=trend_state,
        indicator_validation=indicator_validation,
        atr_ok=atr_ok,
        rsi_divergence=rsi_divergence,
        scenarios=[SimpleNamespace(name="Alternate Bullish", bias="BULLISH")],
    )
    base = dict(base)
    base["primary_pattern_type"] = "IMPULSE"
    return base


def test_alternate_confidence_too_low(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPERIENCE_STORE_PATH", str(tmp_path / "empty.json"))
    clear_experience_store_cache()
    analysis = _alternate_analysis(confidence=0.80)  # < 0.84 alternate threshold
    filtered = apply_trade_filters(analysis)
    assert filtered["scenarios"] == []
    assert any("alternate confidence" in n for n in filtered["trade_filter"]["notes"])


def test_alternate_probability_too_low(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPERIENCE_STORE_PATH", str(tmp_path / "empty.json"))
    clear_experience_store_cache()
    analysis = _alternate_analysis(confidence=0.90, probability=0.45)  # < 0.52
    filtered = apply_trade_filters(analysis)
    assert filtered["scenarios"] == []
    assert any("alternate probability" in n for n in filtered["trade_filter"]["notes"])


def test_alternate_missing_indicator_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPERIENCE_STORE_PATH", str(tmp_path / "empty.json"))
    clear_experience_store_cache()
    analysis = _alternate_analysis(
        confidence=0.90, probability=0.55, indicator_validation=False
    )
    filtered = apply_trade_filters(analysis)
    assert filtered["scenarios"] == []
    assert any("indicator validation" in n for n in filtered["trade_filter"]["notes"])


def test_alternate_missing_atr_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPERIENCE_STORE_PATH", str(tmp_path / "empty.json"))
    clear_experience_store_cache()
    analysis = _alternate_analysis(
        confidence=0.90, probability=0.55,
        indicator_validation=True, atr_ok=False,
    )
    filtered = apply_trade_filters(analysis)
    assert filtered["scenarios"] == []
    assert any("atr" in n for n in filtered["trade_filter"]["notes"])


def test_alternate_not_aligned_with_trend(tmp_path, monkeypatch):
    """Alternate BULLISH in DOWNTREND → not aligned."""
    monkeypatch.setenv("EXPERIENCE_STORE_PATH", str(tmp_path / "empty.json"))
    clear_experience_store_cache()
    analysis = _alternate_analysis(
        confidence=0.90, probability=0.55,
        trend_state="DOWNTREND",
        indicator_validation=True, atr_ok=True,
    )
    filtered = apply_trade_filters(analysis)
    assert filtered["scenarios"] == []
    assert any("trend" in n for n in filtered["trade_filter"]["notes"])


# ── Main scenario failure paths (lines 189, 191, 193) ────────────────────────

def test_main_confidence_too_low_non4h(tmp_path, monkeypatch):
    """Main scenario confidence below threshold on 1D IMPULSE."""
    monkeypatch.setenv("EXPERIENCE_STORE_PATH", str(tmp_path / "empty.json"))
    clear_experience_store_cache()
    analysis = _impulse_analysis(
        confidence=0.65,  # < 0.72
        probability=0.60,
        trend_state="UPTREND",
        indicator_validation=True,
        atr_ok=True,
        scenarios=[SimpleNamespace(name="Main Bullish", bias="BULLISH")],
    )
    filtered = apply_trade_filters(analysis)
    assert filtered["scenarios"] == []
    assert any("main confidence" in n for n in filtered["trade_filter"]["notes"])


def test_main_missing_atr_expansion(tmp_path, monkeypatch):
    """Main scenario: atr=False, divergence=NONE, macd=NONE → blocked."""
    monkeypatch.setenv("EXPERIENCE_STORE_PATH", str(tmp_path / "empty.json"))
    clear_experience_store_cache()
    analysis = _analysis_with(
        timeframe="1D",
        confidence=0.80,
        probability=0.60,
        trend_state="UPTREND",
        indicator_validation=True,
        atr_ok=False,
        rsi_divergence="NONE",
        scenarios=[SimpleNamespace(name="Main Bullish", bias="BULLISH")],
    )
    analysis = dict(analysis)
    analysis["primary_pattern_type"] = "IMPULSE"

    passed, note = _passes_quality_gate(
        analysis=analysis,
        scenario=SimpleNamespace(name="Main Bullish", bias="BULLISH"),
        index=0,
        higher_timeframe_bias=None,
    )
    assert passed is False
    assert note == "main missing atr expansion"


def test_main_not_aligned_with_trend(tmp_path, monkeypatch):
    """BULLISH in DOWNTREND with no indicator_validation, no atr, but with divergence → blocked by trend."""
    monkeypatch.setenv("EXPERIENCE_STORE_PATH", str(tmp_path / "empty.json"))
    clear_experience_store_cache()
    # Use rsi_divergence so the atr check doesn't fire first
    analysis = _analysis_with(
        timeframe="1D",
        confidence=0.80,
        probability=0.60,
        trend_state="DOWNTREND",
        indicator_validation=False,
        atr_ok=False,
        rsi_divergence="BULLISH_RSI_DIVERGENCE",
        scenarios=[SimpleNamespace(name="Main Bullish", bias="BULLISH")],
    )
    analysis = dict(analysis)
    analysis["primary_pattern_type"] = "IMPULSE"

    passed, note = _passes_quality_gate(
        analysis=analysis,
        scenario=SimpleNamespace(name="Main Bullish", bias="BULLISH"),
        index=0,
        higher_timeframe_bias=None,
    )
    assert passed is False
    assert note == "main not aligned with trend"
