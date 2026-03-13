from __future__ import annotations

import time
from dataclasses import dataclass

from analysis.price_level_watcher import Level
from core.engine import build_timeframe_analysis
from scheduler.daily_scheduler import maybe_run_daily_job
from services.alert_state_store import AlertStateStore
from services.binance_price_service import get_last_price
from services.google_sheets_sync import safe_sync_signal
from services.notifier import send_notification
from storage.wave_repository import WaveRepository
from scenarios.scenario_state_machine import update_scenario_state


@dataclass
class OrchestratorRuntime:
    symbol: str
    analyses: list[dict]
    levels: list[Level]
    scenarios: list


def _fmt_value(value) -> str:
    if value is None:
        return "None"
    if isinstance(value, (int, float)):
        rounded = round(float(value), 4)
        text = f"{rounded:.4f}".rstrip("0").rstrip(".")
        return text or "0"
    return str(value)


def _humanize_token(value: str | None) -> str:
    if not value:
        return "-"
    text = value.replace("_", " ").strip().title()
    return (
        text.replace("Tp1", "TP1")
        .replace("Tp2", "TP2")
        .replace("Tp3", "TP3")
        .replace("Sl", "SL")
    )


def _optional_level_line(label: str, value, suffix: str = "") -> str | None:
    if value is None:
        return None
    return f"• {label}: {_fmt_value(value)}{suffix}"


def _fallback_targets(
    bias: str | None,
    entry: float | None,
    stop_loss: float | None,
) -> list[float]:
    if bias is None or entry is None or stop_loss is None:
        return []

    side = bias.upper()
    risk = abs(float(entry) - float(stop_loss))
    if risk <= 0:
        return []

    if side == "BULLISH":
        raw_targets = [
            float(entry) + (risk * 1.0),
            float(entry) + (risk * 1.272),
            float(entry) + (risk * 1.618),
        ]
    elif side == "BEARISH":
        raw_targets = [
            float(entry) - (risk * 1.0),
            float(entry) - (risk * 1.272),
            float(entry) - (risk * 1.618),
        ]
    else:
        return []

    return [round(target, 4) for target in raw_targets]


def _infer_setup_status(
    bias: str | None,
    entry: float | None,
    stop_loss: float | None,
    current_price: float | None,
) -> tuple[str, str]:
    bias = (bias or "").upper()

    if current_price is None or entry is None:
        return "UNKNOWN", "WAIT"

    if bias == "BULLISH":
        if stop_loss is not None and current_price <= stop_loss:
            return "INVALIDATED", "ABOVE"
        if current_price >= entry:
            return "ACTIVE", "ABOVE"
        return "WAITING_BREAKOUT", "ABOVE"

    if bias == "BEARISH":
        if stop_loss is not None and current_price >= stop_loss:
            return "INVALIDATED", "BELOW"
        if current_price <= entry:
            return "ACTIVE", "BELOW"
        return "WAITING_BREAKDOWN", "BELOW"

    return "NEUTRAL", "WAIT"


def _select_display_scenario(scenarios, current_price: float | None):
    if not scenarios:
        return None, "UNKNOWN"

    if current_price is None:
        return scenarios[0], "UNKNOWN"

    ranked = []
    priority = {
        "CONFIRMED": 0,
        "WAITING_CONFIRMATION": 1,
        "INVALIDATED": 2,
        "UNKNOWN": 3,
    }

    for index, scenario in enumerate(scenarios):
        state = update_scenario_state(scenario, current_price)
        ranked.append((priority.get(state, 99), index, scenario, state))

    ranked.sort(key=lambda item: (item[0], item[1]))
    _, _, scenario, state = ranked[0]
    return scenario, state


def _build_levels_from_analysis(analysis: dict) -> list[Level]:
    levels: list[Level] = []
    timeframe = analysis["timeframe"]
    wave_summary = analysis.get("wave_summary") or {}

    stop_loss = wave_summary.get("stop_loss")
    confirm = wave_summary.get("confirm")

    if stop_loss is not None:
        levels.append(Level(f"{timeframe} Support", float(stop_loss), "support"))

    if confirm is not None:
        levels.append(Level(f"{timeframe} Resistance", float(confirm), "resistance"))

    return levels


