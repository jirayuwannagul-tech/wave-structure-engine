from scheduler.daily_scheduler import run_daily_job


def test_run_daily_job_calls_notification(monkeypatch):
    calls = {"message": None}

    monkeypatch.setattr(
        "scheduler.daily_scheduler.run_multi_timeframe",
        lambda symbol: "TEST REPORT"
    )

    def fake_send_notification(message: str):
        calls["message"] = message

    monkeypatch.setattr(
        "scheduler.daily_scheduler.send_notification",
        fake_send_notification,
    )

    run_daily_job()

    assert calls["message"] == "TEST REPORT"