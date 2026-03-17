from datetime import datetime
from zoneinfo import ZoneInfo

from scheduler.daily_scheduler import (
    build_combined_daily_summary_message,
    maybe_run_combined_daily_job,
    maybe_run_daily_job,
    run_combined_daily_job,
    run_daily_job,
)


THAI_TZ = ZoneInfo("Asia/Bangkok")


def test_run_daily_job_calls_notification(monkeypatch):
    calls = {"message": None}
    now = datetime(2026, 3, 12, 7, 5, tzinfo=THAI_TZ)
    runtime = object()

    monkeypatch.setattr(
        "services.trading_orchestrator.render_runtime_snapshot",
        lambda runtime, current_price=None: "TEST REPORT",
    )

    def fake_send_notification(message: str, **kwargs):
        calls["message"] = message
        calls["kwargs"] = kwargs

    monkeypatch.setattr(
        "scheduler.daily_scheduler.send_notification",
        fake_send_notification,
    )

    run_daily_job(symbol="BTCUSDT", now=now, runtime=runtime, current_price=70123.4)

    assert calls["message"] == "BTCUSDT | Daily Summary\n📅 2026-03-12\n\nTEST REPORT"
    assert calls["kwargs"] == {"topic_key": "daily_summary", "symbol": "BTCUSDT"}


def test_maybe_run_daily_job_runs_once_per_day(monkeypatch, tmp_path):
    calls = []
    repo_path = tmp_path / "wave.db"

    from storage.wave_repository import WaveRepository

    repository = WaveRepository(db_path=str(repo_path))
    runtime = object()
    now = datetime(2026, 3, 12, 7, 5, tzinfo=THAI_TZ)

    monkeypatch.setattr(
        "scheduler.daily_scheduler.run_daily_job",
        lambda **kwargs: calls.append(kwargs),
    )

    assert maybe_run_daily_job(repository, runtime, current_price=70000.0, now=now) is True
    assert maybe_run_daily_job(repository, runtime, current_price=70010.0, now=now) is False
    assert len(calls) == 1
    assert calls[0]["runtime"] is None


def test_maybe_run_daily_job_runs_once_per_day_per_symbol(monkeypatch, tmp_path):
    calls = []
    repo_path = tmp_path / "wave.db"

    from storage.wave_repository import WaveRepository

    class Runtime:
        def __init__(self, symbol: str):
            self.symbol = symbol

    repository = WaveRepository(db_path=str(repo_path))
    now = datetime(2026, 3, 12, 7, 5, tzinfo=THAI_TZ)

    monkeypatch.setattr(
        "scheduler.daily_scheduler.run_daily_job",
        lambda **kwargs: calls.append(kwargs),
    )

    assert maybe_run_daily_job(repository, Runtime("BTCUSDT"), current_price=70000.0, now=now) is True
    assert maybe_run_daily_job(repository, Runtime("ETHUSDT"), current_price=3500.0, now=now) is True
    assert len(calls) == 2


def test_build_combined_daily_summary_message_lists_long_and_short_watch_prices():
    class Scenario:
        def __init__(self, bias, confirmation, stop_loss, targets):
            self.bias = bias
            self.confirmation = confirmation
            self.stop_loss = stop_loss
            self.targets = targets

    class Runtime:
        def __init__(self, symbol: str):
            self.symbol = symbol
            self.analyses = [
                {
                    "timeframe": "1D",
                    "scenarios": [
                        Scenario("BULLISH", 101.0, 95.0, [110.0]),
                        Scenario("BEARISH", 89.0, 94.0, [80.0]),
                    ],
                }
            ]

    now = datetime(2026, 3, 12, 7, 5, tzinfo=THAI_TZ)

    message = build_combined_daily_summary_message([Runtime("BTCUSDT"), Runtime("ETHUSDT")], now=now)

    assert message == (
        "Daily Watchlist\n"
        "📅 2026-03-12\n\n"
        "BTCUSDT | L 101 | S 89\n"
        "ETHUSDT | L 101 | S 89"
    )


def test_run_combined_daily_job_sends_single_message(monkeypatch):
    class Runtime:
        def __init__(self, symbol: str):
            self.symbol = symbol
            self.analyses = []

    calls = {}
    now = datetime(2026, 3, 12, 7, 5, tzinfo=THAI_TZ)

    monkeypatch.setattr(
        "scheduler.daily_scheduler.send_notification",
        lambda message, **kwargs: calls.update({"message": message, "kwargs": kwargs}),
    )

    run_combined_daily_job(
        runtimes=[Runtime("BTCUSDT"), Runtime("ETHUSDT")],
        current_prices={},
        now=now,
    )

    assert calls["message"] == (
        "Daily Watchlist\n"
        "📅 2026-03-12\n\n"
        "BTCUSDT | L - | S -\n"
        "ETHUSDT | L - | S -"
    )
    assert calls["kwargs"] == {"topic_key": "daily_summary", "include_layout": False}


def test_maybe_run_combined_daily_job_runs_once_per_day(monkeypatch, tmp_path):
    calls = []
    repo_path = tmp_path / "wave.db"

    from storage.wave_repository import WaveRepository

    class Runtime:
        def __init__(self, symbol: str):
            self.symbol = symbol
            self.analyses = []

    repository = WaveRepository(db_path=str(repo_path))
    now = datetime(2026, 3, 12, 7, 5, tzinfo=THAI_TZ)

    monkeypatch.setattr(
        "scheduler.daily_scheduler.run_combined_daily_job",
        lambda **kwargs: calls.append(kwargs),
    )

    runtimes = [Runtime("BTCUSDT"), Runtime("ETHUSDT")]

    assert maybe_run_combined_daily_job(
        repository,
        runtimes,
        current_prices={"BTCUSDT": 70000.0, "ETHUSDT": 3500.0},
        now=now,
    ) is True
    assert maybe_run_combined_daily_job(
        repository,
        runtimes,
        current_prices={"BTCUSDT": 70010.0, "ETHUSDT": 3510.0},
        now=now,
    ) is False
    assert len(calls) == 1
