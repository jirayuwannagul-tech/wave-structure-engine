from __future__ import annotations

import time
import traceback
from dataclasses import dataclass
import os

from analysis.price_level_watcher import Level
from analysis.setup_filter import build_higher_timeframe_context, extract_trade_bias
from analysis.wave_position import describe_current_leg
from core.engine import build_timeframe_analysis
from scheduler.daily_scheduler import maybe_run_combined_daily_job
from services.alert_state_store import AlertStateStore
from services.binance_price_service import get_last_price
from services.google_sheets_sync import compute_signal_tracking, safe_sync_signal
from services.market_data_sync import sync_recent_market_data
from services.notifier import send_notification
from services.scenario_alert_service import check_scenario_and_alert
from storage.manual_wave_context import get_manual_wave_context, serialize_manual_wave_context
from storage.position_store import PositionStore
from storage.wave_repository import WaveRepository
from scenarios.scenario_state_machine import update_scenario_state

from execution.binance_futures_client import BinanceFuturesClient
from execution.position_manager import PositionManager
from execution.reconciler import reconcile_symbol
from execution.settings import load_execution_config


@dataclass
class OrchestratorRuntime:
    symbol: str
    analyses: list[dict]
    levels: list[Level]
    scenarios: list


MARKET_DATA_SYNC_TIMEFRAMES = ("1W", "1D", "4H")
MARKET_DATA_SYNC_INTERVAL_SECONDS = float(os.getenv("MARKET_DATA_SYNC_INTERVAL_SECONDS", "300"))


def _maybe_run_exchange_execution(symbol: str, event_type: str, signal_row) -> None:
    """Binance futures testnet/live hooks: no strategy filters."""
    cfg = load_execution_config()
    if not cfg.enabled or not cfg.live_order_enabled or not cfg.credentials_ready:
        return
    if str(os.getenv("KILL_SWITCH", "0")).strip().lower() in {"1", "true", "yes", "on"}:
        return
    try:
        client = BinanceFuturesClient(cfg)
        store = PositionStore()
        pm = PositionManager(client, cfg, store)
        if event_type == "ENTRY_TRIGGERED":
            eq_usdt = 0.0
            try:
                bal = client.get_account_balance()
                if isinstance(bal, list):
                    for row in bal:
                        if str(row.get("asset") or "").upper() == "USDT":
                            for key in ("availableBalance", "walletBalance", "balance"):
                                v = row.get(key)
                                if v is not None:
                                    eq_usdt = float(v)
                                    break
                            if eq_usdt > 0:
                                break
            except Exception:
                eq_usdt = 0.0
            result = pm.open_from_signal(
                signal_row,
                account_equity_usdt=eq_usdt if eq_usdt > 0 else None,
            )
            if not result.get("ok"):
                print(f"[orchestrator] exchange open_from_signal: {result}")
        elif event_type in (
            "STOP_LOSS_HIT",
            "TP3_HIT",
            "TIME_STOP_HIT",
            "OPPOSITE_STRUCTURE_HIT",
            "VOLATILITY_EXIT_HIT",
        ):
            pm.close_for_signal(signal_row, event_type)
    except Exception as exc:
        print(f"[orchestrator] exchange execution error: {exc}")
        traceback.print_exc()


def _reconcile_exchange_positions(symbols: list[str]) -> None:
    cfg = load_execution_config()
    if not cfg.enabled or not cfg.credentials_ready:
        return
    if str(os.getenv("KILL_SWITCH", "0")).strip().lower() in {"1", "true", "yes", "on"}:
        return
    store = PositionStore()
    try:
        client = BinanceFuturesClient(cfg)
    except Exception:
        return
    for sym in symbols:
        try:
            reconcile_symbol(client, store, sym, cfg)
        except Exception as exc:
            print(f"[orchestrator] reconcile {sym}: {exc}")


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


