import pytest

from analysis.risk_reward import calculate_rr, calculate_rr_levels


def test_calculate_rr_supports_bullish_bearish_aliases():
    assert calculate_rr("BULLISH", 100.0, 95.0, 110.0) == 2.0
    assert calculate_rr("BEARISH", 100.0, 105.0, 90.0) == 2.0


def test_calculate_rr_levels_returns_expected_values():
    levels = calculate_rr_levels(
        side="SHORT",
        entry_price=63030.0,
        stop_loss=74050.0,
        tp1=52010.0,
        tp2=49012.56,
        tp3=45199.64,
    )

    assert levels == {
        "rr_tp1": 1.0,
        "rr_tp2": 1.272,
        "rr_tp3": 1.618,
    }


# ── None argument returns None (line 11) ─────────────────────────────────────

def test_calculate_rr_none_side():
    assert calculate_rr(None, 100.0, 90.0, 110.0) is None


def test_calculate_rr_none_entry():
    assert calculate_rr("LONG", None, 90.0, 110.0) is None


def test_calculate_rr_none_stop():
    assert calculate_rr("LONG", 100.0, None, 110.0) is None


def test_calculate_rr_none_target():
    assert calculate_rr("LONG", 100.0, 90.0, None) is None


# ── Unknown side returns None (line 29) ──────────────────────────────────────

def test_calculate_rr_unknown_side():
    assert calculate_rr("UNKNOWN", 100.0, 90.0, 110.0) is None


# ── Non-positive risk or reward returns None (line 32) ───────────────────────

def test_calculate_rr_zero_risk_long():
    # entry == stop → risk=0 → None
    assert calculate_rr("LONG", 100.0, 100.0, 110.0) is None


def test_calculate_rr_negative_reward_long():
    # target < entry for LONG → reward < 0 → None
    assert calculate_rr("LONG", 100.0, 90.0, 95.0) is None


def test_calculate_rr_zero_risk_short():
    assert calculate_rr("SHORT", 100.0, 100.0, 90.0) is None


def test_calculate_rr_negative_reward_short():
    assert calculate_rr("SHORT", 100.0, 110.0, 105.0) is None
