from __future__ import annotations

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

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
        "BTCUSDT | Daily Summary\n"
        f"📅 {now.strftime('%Y-%m-%d')}\n\n"
        f"{report}"
    )


def run_daily_job(
    now: datetime | None = None,
    runtime=None,
    current_price: float | None = None,
) -> None:
    from services.trading_orchestrator import _load_runtime, render_runtime_snapshot

    if runtime is None:
        runtime = _load_runtime("BTCUSDT")

    report = render_runtime_snapshot(runtime, current_price=current_price)
    send_notification(
        build_daily_summary_message(report, now=now),
        topic_key="daily_summary",
    )


def maybe_run_daily_job(
    repository,
    runtime,
    current_price: float | None = None,
    now: datetime | None = None,
) -> bool:
    if now is None:
        now = datetime.now(THAI_TZ)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=THAI_TZ)
    else:
        now = now.astimezone(THAI_TZ)

    if now.hour < 7 or (now.hour == 7 and now.minute < 5):
        return False

    event_key = f"DAILY_SUMMARY:{now.strftime('%Y-%m-%d')}"
    if repository.has_system_event(event_key):
        return False

    run_daily_job(now=now, runtime=runtime, current_price=current_price)
    repository.record_system_event(
        event_key,
        details={"current_price": current_price},
    )
    return True


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