def _optional_text_line(label: str, value, suffix: str = "") -> str | None:
    if value in (None, ""):
        return None
    return f"• {label}: {value}{suffix}"


def _format_trade_side(side: str | None) -> str:
    normalized = (side or "").upper()
    if normalized == "LONG":
        return "🟢 Long"
    if normalized == "SHORT":
        return "🔴 Short"
    return _humanize_token(side)


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
        execution_scenarios = (
            analysis.get("execution_scenarios")
            if "execution_scenarios" in analysis
            else analysis.get("scenarios")
        ) or []
        for scenario in execution_scenarios:
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


def _resolve_weekly_context(symbol: str) -> tuple[dict, dict | None]:
    analysis_1w = build_timeframe_analysis(symbol, "1w", 200)
    manual_context = get_manual_wave_context(symbol, "1W")

    if manual_context is None:
        analysis_1w["manual_wave_context"] = None
        return analysis_1w, build_higher_timeframe_context(analysis_1w)

    analysis_1w["manual_wave_context"] = serialize_manual_wave_context(manual_context)
    return analysis_1w, analysis_1w["manual_wave_context"]


def _load_runtime(symbol: str = "BTCUSDT", retries: int = 3) -> OrchestratorRuntime:
    """Load analysis for all timeframes, retrying on transient failures."""
    delay = 5.0
    for attempt in range(1, retries + 1):
        try:
            analysis_1w, weekly_context = _resolve_weekly_context(symbol)
            weekly_bias = (weekly_context or {}).get("bias")
            weekly_wave_number = (weekly_context or {}).get("wave_number")
            analysis_1d = build_timeframe_analysis(
                symbol,
                "1d",
                200,
                higher_timeframe_bias=weekly_bias,
                higher_timeframe_wave_number=weekly_wave_number,
                higher_timeframe_context=weekly_context,
            )
            analysis_1d["higher_timeframe_context"] = weekly_context
            higher_timeframe_bias = extract_trade_bias(analysis_1d)
            inprogress_1d = analysis_1d.get("inprogress")
            position_1d = analysis_1d.get("position")
            htf_wave_number = None
            if inprogress_1d is not None and getattr(inprogress_1d, "is_valid", False):
                htf_wave_number = getattr(inprogress_1d, "wave_number", None)
            elif position_1d is not None:
                htf_wave_number = getattr(position_1d, "wave_number", None) or describe_current_leg(position_1d)
            daily_context = build_higher_timeframe_context(analysis_1d) or {
                "timeframe": "1D",
                "bias": higher_timeframe_bias,
                "wave_number": htf_wave_number,
            }
            if weekly_context:
                daily_context["parent"] = weekly_context
            analysis_4h = build_timeframe_analysis(
                symbol, "4h", 200,
                higher_timeframe_bias=higher_timeframe_bias,
                higher_timeframe_wave_number=htf_wave_number,
                higher_timeframe_context=daily_context,
            )
            analysis_4h["higher_timeframe_context"] = daily_context

            # ── Hierarchical wave count injection (1D) ────────────────────
            # Disabled in live until stop/target validation is solid.
            # Re-enable by setting env HIER_LIVE=1
            _hier_live_enabled = os.getenv("HIER_LIVE", "0").strip() == "1"
            if _hier_live_enabled and not (analysis_1d.get("scenarios") or []):
                try:
                    from pathlib import Path
                    import pandas as pd
                    from analysis.hierarchical_wave_counter import build_hierarchical_count_from_dfs
                    csv_1w = Path(f"data/{symbol}_1w.csv")
                    csv_1d = Path(f"data/{symbol}_1d.csv")
                    if csv_1w.exists() and csv_1d.exists():
                        from analysis.indicator_engine import calculate_atr as _atr
                        df_1w = pd.read_csv(csv_1w)
                        df_1d = pd.read_csv(csv_1d)
                        for _df in (df_1w, df_1d):
                            if "open_time" in _df.columns:
                                _df["open_time"] = pd.to_datetime(_df["open_time"], utc=True, errors="coerce")
                            if "atr" not in _df.columns:
                                _df["atr"] = _atr(_df, period=14)
                        current_price_live = float(df_1d.iloc[-1]["close"])
                        hier = build_hierarchical_count_from_dfs(
                            symbol=symbol,
                            primary_df=df_1w,
                            intermediate_df=df_1d,
                            current_price=current_price_live,
                        )
                        htf_aligned = (
                            weekly_bias is None
                            or hier.trade_bias == str(weekly_bias).upper()
                        )
                        if (
                            htf_aligned
                            and hier.scenarios
                            and hier.hierarchical_confidence >= 0.30
                            and hier.is_consistent
                        ):
                            active_pos = hier.intermediate or hier.primary
                            wave_label = (
                                f"{active_pos.structure}_W{active_pos.wave_number}"
                                if active_pos else "HIERARCHICAL"
                            )
                            analysis_1d = dict(analysis_1d)
                            analysis_1d["scenarios"] = hier.scenarios
                            analysis_1d["execution_scenarios"] = hier.scenarios
                            analysis_1d["has_pattern"] = True
                            analysis_1d["primary_pattern_type"] = wave_label
                            analysis_1d["_hier_count"] = hier
                except Exception as _hier_exc:
                    print(f"[orchestrator] hierarchical injection failed: {_hier_exc}")

            analyses = [analysis_1d, analysis_4h]
            return _build_runtime(symbol, analyses)
        except Exception as exc:
            if attempt == retries:
                raise
            print(f"[orchestrator] _load_runtime attempt {attempt} failed ({exc}), retrying in {delay}s…")
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")  # pragma: no cover


