from datetime import datetime
from zoneinfo import ZoneInfo

from scheduler.daily_scheduler import is_daily_run_time


THAI_TZ = ZoneInfo("Asia/Bangkok")


def test_is_daily_run_time_true_at_0705():
    now = datetime(2026, 3, 11, 7, 5, tzinfo=THAI_TZ)
    assert is_daily_run_time(now) is True


def test_is_daily_run_time_false_before_0705():
    now = datetime(2026, 3, 11, 7, 4, tzinfo=THAI_TZ)
    assert is_daily_run_time(now) is False


def test_is_daily_run_time_false_after_0705():
    now = datetime(2026, 3, 11, 7, 6, tzinfo=THAI_TZ)
    assert is_daily_run_time(now) is False