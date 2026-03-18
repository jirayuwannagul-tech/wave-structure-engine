from __future__ import annotations

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from services.notifier import send_notification
from analysis.wave_position import describe_current_leg

THAI_TZ = ZoneInfo("Asia/Bangkok")


def _now_bangkok(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(THAI_TZ)
    if now.tzinfo is None:
        return now.replace(tzinfo=THAI_TZ)
    return now.astimezone(THAI_TZ)


def in_daily_watch_window(now: datetime | None = None) -> bool:
    """
    Bangkok 07:05–07:59 — first orchestrator cycle in this window each day sends the reminder.
    Optional: DAILY_WATCH_START_HOUR (default 7), DAILY_WATCH_START_MINUTE (5),
    DAILY_WATCH_END_HOUR (default 7) — if end hour > start, extends window (e.g. catch-up until 08:30).
    """
    n = _now_bangkok(now)
    sh = int(os.getenv("DAILY_WATCH_START_HOUR", "7"))
    sm = int(os.getenv("DAILY_WATCH_START_MINUTE", "5"))
    eh = int(os.getenv("DAILY_WATCH_END_HOUR", "7"))
    em = int(os.getenv("DAILY_WATCH_END_MINUTE", "59"))
    t = n.hour * 60 + n.minute
    t0 = sh * 60 + sm
    t1 = eh * 60 + em
    return t0 <= t <= t1


def _fmt_value(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, (int, float)):
        rounded = round(float(value), 4)
        text = f"{rounded:.4f}".rstrip("0").rstrip(".")
        return text or "0"
    return str(value)


def _timeframe_rank(timeframe: str | None) -> int:
    value = (timeframe or "").upper()
    if value == "1D":
        return 0
    if value == "4H":
        return 1
    return 99


def _select_watch_price(runtime, bias: str, current_price: float | None = None) -> float | None:
    target_bias = (bias or "").upper()
    candidates: list[tuple[int, float, float]] = []

    for analysis in getattr(runtime, "analyses", []) or []:
        timeframe = analysis.get("timeframe")
        scenarios = analysis.get("scenarios") or []
        analysis_price = analysis.get("current_price")
        price_reference = current_price if current_price is not None else analysis_price
        analysis_candidates_before = len(candidates)

        for scenario in scenarios:
            scenario_bias = (getattr(scenario, "bias", None) or "").upper()
            confirmation = getattr(scenario, "confirmation", None)
            stop_loss = getattr(scenario, "stop_loss", None)
            targets = list(getattr(scenario, "targets", []) or [])

            if scenario_bias != target_bias or confirmation is None or stop_loss is None:
                continue

            entry = float(confirmation)
            stop = float(stop_loss)
            if target_bias == "BULLISH":
                if stop >= entry:
                    continue
                if targets and not any(float(target) > entry for target in targets):
                    continue
                if price_reference is not None and entry < float(price_reference):
                    continue
            elif target_bias == "BEARISH":
                if stop <= entry:
                    continue
                if targets and not any(float(target) < entry for target in targets):
                    continue
                if price_reference is not None and entry > float(price_reference):
                    continue
            else:
                continue

            distance = abs(float(price_reference) - entry) if price_reference is not None else float("inf")
            candidates.append((_timeframe_rank(timeframe), distance, entry))

        if len(candidates) > analysis_candidates_before:
            continue

        key_levels = analysis.get("key_levels")
        wave_summary = analysis.get("wave_summary") or {}
        fallback_level = None

        if target_bias == "BULLISH":
            resistance = getattr(key_levels, "resistance", None) if key_levels is not None else None
            support = getattr(key_levels, "support", None) if key_levels is not None else None
            if price_reference is not None and resistance is not None and float(resistance) >= float(price_reference):
                fallback_level = resistance
            else:
                fallback_level = resistance or wave_summary.get("confirm") or support
        elif target_bias == "BEARISH":
            support = getattr(key_levels, "support", None) if key_levels is not None else None
            resistance = getattr(key_levels, "resistance", None) if key_levels is not None else None
            if price_reference is not None and support is not None and float(support) <= float(price_reference):
                fallback_level = support
            else:
                fallback_level = support or wave_summary.get("confirm") or resistance

        if fallback_level is None:
            continue

        try:
            fallback_value = float(fallback_level)
        except (TypeError, ValueError):
            continue

        distance = abs(float(price_reference) - fallback_value) if price_reference is not None else float("inf")
        candidates.append((_timeframe_rank(timeframe), distance, fallback_value))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    return candidates[0][2]


def build_symbol_watch_message(runtime, current_price: float | None = None) -> str:
    symbol = getattr(runtime, "symbol", None) or "BTCUSDT"
    long_watch = _select_watch_price(runtime, "BULLISH", current_price=current_price)
    short_watch = _select_watch_price(runtime, "BEARISH", current_price=current_price)
    return f"{symbol} | L {_fmt_value(long_watch)} | S {_fmt_value(short_watch)}"


def build_combined_daily_summary_message(
    runtimes: list,
    current_prices: dict[str, float] | None = None,
    now: datetime | None = None,
) -> str:
    if now is None:
        now = datetime.now(THAI_TZ)

    if now.tzinfo is None:
        now = now.replace(tzinfo=THAI_TZ)
    else:
        now = now.astimezone(THAI_TZ)

    rows = []
    for runtime in runtimes:
        symbol = getattr(runtime, "symbol", None) or "BTCUSDT"
        price = (current_prices or {}).get(symbol)
        rows.append(build_symbol_watch_message(runtime, current_price=price))

    return (
        "⏰ แจ้งเตือนจับตาดูรายวัน (07:05 น. เวลาไทย)\n"
        "────────────────\n"
        "Daily Watchlist\n"
        f"📅 {now.strftime('%Y-%m-%d')}\n\n"
        + "\n".join(rows)
    )


def is_daily_run_time(now: datetime | None = None) -> bool:
    if now is None:
        now = datetime.now(THAI_TZ)

    if now.tzinfo is None:
        now = now.replace(tzinfo=THAI_TZ)

    return now.hour == 7 and now.minute == 5


def build_daily_summary_message(report: str, symbol: str = "BTCUSDT", now: datetime | None = None) -> str:
    if now is None:
        now = datetime.now(THAI_TZ)

    if now.tzinfo is None:
        now = now.replace(tzinfo=THAI_TZ)
    else:
        now = now.astimezone(THAI_TZ)

    return (
        f"{symbol} | Daily Summary\n"
        f"📅 {now.strftime('%Y-%m-%d')}\n\n"
        f"{report}"
    )


def run_daily_job(
    symbol: str = "BTCUSDT",
    now: datetime | None = None,
    runtime=None,
    current_price: float | None = None,
) -> None:
    from services.trading_orchestrator import _load_runtime, render_runtime_snapshot

    if runtime is None:
        runtime = _load_runtime(symbol)

    report = render_runtime_snapshot(runtime, current_price=current_price)
    send_notification(
        build_daily_summary_message(report, symbol=symbol, now=now),
        topic_key="daily_summary",
        symbol=symbol,
    )


def run_combined_daily_job(
    runtimes: list,
    current_prices: dict[str, float] | None = None,
    now: datetime | None = None,
) -> None:
    msg = build_combined_daily_summary_message(
        runtimes,
        current_prices=current_prices,
        now=now,
    )
    # Prefer DAILY_WATCH_TOPIC_ID or TELEGRAM_TOPIC_ID so the ping lands in the same forum thread as 1D alerts.
    raw_tid = (os.getenv("DAILY_WATCH_TOPIC_ID") or os.getenv("TELEGRAM_TOPIC_ID") or "").strip()
    if raw_tid.split("#", 1)[0].strip().isdigit():
        send_notification(
            msg,
            topic_id=int(raw_tid.split("#", 1)[0].strip()),
            include_layout=False,
        )
    else:
        send_notification(
            msg,
            topic_key="daily_summary",
            include_layout=False,
        )


def _daily_enabled(env_name: str, *, default: str = "0") -> bool:
    return str(os.getenv(env_name, default) or "").strip().lower() in {"1", "true", "yes", "on"}


def _fmt_wave_name(position) -> str:
    if position is None:
        return "-"
    try:
        text = describe_current_leg(position)
        return str(text) if text else "-"
    except Exception:
        # Fallbacks if a plain object/dict is passed
        if isinstance(position, dict):
            return str(position.get("position") or position.get("structure") or "-")
        return str(getattr(position, "position", None) or getattr(position, "structure", None) or "-")


def _pick_daily_analysis(runtime, timeframe: str) -> dict | None:
    target = (timeframe or "").upper().strip()
    analyses = list(getattr(runtime, "analyses", []) or [])
    if not analyses:
        return None
    for a in analyses:
        if (a.get("timeframe") or "").upper() == target:
            return a
    return analyses[0]


def _pick_main_scenario(analysis: dict):
    scenarios = analysis.get("execution_scenarios") or analysis.get("scenarios") or []
    return scenarios[0] if scenarios else None


def _support_resistance_from_scenario(scenario) -> tuple[float | None, float | None]:
    if scenario is None:
        return (None, None)
    bias = (getattr(scenario, "bias", None) or "").upper()
    confirm = getattr(scenario, "confirmation", None)
    inval = getattr(scenario, "invalidation", None)
    try:
        confirm_f = float(confirm) if confirm is not None else None
    except Exception:
        confirm_f = None
    try:
        inval_f = float(inval) if inval is not None else None
    except Exception:
        inval_f = None

    # One support / one resistance (no SL/TP):
    # - Bullish: support=invalidation, resistance=confirmation
    # - Bearish: support=confirmation, resistance=invalidation
    if bias == "BEARISH":
        return (confirm_f, inval_f)
    return (inval_f, confirm_f)


def build_daily_scenario_message(
    runtimes: list,
    *,
    now: datetime | None = None,
    timeframe: str | None = None,
) -> str:
    now = _now_bangkok(now)
    tf = (timeframe or os.getenv("DAILY_SCENARIO_TIMEFRAME", "1D") or "1D").upper().strip()

    rows: list[str] = []
    for runtime in runtimes:
        symbol = getattr(runtime, "symbol", None) or "BTCUSDT"
        analysis = _pick_daily_analysis(runtime, tf)
        if not analysis:
            rows.append(f"{symbol}\n- แนวรับ: -\n- แนวต้าน: -\n- เฝ้าดู: -")
            continue

        scenario = _pick_main_scenario(analysis)
        support, resistance = _support_resistance_from_scenario(scenario)
        wave_name = _fmt_wave_name(analysis.get("position"))

        rows.append(
            "\n".join(
                [
                    f"{symbol}",
                    f"- แนวรับ: {_fmt_value(support)}",
                    f"- แนวต้าน: {_fmt_value(resistance)}",
                    f"- เฝ้าดู: {wave_name}",
                ]
            )
        )

    return (
        "📌 Scenario Update (หลังปิดแท่ง) — 07:05 (Asia/Bangkok)\n"
        f"โฟกัส: แนวรับ/แนวต้าน (อย่างละ 1) + เฝ้าดู “ชื่อคลื่น” | TF: {tf}\n"
        f"📅 {now.strftime('%Y-%m-%d')}\n\n"
        + "\n\n".join(rows)
    )


def run_daily_scenario_job(
    runtimes: list,
    *,
    now: datetime | None = None,
) -> None:
    msg = build_daily_scenario_message(runtimes, now=now)
    raw_tid = (os.getenv("DAILY_SCENARIO_TOPIC_ID") or os.getenv("DAILY_WATCH_TOPIC_ID") or os.getenv("TELEGRAM_TOPIC_ID") or "").strip()
    if raw_tid.split("#", 1)[0].strip().isdigit():
        send_notification(
            msg,
            topic_id=int(raw_tid.split("#", 1)[0].strip()),
            include_layout=False,
        )
    else:
        send_notification(
            msg,
            topic_key="daily_summary",
            include_layout=False,
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

    symbol = getattr(runtime, "symbol", None) or "BTCUSDT"
    event_key = f"DAILY_SUMMARY:{symbol}:{now.strftime('%Y-%m-%d')}"
    if repository.has_system_event(event_key):
        return False

    # Always render the daily summary from a fresh runtime snapshot so the
    # morning report does not depend on a long-lived in-memory state.
    run_daily_job(symbol=symbol, now=now, runtime=None, current_price=current_price)
    repository.record_system_event(
        event_key,
        details={"symbol": symbol, "current_price": current_price},
    )
    return True


def maybe_run_combined_daily_job(
    repository,
    runtimes: list,
    current_prices: dict[str, float] | None = None,
    now: datetime | None = None,
) -> bool:
    if not _daily_enabled("DAILY_WATCH_ENABLED", default="0"):
        return False
    now = _now_bangkok(now)

    if not in_daily_watch_window(now):
        return False

    event_key = f"DAILY_WATCH_0705:{now.strftime('%Y-%m-%d')}"
    if repository.has_system_event(event_key):
        return False

    run_combined_daily_job(
        runtimes=runtimes,
        current_prices=current_prices,
        now=now,
    )
    repository.record_system_event(
        event_key,
        details={
            "symbols": [getattr(runtime, "symbol", None) or "BTCUSDT" for runtime in runtimes],
            "current_prices": current_prices or {},
        },
    )
    return True


def maybe_run_daily_scenario_job(
    repository,
    runtimes: list,
    now: datetime | None = None,
) -> bool:
    if not _daily_enabled("DAILY_SCENARIO_ENABLED", default="1"):
        return False
    now = _now_bangkok(now)
    if not in_daily_watch_window(now):
        return False

    event_key = f"DAILY_SCENARIO_0705:{now.strftime('%Y-%m-%d')}"
    if repository.has_system_event(event_key):
        return False

    run_daily_scenario_job(runtimes=runtimes, now=now)
    repository.record_system_event(
        event_key,
        details={"symbols": [getattr(runtime, "symbol", None) or "BTCUSDT" for runtime in runtimes]},
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