def _build_runtime(symbol: str, analyses: list[dict]) -> OrchestratorRuntime:
    levels: list[Level] = []
    scenarios: list = []

    for analysis in analyses:
        levels.extend(_build_levels_from_analysis(analysis))
        for scenario in analysis.get("scenarios", []):
            scenarios.append(
                {
                    "timeframe": analysis.get("timeframe"),
                    "scenario": scenario,
                }
            )

    return OrchestratorRuntime(
        symbol=symbol,
        analyses=analyses,
        levels=levels,
        scenarios=scenarios,
    )


def _load_runtime(symbol: str = "BTCUSDT") -> OrchestratorRuntime:
    analyses = [
        build_timeframe_analysis(symbol, "1d", 200),
        build_timeframe_analysis(symbol, "4h", 200),
    ]
    return _build_runtime(symbol, analyses)


def _format_analysis_summary(analysis: dict) -> str:
    timeframe = analysis["timeframe"]
    pattern_type = analysis.get("primary_pattern_type") or "UNKNOWN"
    scenarios = analysis.get("scenarios") or []
    wave_summary = analysis.get("wave_summary") or {}
    current_price = analysis.get("current_price")
    main_scenario, scenario_state = _select_display_scenario(scenarios, current_price)

    bias = getattr(main_scenario, "bias", None) or wave_summary.get("bias") or "NONE"
    entry = getattr(main_scenario, "confirmation", None)
    stop_loss = getattr(main_scenario, "stop_loss", None)
    targets = list(getattr(main_scenario, "targets", []) or [])

    if entry is None:
        entry = wave_summary.get("confirm")
    if stop_loss is None:
        stop_loss = wave_summary.get("stop_loss")
    if not targets:
        targets = list(wave_summary.get("targets", []) or [])
    if not targets:
        targets = _fallback_targets(bias, entry, stop_loss)

    tp1 = targets[0] if len(targets) >= 1 else None
    tp2 = targets[1] if len(targets) >= 2 else None
    tp3 = targets[2] if len(targets) >= 3 else None
    scenario_name = getattr(main_scenario, "name", None) or "No active scenario"
    setup_status, trigger_side = _infer_setup_status(
        bias=bias,
        entry=entry,
        stop_loss=stop_loss,
        current_price=current_price,
    )
    if scenario_state == "CONFIRMED":
        setup_status = "ACTIVE"
    elif scenario_state == "INVALIDATED":
        setup_status = "INVALIDATED"
    if trigger_side == "ABOVE":
        trigger_text = f"Above {_fmt_value(entry)}"
    elif trigger_side == "BELOW":
        trigger_text = f"Below {_fmt_value(entry)}"
    else:
        trigger_text = _fmt_value(entry)

    lines = [
        timeframe,
        f"• Structure: {pattern_type}",
        f"• Scenario: {scenario_name}",
        f"• Bias: {bias}",
        f"• Setup: {_humanize_token(setup_status)}",
        f"• Trigger: {trigger_text}",
        f"• Entry: {_fmt_value(entry)}",
        f"• SL: {_fmt_value(stop_loss)}",
        _optional_level_line("TP1", tp1),
        _optional_level_line("TP2", tp2),
        _optional_level_line("TP3", tp3),
    ]
    return "\n".join(line for line in lines if line)


def _refresh_runtime(
    runtime: OrchestratorRuntime,
    store: AlertStateStore,
    reason: str,
    repository: WaveRepository | None = None,
    current_price: float | None = None,
    sheets_logger=None,
) -> OrchestratorRuntime:
    refreshed = _load_runtime(runtime.symbol)
    if repository is not None:
        signal_ids = repository.sync_runtime(refreshed, current_price=current_price)
        for signal_id in signal_ids:
            safe_sync_signal(repository.fetch_signal(signal_id), sheets_logger)
    for analysis in refreshed.analyses:
        send_notification(
            f"🔄 {runtime.symbol} | Re-analysis Update\n\n"
            f"Reason:\n• {reason.replace(', ', chr(10) + '• ')}\n\n"
            f"{_format_analysis_summary(analysis)}",
            timeframe=analysis.get("timeframe"),
        )
    return refreshed


def render_runtime_snapshot(runtime: OrchestratorRuntime, current_price: float | None = None) -> str:
    parts = []
    if current_price is not None:
        parts.append(f"💵 Current / Close: {_fmt_value(current_price)}")
        parts.append("")
    parts.extend(_format_analysis_summary(analysis) for analysis in runtime.analyses)
    return "\n\n".join(parts)


