import os

import pandas as pd
import pytest

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
    current_price: float = 99.0,
):
    return {
        "symbol": "BTCUSDT",
        "timeframe": timeframe,
        "primary_pattern_type": pattern_type,
        "current_price": current_price,
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


def test_build_signal_snapshot_prefers_execution_scenarios_when_present():
    analysis = _analysis()
    analysis["execution_scenarios"] = [
        Scenario(
            name="Exec Bearish",
            condition="test",
            interpretation="test",
            target="test",
            bias="BEARISH",
            invalidation=105.0,
            confirmation=98.0,
            stop_loss=105.0,
            targets=[92.0, 88.0, 84.0],
        )
    ]

    snapshot = build_signal_snapshot(analysis)

    assert snapshot is not None
    assert snapshot["scenario_name"] == "Exec Bearish"
    assert snapshot["side"] == "SHORT"
    assert snapshot["entry_price"] == 98.0


def test_build_signal_snapshot_skips_overextended_market_scenario(monkeypatch):
    monkeypatch.delenv("BINANCE_EXECUTION_ENABLED", raising=False)
    monkeypatch.delenv("BINANCE_LIVE_ORDER_ENABLED", raising=False)
    monkeypatch.setenv("BINANCE_ENTRY_STYLE", "market")

    snapshot = build_signal_snapshot(
        _analysis(entry=100.0, stop_loss=95.0, current_price=109.0)
    )

    assert snapshot is None


def test_build_signal_snapshot_skips_already_crossed_signal_price_scenario(monkeypatch):
    monkeypatch.setenv("BINANCE_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("BINANCE_LIVE_ORDER_ENABLED", "true")
    monkeypatch.setenv("BINANCE_ENTRY_STYLE", "signal_price")

    snapshot = build_signal_snapshot(
        _analysis(entry=100.0, stop_loss=95.0, current_price=101.0)
    )

    assert snapshot is None


def test_build_signal_snapshot_uses_next_actionable_execution_scenario(monkeypatch):
    monkeypatch.setenv("BINANCE_ENTRY_STYLE", "market")
    analysis = _analysis(current_price=100.5)
    analysis["execution_scenarios"] = [
        Scenario(
            name="Stale Bullish",
            condition="test",
            interpretation="test",
            target="test",
            bias="BULLISH",
            invalidation=95.0,
            confirmation=90.0,
            stop_loss=88.0,
            targets=[95.0, 98.0, 101.0],
        ),
        Scenario(
            name="Fresh Bearish",
            condition="test",
            interpretation="test",
            target="test",
            bias="BEARISH",
            invalidation=106.0,
            confirmation=100.4,
            stop_loss=106.0,
            targets=[99.0, 98.0, 97.0],
        ),
    ]

    snapshot = build_signal_snapshot(analysis)

    assert snapshot is not None
    assert snapshot["scenario_name"] == "Fresh Bearish"
    assert snapshot["side"] == "SHORT"


def test_repository_tracks_tp1_then_stop_loss(tmp_path):
    repo = WaveRepository(db_path=str(tmp_path / "wave.db"))
    # Entry-only mode (default): persist only after entry is crossed.
    signal_id = repo.sync_analysis(_analysis(), current_price=100.5)

    assert signal_id is not None

    events = repo.track_price_update("BTCUSDT", 111.0)
    assert (signal_id, "TP1_HIT") in events

    events = repo.track_price_update("BTCUSDT", 94.0)
    assert (signal_id, "STOP_LOSS_HIT") in events

    with repo._connect() as conn:
        row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
    assert row["status"] == "STOPPED"
    assert row["stop_loss"] == 95.0
    assert row["managed_stop_loss"] == 100.5
    assert row["tp1_hit_at"] is not None
    assert row["close_reason"] == "STOP_LOSS"

    event_types = [event["event_type"] for event in repo.fetch_signal_events(signal_id)]
    assert event_types == ["ENTRY_TRIGGERED", "SIGNAL_CREATED", "TP1_HIT", "STOP_MOVED", "STOP_LOSS_HIT"]


def test_repository_closes_active_trade_on_opposite_structure(tmp_path):
    repo = WaveRepository(db_path=str(tmp_path / "wave.db"))
    signal_id = repo.sync_analysis(_analysis(entry=100.0, stop_loss=95.0), current_price=100.5)
    events = repo.track_price_update(
        "BTCUSDT",
        98.5,
        analyses=[
            {
                "timeframe": "4H",
                "execution_scenarios": [
                    Scenario(
                        name="Opposite Bearish",
                        condition="test",
                        interpretation="test",
                        target="test",
                        bias="BEARISH",
                        invalidation=104.0,
                        confirmation=99.0,
                        stop_loss=104.0,
                        targets=[94.0],
                    )
                ],
            }
        ],
    )

    assert (signal_id, "OPPOSITE_STRUCTURE_HIT") in events

    with repo._connect() as conn:
        row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()

    assert row["status"] == "STOPPED"
    assert row["close_reason"] == "OPPOSITE_STRUCTURE"


def test_repository_closes_active_trade_on_volatility_exit(tmp_path):
    repo = WaveRepository(db_path=str(tmp_path / "wave.db"))
    signal_id = repo.sync_analysis(_analysis(entry=100.0, stop_loss=95.0), current_price=100.5)

    df = pd.DataFrame(
        {
            "open_time": pd.to_datetime(
                [
                    "2026-03-17T00:00:00Z",
                    "2026-03-17T04:00:00Z",
                    "2026-03-17T08:00:00Z",
                    "2026-03-17T12:00:00Z",
                    "2026-03-17T16:00:00Z",
                    "2026-03-17T20:00:00Z",
                ],
                utc=True,
            ),
            "open": [100.0, 100.5, 100.2, 100.1, 100.4, 100.0],
            "high": [101.0, 101.2, 101.1, 101.0, 101.3, 110.0],
            "low": [99.4, 99.7, 99.6, 99.7, 99.9, 90.0],
            "close": [100.6, 100.3, 100.4, 100.5, 100.2, 99.0],
            "volume": [1, 1, 1, 1, 1, 1],
            "close_time": pd.to_datetime(
                [
                    "2026-03-17T03:59:59Z",
                    "2026-03-17T07:59:59Z",
                    "2026-03-17T11:59:59Z",
                    "2026-03-17T15:59:59Z",
                    "2026-03-17T19:59:59Z",
                    "2026-03-17T23:59:59Z",
                ],
                utc=True,
            ),
            "quote_asset_volume": [1, 1, 1, 1, 1, 1],
            "number_of_trades": [1, 1, 1, 1, 1, 1],
        }
    )
    repo.upsert_market_candles("BTCUSDT", "4H", df)

    events = repo.track_price_update("BTCUSDT", 99.0)
    assert (signal_id, "VOLATILITY_EXIT_HIT") in events

    with repo._connect() as conn:
        row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()

    assert row["status"] == "STOPPED"
    assert row["close_reason"] == "VOLATILITY_EXIT"


def test_repository_time_stop_closes_stalled_trade(tmp_path):
    # Time-stop logic relies on the entry_triggered_at timestamp written at trigger time.
    # Use legacy flow for deterministic timestamps in this unit test.
    monkeypatch_env = os.environ.get("SIGNALS_ENTRY_ONLY")
    os.environ["SIGNALS_ENTRY_ONLY"] = "false"
    repo = WaveRepository(db_path=str(tmp_path / "wave.db"))
    signal_id = repo.sync_analysis(_analysis(timeframe="4H", entry=100.0, stop_loss=95.0), current_price=100.2)

    assert signal_id is not None

    repo.track_price_update("BTCUSDT", 100.2, event_time="2026-03-17T00:00:00+00:00")
    events = repo.track_price_update("BTCUSDT", 100.4, event_time="2026-03-18T00:00:00+00:00")

    assert (signal_id, "TIME_STOP_HIT") in events

    with repo._connect() as conn:
        row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()

    assert row["status"] == "STOPPED"
    assert row["close_reason"] == "TIME_STOP"
    if monkeypatch_env is None:
        del os.environ["SIGNALS_ENTRY_ONLY"]
    else:
        os.environ["SIGNALS_ENTRY_ONLY"] = monkeypatch_env


def test_signal_gate_blocks_second_plan_until_terminal_exit(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNAL_GATE_TERMINAL_EXIT", "true")
    repo = WaveRepository(db_path=str(tmp_path / "wave.db"))
    first_id = repo.sync_analysis(_analysis(entry=100.0, stop_loss=95.0), current_price=100.5)
    second_id = repo.sync_analysis(_analysis(entry=101.0, stop_loss=96.0))

    assert first_id is not None
    assert second_id is None

    with repo._connect() as conn:
        row = conn.execute("SELECT * FROM signals WHERE id = ?", (first_id,)).fetchone()
    assert row["status"] == "ACTIVE"

    repo.track_price_update("BTCUSDT", 130.0)
    third_id = repo.sync_analysis(_analysis(entry=102.0, stop_loss=97.0), current_price=102.5)
    assert third_id is not None
    with repo._connect() as conn:
        new_row = conn.execute("SELECT * FROM signals WHERE id = ?", (third_id,)).fetchone()
    assert new_row["status"] in {"ACTIVE", "PENDING_ENTRY"}


def test_signal_gate_blocks_other_timeframe_by_default_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNAL_GATE_TERMINAL_EXIT", "true")
    repo = WaveRepository(db_path=str(tmp_path / "wave.db"))
    id_4h = repo.sync_analysis(_analysis(timeframe="4H", entry=100.0, stop_loss=95.0), current_price=100.5)
    id_1d = repo.sync_analysis(_analysis(timeframe="1D", entry=200.0, stop_loss=190.0), current_price=200.5)
    assert id_4h is not None
    assert id_1d is None


def test_exchange_managed_signal_entry_stays_pending_until_exchange_fill(tmp_path, monkeypatch):
    monkeypatch.setenv("BINANCE_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("BINANCE_LIVE_ORDER_ENABLED", "true")
    monkeypatch.setenv("BINANCE_ENTRY_STYLE", "signal_price")
    repo = WaveRepository(db_path=str(tmp_path / "wave.db"))

    signal_id = repo.sync_analysis(_analysis(entry=100.0, stop_loss=95.0), current_price=99.0)

    assert signal_id is not None
    with repo._connect() as conn:
        row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
    assert row["status"] == "PENDING_ENTRY"
    assert row["entry_triggered_at"] is None

    events = repo.track_price_update("BTCUSDT", 100.5)
    assert events == []
    with repo._connect() as conn:
        row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
    assert row["status"] == "PENDING_ENTRY"

    assert repo.mark_signal_entry_filled_from_exchange(signal_id, 100.2) is True
    with repo._connect() as conn:
        row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
    assert row["status"] == "ACTIVE"
    assert row["entry_price"] == 100.0
    assert row["entry_triggered_price"] == 100.2
    assert row["entry_triggered_at"] is not None

    event_types = [event["event_type"] for event in repo.fetch_signal_events(signal_id)]
    assert event_types == ["SIGNAL_CREATED", "ENTRY_TRIGGERED"]


def test_repository_replaces_pending_signal_on_same_timeframe(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNALS_ENTRY_ONLY", "false")
    monkeypatch.setenv("SIGNAL_GATE_TERMINAL_EXIT", "false")
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


def test_sync_runtime_returns_replaced_and_new_signal_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNALS_ENTRY_ONLY", "false")
    monkeypatch.setenv("SIGNAL_GATE_TERMINAL_EXIT", "false")
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
    monkeypatch_env = os.environ.get("SIGNALS_ENTRY_ONLY")
    os.environ["SIGNALS_ENTRY_ONLY"] = "false"
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
    if monkeypatch_env is None:
        del os.environ["SIGNALS_ENTRY_ONLY"]
    else:
        os.environ["SIGNALS_ENTRY_ONLY"] = monkeypatch_env


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


def test_update_signal_entry_to_exchange_average(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNALS_ENTRY_ONLY", "0")
    db = str(tmp_path / "w.db")
    repo = WaveRepository(db_path=db)
    sid = repo.sync_analysis(
        _analysis(entry=100.0, stop_loss=95.0, targets=[110.0, 120.0, 130.0]),
    )
    assert sid is not None
    assert repo.update_signal_entry_to_exchange_average(int(sid), 101.25) is True
    row = repo.fetch_signal(int(sid))
    assert float(row["entry_price"]) == pytest.approx(100.0)
    assert float(row["entry_triggered_price"]) == pytest.approx(101.25)
    assert row["rr_tp1"] is not None
