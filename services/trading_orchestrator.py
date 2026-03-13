from __future__ import annotations

import time
from dataclasses import dataclass

from analysis.level_state_engine import detect_level_state
from analysis.price_level_watcher import Level
from core.engine import build_timeframe_analysis
from services.alert_state_store import AlertStateStore
from services.binance_price_service import get_last_price
from services.google_sheets_sync import safe_sync_signal
from services.notifier import send_notification
from services.scenario_alert_service import check_scenario_and_alert
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

    return (
        f"{timeframe} | {pattern_type} | {scenario_name}\n"
        f"Bias: {bias}\n"
        f"Setup: {setup_status}\n"
        f"Trigger: {trigger_text}\n"
        f"Entry: {_fmt_value(entry)}\n"
        f"SL: {_fmt_value(stop_loss)}\n"
        f"TP1: {_fmt_value(tp1)}\n"
        f"TP2: {_fmt_value(tp2)}\n"
        f"TP3: {_fmt_value(tp3)}"
    )


def _refresh_runtime(
    runtime: OrchestratorRuntime,
    store: AlertStateStore,
    reason: str,
    repository: WaveRepository | None = None,
    current_price: float | None = None,
    sheets_logger=None,
) -> OrchestratorRuntime:
    store.clear_prefix(f"{runtime.symbol}:LEVEL:")
    store.clear_prefix(f"{runtime.symbol}:SCENARIO:")

    refreshed = _load_runtime(runtime.symbol)
    if repository is not None:
        signal_ids = repository.sync_runtime(refreshed, current_price=current_price)
        for signal_id in signal_ids:
            safe_sync_signal(repository.fetch_signal(signal_id), sheets_logger)
    for analysis in refreshed.analyses:
        send_notification(
            f"🔄 {runtime.symbol} Re-analysis triggered\n"
            f"Reason: {reason}\n\n"
            f"{_format_analysis_summary(analysis)}",
            timeframe=analysis.get("timeframe"),
        )
    return refreshed


def render_runtime_snapshot(runtime: OrchestratorRuntime, current_price: float | None = None) -> str:
    parts = [f"Symbol: {runtime.symbol}"]
    if current_price is not None:
        parts.append(f"Current price: {_fmt_value(current_price)}")
    parts.append("")
    parts.extend(_format_analysis_summary(analysis) for analysis in runtime.analyses)
    return "\n\n".join(parts)


def _build_signal_event_message(signal_row, event_type: str) -> str | None:
    event_type = (event_type or "").upper()
    if event_type not in {"TP1_HIT", "TP2_HIT", "TP3_HIT", "STOP_LOSS_HIT"}:
        return None

    timeframe = signal_row["timeframe"]
    scenario_name = signal_row["scenario_name"]
    entry_price = signal_row["entry_price"]
    stop_loss = signal_row["stop_loss"]
    tp1 = signal_row["tp1"]
    tp2 = signal_row["tp2"]
    tp3 = signal_row["tp3"]
    status = signal_row["status"]
    tp1_mark = " ✅" if signal_row["tp1_hit_at"] else ""
    tp2_mark = " ✅" if signal_row["tp2_hit_at"] else ""
    tp3_mark = " ✅" if signal_row["tp3_hit_at"] else ""
    sl_mark = " ❌" if event_type == "STOP_LOSS_HIT" else ""

    return (
        f"{timeframe}\n\n"
        f"status: {status}\n"
        f"scenario: {scenario_name}\n"
        f"Entry: {_fmt_value(entry_price)}\n"
        f"SL: {_fmt_value(stop_loss)}{sl_mark}\n"
        f"TP1: {_fmt_value(tp1)}{tp1_mark}\n"
        f"TP2: {_fmt_value(tp2)}{tp2_mark}\n"
        f"TP3: {_fmt_value(tp3)}{tp3_mark}"
    )


def process_market_update(
    runtime: OrchestratorRuntime,
    current_price: float,
    store: AlertStateStore,
    tolerance: float = 0.002,
    repository: WaveRepository | None = None,
    sheets_logger=None,
) -> OrchestratorRuntime:
    refresh_reasons: list[str] = []

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

    for level in runtime.levels:
        state = detect_level_state(
            current_price=current_price,
            level_price=level.price,
            level_type=level.level_type,
            tolerance=tolerance,
        )

        if state is None:
            continue

        key = f"{runtime.symbol}:LEVEL:{level.name}"

        if not store.should_alert(key, state):
            continue

        if state == "NEAR":
            send_notification(
                f"⚠️ {runtime.symbol} เข้าใกล้ {level.name} ({_fmt_value(level.price)})\n"
                f"ราคาปัจจุบัน: {_fmt_value(current_price)}",
                timeframe=level.name.split()[0],
            )
        elif state == "BREAK":
            send_notification(
                f"🚨 {runtime.symbol} BREAK {level.name} ({_fmt_value(level.price)})\n"
                f"ราคาปัจจุบัน: {_fmt_value(current_price)}",
                timeframe=level.name.split()[0],
            )
            refresh_reasons.append(f"level break: {level.name}")

    for scenario_item in runtime.scenarios:
        if isinstance(scenario_item, dict):
            scenario = scenario_item.get("scenario")
            timeframe = scenario_item.get("timeframe")
        else:
            scenario = scenario_item
            timeframe = None

        if scenario is None:
            continue

        state = check_scenario_and_alert(
            scenario=scenario,
            current_price=current_price,
            store=store,
            symbol=runtime.symbol,
            timeframe=timeframe,
        )
        if state in {"CONFIRMED", "INVALIDATED"}:
            refresh_reasons.append(f"scenario {state.lower()}: {scenario.name}")

    if refresh_reasons:
        return _refresh_runtime(
            runtime=runtime,
            store=store,
            reason=", ".join(refresh_reasons),
            repository=repository,
            current_price=current_price,
            sheets_logger=sheets_logger,
        )

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
            runtime = process_market_update(
                runtime=runtime,
                current_price=price,
                store=store,
                repository=repository,
                sheets_logger=sheets_logger,
            )
            print(render_runtime_snapshot(runtime, current_price=price))

            if once:
                return runtime

            time.sleep(poll_interval)

        except Exception as e:
            print("Error:", e)
            if once:
                raise
            time.sleep(max(poll_interval, 10))


if __name__ == "__main__":
    run_orchestrator()