def _format_analysis_summary(analysis: dict) -> str:
    timeframe = analysis["timeframe"]
    pattern_type = analysis.get("primary_pattern_type") or "UNKNOWN"
    position = analysis.get("position")
    current_leg = describe_current_leg(position)
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
        _optional_level_line("Current Leg", current_leg),
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
            symbol=runtime.symbol,
        )
    return refreshed


def render_runtime_snapshot(runtime: OrchestratorRuntime, current_price: float | None = None) -> str:
    """Format a human-readable snapshot of the current runtime state."""
    parts = []
    if current_price is not None:
        parts.append(f"💵 Current / Close: {_fmt_value(current_price)}")
        parts.append("")
    parts.extend(_format_analysis_summary(analysis) for analysis in runtime.analyses)
    return "\n\n".join(parts)


def _build_signal_event_message(signal_row, event_type: str) -> str | None:
    event_type = (event_type or "").upper()
    if event_type not in {
        "ENTRY_TRIGGERED",
        "TP1_HIT",
        "TP2_HIT",
        "TP3_HIT",
        "STOP_LOSS_HIT",
        "TIME_STOP_HIT",
        "OPPOSITE_STRUCTURE_HIT",
        "VOLATILITY_EXIT_HIT",
    }:
        return None

    def _signal_value(key: str):
        if hasattr(signal_row, "keys"):
            try:
                if key in signal_row.keys():
                    return signal_row[key]
            except Exception:
                pass
        if isinstance(signal_row, dict):
            return signal_row.get(key)
        return signal_row[key]

    timeframe = _signal_value("timeframe")
    scenario_name = _signal_value("scenario_name")
    entry_price = _signal_value("entry_price")
    stop_loss = _signal_value("stop_loss")
    tp1 = _signal_value("tp1")
    tp2 = _signal_value("tp2")
    tp3 = _signal_value("tp3")
    status = _signal_value("status")
    symbol = _signal_value("symbol")
    side = _signal_value("side")
    rr_tp1 = _signal_value("rr_tp1")
    rr_tp2 = _signal_value("rr_tp2")
    rr_tp3 = _signal_value("rr_tp3")
    tracking = compute_signal_tracking(signal_row)
    tg_marks = {"✓": "✅", "✗": "❌"}
    tp1_mark = f" {tg_marks[tracking['tp1_mark']]}" if tracking["tp1_mark"] else ""
    tp2_mark = f" {tg_marks[tracking['tp2_mark']]}" if tracking["tp2_mark"] else ""
    tp3_mark = f" {tg_marks[tracking['tp3_mark']]}" if tracking["tp3_mark"] else ""
    sl_mark = f" {tg_marks[tracking['sl_mark']]}" if tracking["sl_mark"] else ""
    event_titles = {
        "ENTRY_TRIGGERED": "Entry Triggered",
        "TP1_HIT": "TP1 Hit",
        "TP2_HIT": "TP2 Hit",
        "TP3_HIT": "TP3 Hit",
        "STOP_LOSS_HIT": "Stop Loss Hit",
        "TIME_STOP_HIT": "Time Stop Hit",
        "OPPOSITE_STRUCTURE_HIT": "Opposite Structure Exit",
        "VOLATILITY_EXIT_HIT": "Volatility Exit",
    }
    event_icons = {
        "ENTRY_TRIGGERED": "🎯",
        "TP1_HIT": "✅",
        "TP2_HIT": "✅",
        "TP3_HIT": "✅",
        "STOP_LOSS_HIT": "❌",
        "TIME_STOP_HIT": "⏱",
        "OPPOSITE_STRUCTURE_HIT": "🛡",
        "VOLATILITY_EXIT_HIT": "🛡",
    }

    def _rr_suffix(value) -> str:
        if value is None:
            return ""
        return f" ({_fmt_value(value)}R)"

    lines = [
        f"{event_icons[event_type]} {symbol} | {timeframe} {event_titles[event_type]}",
        "",
        f"• Scenario: {scenario_name}",
        f"• Status: {_humanize_token(status)}",
        f"• Side: {_format_trade_side(side)}",
        f"• Entry: {_fmt_value(entry_price)}",
        f"• SL: {_fmt_value(stop_loss)}{sl_mark}",
        _optional_level_line("TP1", tp1, f"{tp1_mark}{_rr_suffix(rr_tp1)}"),
        _optional_level_line("TP2", tp2, f"{tp2_mark}{_rr_suffix(rr_tp2)}"),
        _optional_level_line("TP3", tp3, f"{tp3_mark}{_rr_suffix(rr_tp3)}"),
        _optional_text_line("Result", _humanize_token(tracking["result"])),
        _optional_text_line("Realized RR", tracking["realized_rr"], "R"),
        _optional_text_line("Win Rate", tracking["win_rate_pct"], "%"),
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
    for item in runtime.scenarios:
        if isinstance(item, dict):
            scenario = item.get("scenario")
            timeframe = item.get("timeframe")
        else:
            scenario = item
            timeframe = None
        if scenario is None:
            continue
        check_scenario_and_alert(
            scenario=scenario,
            current_price=current_price,
            store=store,
            symbol=runtime.symbol,
            timeframe=timeframe,
        )

    if repository is not None:
        lifecycle_events = repository.track_price_update(
            runtime.symbol,
            current_price,
            analyses=runtime.analyses,
        )
        for signal_id, event_type in lifecycle_events:
            signal_row = repository.fetch_signal(signal_id)
            if signal_row is None:
                continue
            safe_sync_signal(signal_row, sheets_logger)
            message = _build_signal_event_message(signal_row, event_type)
            if message:
                send_notification(
                    message,
                    timeframe=signal_row["timeframe"],
                    symbol=signal_row["symbol"],
                    include_layout=False,
                )
            _maybe_run_exchange_execution(runtime.symbol, event_type, signal_row)

    return runtime


def run_orchestrator(
    symbol: str = "BTCUSDT",
    symbols: list[str] | None = None,
    poll_interval: float = 5.0,
    once: bool = False,
    repository: WaveRepository | None = None,
    sheets_logger=None,
) -> OrchestratorRuntime:
    """Start the live Elliott Wave monitoring loop.

    Polls Binance every poll_interval seconds, checks price vs key levels,
    updates signal lifecycle states in SQLite, and sends Telegram alerts.

    Args:
        symbol: Trading pair to monitor (default "BTCUSDT").
        symbols: Optional list of trading pairs to monitor in one process.
        poll_interval: Seconds between each price-check cycle (default 5.0).
        once: If True, run exactly one cycle and return (dry-run mode).
        repository: WaveRepository instance. A new one is created if None.
        sheets_logger: Optional Google Sheets sync logger instance.

    Returns:
        The OrchestratorRuntime from the last completed cycle.
    """
    symbols = [item.upper() for item in (symbols or [symbol]) if item]
    store = AlertStateStore()
    repository = repository or WaveRepository()
    sync_recent_market_data(
        symbols=symbols,
        timeframes=list(MARKET_DATA_SYNC_TIMEFRAMES),
        repository=repository,
    )
    last_market_data_sync_at = time.time()
    runtimes = {item: _load_runtime(item) for item in symbols}
    for runtime in runtimes.values():
        signal_ids = repository.sync_runtime(runtime)
        for signal_id in signal_ids:
            safe_sync_signal(repository.fetch_signal(signal_id), sheets_logger)

    print("Starting trading orchestrator...")
    for runtime in runtimes.values():
        print(f"Loaded levels for {runtime.symbol}:")
        for level in runtime.levels:
            print(f"- {level.name}: {level.price} ({level.level_type})")

    while True:
        try:
            snapshots: list[str] = []
            now_ts = time.time()
            refresh_runtimes = False
            if now_ts - last_market_data_sync_at >= MARKET_DATA_SYNC_INTERVAL_SECONDS:
                sync_recent_market_data(
                    symbols=symbols,
                    timeframes=list(MARKET_DATA_SYNC_TIMEFRAMES),
                    repository=repository,
                )
                last_market_data_sync_at = now_ts
                refresh_runtimes = True
            price_updates: dict[str, float] = {}
            ordered_runtimes: list[OrchestratorRuntime] = []
            for runtime in list(runtimes.values()):
                if refresh_runtimes:
                    runtime = _load_runtime(runtime.symbol)
                    runtimes[runtime.symbol] = runtime
                    signal_ids = repository.sync_runtime(runtime)
                    for signal_id in signal_ids:
                        safe_sync_signal(repository.fetch_signal(signal_id), sheets_logger)
                price = get_last_price(runtime.symbol)
                price_updates[runtime.symbol] = price
                ordered_runtimes.append(runtime)
                print(f"{runtime.symbol} price: {price}")
            maybe_run_combined_daily_job(
                repository=repository,
                runtimes=ordered_runtimes,
                current_prices=price_updates,
            )

            for runtime in ordered_runtimes:
                price = price_updates[runtime.symbol]
                runtime = process_market_update(
                    runtime=runtime,
                    current_price=price,
                    store=store,
                    repository=repository,
                    sheets_logger=sheets_logger,
                )
                runtimes[runtime.symbol] = runtime
                if once:
                    snapshots.append(
                        f"{runtime.symbol}\n\n{render_runtime_snapshot(runtime, current_price=price)}"
                    )

            _reconcile_exchange_positions(symbols)

            if once:
                print("\n\n".join(snapshots))
                return next(iter(runtimes.values()))

            time.sleep(poll_interval)

        except KeyboardInterrupt:
            print("[orchestrator] Stopped by user.")
            break
        except Exception as e:
            print(f"[orchestrator] Unhandled error: {e}")
            traceback.print_exc()
            if once:
                raise
            backoff = max(poll_interval * 2, 30)
            print(f"[orchestrator] Backing off for {backoff}s before next cycle…")
            time.sleep(backoff)


if __name__ == "__main__":
    run_orchestrator()
