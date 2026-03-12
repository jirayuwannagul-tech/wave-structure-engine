from datetime import datetime
from zoneinfo import ZoneInfo

from scheduler.daily_scheduler import run_daily_job


def test_run_daily_job_calls_notification(monkeypatch):
    calls = {"message": None}
    now = datetime(2026, 3, 12, 7, 5, tzinfo=ZoneInfo("Asia/Bangkok"))

    monkeypatch.setattr(
        "scheduler.daily_scheduler.run_multi_timeframe",
        lambda symbol: "TEST REPORT"
    )

    def fake_send_notification(message: str, **kwargs):
        calls["message"] = message
        calls["kwargs"] = kwargs

    monkeypatch.setattr(
        "scheduler.daily_scheduler.send_notification",
        fake_send_notification,
    )

    run_daily_job(now=now)

    assert calls["message"] == "BTCUSDT Daily Close Summary\nDate: 2026-03-12\n\nTEST REPORT"
    assert calls["kwargs"] == {"topic_key": "daily_summary"}