def _build_signal_event_message(signal_row, event_type: str) -> str | None:
    event_type = (event_type or "").upper()
    if event_type not in {"ENTRY_TRIGGERED", "TP1_HIT", "TP2_HIT", "TP3_HIT", "STOP_LOSS_HIT"}:
        return None

    timeframe = signal_row["timeframe"]
    scenario_name = signal_row["scenario_name"]
    entry_price = signal_row["entry_price"]
    stop_loss = signal_row["stop_loss"]
    tp1 = signal_row["tp1"]
    tp2 = signal_row["tp2"]
    tp3 = signal_row["tp3"]
    status = signal_row["status"]
    symbol = signal_row["symbol"]
    tp1_mark = " ✅" if signal_row["tp1_hit_at"] else ""
    tp2_mark = " ✅" if signal_row["tp2_hit_at"] else ""
    tp3_mark = " ✅" if signal_row["tp3_hit_at"] else ""
    sl_mark = " ❌" if event_type == "STOP_LOSS_HIT" else ""
    event_titles = {
        "ENTRY_TRIGGERED": "Entry Triggered",
        "TP1_HIT": "TP1 Hit",
        "TP2_HIT": "TP2 Hit",
        "TP3_HIT": "TP3 Hit",
        "STOP_LOSS_HIT": "Stop Loss Hit",
    }
    lines = [
        f"{'❌' if event_type == 'STOP_LOSS_HIT' else ('🎯' if event_type == 'ENTRY_TRIGGERED' else '✅')} {symbol} | {timeframe} {event_titles[event_type]}",
        "",
        f"• Scenario: {scenario_name}",
        f"• Status: {_humanize_token(status)}",
        f"• Entry: {_fmt_value(entry_price)}",
        f"• SL: {_fmt_value(stop_loss)}{sl_mark}",
        _optional_level_line("TP1", tp1, tp1_mark),
        _optional_level_line("TP2", tp2, tp2_mark),
        _optional_level_line("TP3", tp3, tp3_mark),
    ]
    return "\n".join(line for line in lines if line is not None)


def process_market_update(
    runtime: OrchestratorRuntime,
    current_price: float,
    store: AlertStateStore,
    tolerance: float = 0.002,
    repository: WaveRepository | None = None,
    sheets_logger=None,
) -> OrchestratorRuntime:
    if repository is not None:
        lifecycle_events = repository.track_price_update(runtime.symbol, current_price)
        for signal_id, event_type in lifecycle_events:
            signal_row = repository.fetch_signal(signal_id)
            if signal_row is None:
                continue
            safe_sync_signal(signal_row, sheets_logger)
            message = _build_signal_event_message(signal_row, event_type)
            if message:
                send_notification(message, timeframe=signal_row["timeframe"], include_layout=False)

    return runtime


def run_orchestrator(
    symbol: str = "BTCUSDT",
    poll_interval: float = 5.0,
    once: bool = False,
    repository: WaveRepository | None = None,
    sheets_logger=None,
) -> OrchestratorRuntime:
    runtime = _load_runtime(symbol)
    store = AlertStateStore()
    repository = repository or WaveRepository()
    signal_ids = repository.sync_runtime(runtime)
    for signal_id in signal_ids:
        safe_sync_signal(repository.fetch_signal(signal_id), sheets_logger)

    print("Starting trading orchestrator...")
    print("Loaded levels:")
    for level in runtime.levels:
        print(f"- {level.name}: {level.price} ({level.level_type})")

    while True:
        try:
            price = get_last_price(runtime.symbol)
            print(f"BTC price: {price}")
            daily_sent = maybe_run_daily_job(
                repository=repository,
                runtime=runtime,
                current_price=price,
            )
            if daily_sent:
                runtime = _load_runtime(runtime.symbol)
                signal_ids = repository.sync_runtime(runtime, current_price=price)
                for signal_id in signal_ids:
                    safe_sync_signal(repository.fetch_signal(signal_id), sheets_logger)
            runtime = process_market_update(
                runtime=runtime,
                current_price=price,
                store=store,
                repository=repository,
                sheets_logger=sheets_logger,
            )

            if once:
                print(render_runtime_snapshot(runtime, current_price=price))
                return runtime

            time.sleep(poll_interval)

        except Exception as e:
            print("Error:", e)
            if once:
                raise
            time.sleep(max(poll_interval, 10))


if __name__ == "__main__":
    run_orchestrator()
