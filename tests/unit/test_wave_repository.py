from scenarios.scenario_engine import Scenario
from storage.wave_repository import WaveRepository, build_signal_snapshot


class PositionStub:
    structure = "ABC_CORRECTION"
    position = "WAVE_C_END"
    bias = "BULLISH"


def _analysis(
    timeframe: str = "4H",
    pattern_type: str = "ABC_CORRECTION",
    bias: str = "BULLISH",
    entry: float = 100.0,
    stop_loss: float = 95.0,
    targets: list[float] | None = None,
):
    return {
        "symbol": "BTCUSDT",
        "timeframe": timeframe,
        "primary_pattern_type": pattern_type,
        "current_price": 99.0,
        "position": PositionStub(),
        "scenarios": [
            Scenario(
                name="Main Bullish" if bias == "BULLISH" else "Main Bearish",
                condition="test",
                interpretation="test",
                target="test",
                bias=bias,
                invalidation=stop_loss,
                confirmation=entry,
                stop_loss=stop_loss,
                targets=targets or [110.0, 120.0, 130.0],
            )
        ],
    }


def test_build_signal_snapshot_returns_tradeable_signal():
    snapshot = build_signal_snapshot(_analysis())

    assert snapshot is not None
    assert snapshot["symbol"] == "BTCUSDT"
    assert snapshot["timeframe"] == "4H"
    assert snapshot["side"] == "LONG"
    assert snapshot["entry_price"] == 100.0
    assert snapshot["tp3"] == 130.0


def test_repository_tracks_tp1_then_stop_loss(tmp_path):
    repo = WaveRepository(db_path=str(tmp_path / "wave.db"))
    signal_id = repo.sync_analysis(_analysis())

    assert signal_id is not None

    events = repo.track_price_update("BTCUSDT", 100.5)
    assert (signal_id, "ENTRY_TRIGGERED") in events

    events = repo.track_price_update("BTCUSDT", 111.0)
    assert (signal_id, "TP1_HIT") in events

    events = repo.track_price_update("BTCUSDT", 94.0)
    assert (signal_id, "STOP_LOSS_HIT") in events

    with repo._connect() as conn:
        row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
    assert row["status"] == "STOPPED"
    assert row["tp1_hit_at"] is not None
    assert row["close_reason"] == "STOP_LOSS"

    event_types = [event["event_type"] for event in repo.fetch_signal_events(signal_id)]
    assert event_types == ["SIGNAL_CREATED", "ENTRY_TRIGGERED", "TP1_HIT", "STOP_LOSS_HIT"]


def test_repository_replaces_pending_signal_on_same_timeframe(tmp_path):
    repo = WaveRepository(db_path=str(tmp_path / "wave.db"))
    first_id = repo.sync_analysis(_analysis(entry=100.0, stop_loss=95.0))
    second_id = repo.sync_analysis(_analysis(entry=101.0, stop_loss=96.0))

    assert first_id is not None
    assert second_id is not None
    assert first_id != second_id

    with repo._connect() as conn:
        first = conn.execute("SELECT * FROM signals WHERE id = ?", (first_id,)).fetchone()
        second = conn.execute("SELECT * FROM signals WHERE id = ?", (second_id,)).fetchone()

    assert first["status"] == "REPLACED"
    assert first["close_reason"] == "REPLACED_BY_NEW_SIGNAL"
    assert second["status"] == "PENDING_ENTRY"
