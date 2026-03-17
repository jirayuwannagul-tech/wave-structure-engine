from __future__ import annotations

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from services.notifier import send_notification

THAI_TZ = ZoneInfo("Asia/Bangkok")


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
            elif target_bias == "BEARISH":
                if stop <= entry:
                    continue
                if targets and not any(float(target) < entry for target in targets):
                    continue
            else:
                continue

            distance = abs(float(price_reference) - entry) if price_reference is not None else float("inf")
            candidates.append((_timeframe_rank(timeframe), distance, entry))

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
    send_notification(
        build_combined_daily_summary_message(
            runtimes,
            current_prices=current_prices,
            now=now,
        ),
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
