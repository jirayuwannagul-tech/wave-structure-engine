from datetime import datetime
from zoneinfo import ZoneInfo

from scheduler.daily_scheduler import maybe_run_daily_job, run_daily_job


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
