import pandas as pd

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
    assert snapshot["rr_tp1"] == 2.0
    assert snapshot["rr_tp2"] == 4.0
    assert snapshot["rr_tp3"] == 6.0


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
    assert row["stop_loss"] == 100.5
    assert row["tp1_hit_at"] is not None
    assert row["close_reason"] == "STOP_LOSS"

    event_types = [event["event_type"] for event in repo.fetch_signal_events(signal_id)]
    assert event_types == ["SIGNAL_CREATED", "ENTRY_TRIGGERED", "TP1_HIT", "STOP_MOVED", "STOP_LOSS_HIT"]


def test_repository_time_stop_closes_stalled_trade(tmp_path):
    repo = WaveRepository(db_path=str(tmp_path / "wave.db"))
    signal_id = repo.sync_analysis(_analysis(timeframe="4H", entry=100.0, stop_loss=95.0))

    assert signal_id is not None

    repo.track_price_update("BTCUSDT", 100.2, event_time="2026-03-17T00:00:00+00:00")
    events = repo.track_price_update("BTCUSDT", 100.4, event_time="2026-03-18T00:00:00+00:00")

    assert (signal_id, "TIME_STOP_HIT") in events

    with repo._connect() as conn:
        row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()

    assert row["status"] == "STOPPED"
    assert row["close_reason"] == "TIME_STOP"


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


def test_sync_runtime_returns_replaced_and_new_signal_ids(tmp_path):
    repo = WaveRepository(db_path=str(tmp_path / "wave.db"))

    class Runtime:
        analyses = [_analysis(entry=100.0, stop_loss=95.0)]

    first_ids = repo.sync_runtime(Runtime(), current_price=99.0)
    Runtime.analyses = [_analysis(entry=101.0, stop_loss=96.0)]
    second_ids = repo.sync_runtime(Runtime(), current_price=99.0)

    assert len(first_ids) == 1
    assert len(second_ids) == 2

    with repo._connect() as conn:
        first = conn.execute("SELECT * FROM signals WHERE id = ?", (first_ids[0],)).fetchone()
        second = conn.execute("SELECT * FROM signals WHERE id = ?", (second_ids[-1],)).fetchone()

    assert first["status"] == "REPLACED"
    assert second["status"] == "PENDING_ENTRY"


def test_repository_tracks_system_events_once(tmp_path):
    repo = WaveRepository(db_path=str(tmp_path / "wave.db"))

    assert repo.has_system_event("DAILY_SUMMARY:2026-03-13") is False
    assert repo.record_system_event("DAILY_SUMMARY:2026-03-13", details={"price": 70000.0}) is not None
    assert repo.has_system_event("DAILY_SUMMARY:2026-03-13") is True
    assert repo.record_system_event("DAILY_SUMMARY:2026-03-13", details={"price": 70010.0}) is None


def test_sync_analysis_backfills_rr_for_existing_signal(tmp_path):
    repo = WaveRepository(db_path=str(tmp_path / "wave.db"))
    signal_id = repo.sync_analysis(_analysis())

    with repo._connect() as conn:
        conn.execute(
            "UPDATE signals SET rr_tp1 = NULL, rr_tp2 = NULL, rr_tp3 = NULL WHERE id = ?",
            (signal_id,),
        )

    same_signal_id = repo.sync_analysis(_analysis())

    assert same_signal_id == signal_id

    with repo._connect() as conn:
        row = conn.execute("SELECT rr_tp1, rr_tp2, rr_tp3 FROM signals WHERE id = ?", (signal_id,)).fetchone()

    assert row["rr_tp1"] == 2.0
    assert row["rr_tp2"] == 4.0
    assert row["rr_tp3"] == 6.0


def test_repository_upserts_market_candles(tmp_path):
    repo = WaveRepository(db_path=str(tmp_path / "wave.db"))
    df = pd.DataFrame(
        {
            "open_time": pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"], utc=True),
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [10.0, 11.0],
            "close_time": pd.to_datetime(["2026-01-01T23:59:59Z", "2026-01-02T23:59:59Z"], utc=True),
            "quote_asset_volume": [20.0, 21.0],
            "number_of_trades": [5, 6],
        }
    )

    inserted = repo.upsert_market_candles("BTCUSDT", "1D", df)
    assert inserted == 2
    assert repo.count_market_candles("BTCUSDT", "1D") == 2

    updated = df.copy()
    updated.loc[1, "close"] = 202.0
    upserted = repo.upsert_market_candles("BTCUSDT", "1D", updated.iloc[1:])
    assert upserted == 1

    with repo._connect() as conn:
        row = conn.execute(
            "SELECT close FROM market_candles WHERE symbol = ? AND timeframe = ? AND open_time = ?",
            ("BTCUSDT", "1D", "2026-01-02T00:00:00+00:00"),
        ).fetchone()

    assert row["close"] == 202.0
