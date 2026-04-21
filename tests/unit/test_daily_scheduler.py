from datetime import datetime
from zoneinfo import ZoneInfo

from scheduler.daily_scheduler import in_daily_watch_window, is_daily_run_time


LOCAL_TZ = ZoneInfo("America/Los_Angeles")


def test_is_daily_run_time_true_at_0705():
    now = datetime(2026, 3, 11, 7, 5, tzinfo=LOCAL_TZ)
    assert is_daily_run_time(now) is True


def test_is_daily_run_time_false_before_0705():
    now = datetime(2026, 3, 11, 7, 4, tzinfo=LOCAL_TZ)
    assert is_daily_run_time(now) is False


def test_is_daily_run_time_false_after_0705():
    now = datetime(2026, 3, 11, 7, 6, tzinfo=LOCAL_TZ)
    assert is_daily_run_time(now) is False


def test_in_daily_watch_window_0705_to_0759():
    assert in_daily_watch_window(datetime(2026, 3, 11, 7, 5, tzinfo=LOCAL_TZ))
    assert in_daily_watch_window(datetime(2026, 3, 11, 7, 30, tzinfo=LOCAL_TZ))
    assert in_daily_watch_window(datetime(2026, 3, 11, 7, 59, tzinfo=LOCAL_TZ))
    assert not in_daily_watch_window(datetime(2026, 3, 11, 7, 4, tzinfo=LOCAL_TZ))
    assert not in_daily_watch_window(datetime(2026, 3, 11, 8, 0, tzinfo=LOCAL_TZ))