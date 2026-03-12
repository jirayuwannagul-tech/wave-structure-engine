from __future__ import annotations

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from core.engine import run_multi_timeframe
from services.notifier import send_notification

THAI_TZ = ZoneInfo("Asia/Bangkok")


def is_daily_run_time(now: datetime | None = None) -> bool:
    if now is None:
        now = datetime.now(THAI_TZ)

    if now.tzinfo is None:
        now = now.replace(tzinfo=THAI_TZ)

    return now.hour == 7 and now.minute == 5


def build_daily_summary_message(report: str, now: datetime | None = None) -> str:
    if now is None:
        now = datetime.now(THAI_TZ)

    if now.tzinfo is None:
        now = now.replace(tzinfo=THAI_TZ)
    else:
        now = now.astimezone(THAI_TZ)

    return (
        "BTCUSDT Daily Close Summary\n"
        f"Date: {now.strftime('%Y-%m-%d')}\n\n"
        f"{report}"
    )


def run_daily_job(now: datetime | None = None) -> None:
    report = run_multi_timeframe("BTCUSDT")
    send_notification(
        build_daily_summary_message(report, now=now),
        topic_key="daily_summary",
    )


if __name__ == "__main__":
    force_run = "--force" in sys.argv

    now = datetime.now(THAI_TZ)

    print("now =", now.strftime("%Y-%m-%d %H:%M:%S %Z"))
    print("is_daily_run_time =", is_daily_run_time(now))
    print("force_run =", force_run)

    if is_daily_run_time(now) or force_run:
        run_daily_job()
    else:
        print("skip: not daily run time")
