from __future__ import annotations

import os
import subprocess
import time
from typing import Any

from execution.binance_futures_client import BinanceFuturesClient
from execution.settings import load_execution_config
from services.binance_price_service import get_last_price
from services.trading_orchestrator import _fallback_targets, _load_runtime, _select_display_scenario


def _is_valid_signal_shape(bias: Any, entry: Any, stop_loss: Any, tp1: Any) -> bool:
    if bias is None or entry is None or stop_loss is None:
        return False
    try:
        entry_value = float(entry)
        stop_value = float(stop_loss)
    except (TypeError, ValueError):
        return False

    side = str(bias).upper()
    if side == "BULLISH":
        if stop_value >= entry_value:
            return False
        if tp1 is not None:
            try:
                if float(tp1) <= entry_value:
                    return False
            except (TypeError, ValueError):
                return False
        return True

    if side == "BEARISH":
        if stop_value <= entry_value:
            return False
        if tp1 is not None:
            try:
                if float(tp1) >= entry_value:
                    return False
            except (TypeError, ValueError):
                return False
        return True

    return False


def _fmt_number(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return value
    if isinstance(value, (int, float)):
        rounded = round(float(value), 4)
        text = f"{rounded:,.4f}".rstrip("0").rstrip(".")
        return text or "0"
    return str(value)


def _service_status(service_name: str) -> str:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "n/a"
    status = (result.stdout or "").strip()
    return status or "unknown"


def _resolve_dashboard_symbols(symbol: str) -> list[str]:
    configured = (os.getenv("MONITOR_SYMBOLS") or "").split(",")
    symbols = [item.strip().upper() for item in configured if item.strip()]
    if not symbols:
        symbols = [symbol.upper()]
    if symbol.upper() not in symbols:
        symbols.insert(0, symbol.upper())
    return symbols


def _build_signals(runtimes: list) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for runtime in runtimes:
        for analysis in runtime.analyses:
            scenarios = analysis.get("scenarios") or analysis.get("all_scenarios") or []
            scenario, _ = _select_display_scenario(scenarios, analysis.get("current_price"))
            wave_summary = analysis.get("wave_summary") or {}
            summary_bias = wave_summary.get("bias")
            summary_entry = wave_summary.get("confirm")
            summary_stop = wave_summary.get("stop_loss")
            summary_targets = list(wave_summary.get("targets", []) or [])
            summary_tp1 = summary_targets[0] if len(summary_targets) >= 1 else None

            scenario_bias = getattr(scenario, "bias", None) if scenario is not None else None
            scenario_entry = getattr(scenario, "confirmation", None) if scenario is not None else None
            scenario_stop = getattr(scenario, "stop_loss", None) if scenario is not None else None
            scenario_targets = list(getattr(scenario, "targets", []) or []) if scenario is not None else []
            scenario_tp1 = scenario_targets[0] if len(scenario_targets) >= 1 else None

            use_summary = _is_valid_signal_shape(summary_bias, summary_entry, summary_stop, summary_tp1)
            use_scenario = _is_valid_signal_shape(scenario_bias, scenario_entry, scenario_stop, scenario_tp1)

            if use_summary:
                bias = summary_bias
                entry = summary_entry
                stop_loss = summary_stop
                targets = summary_targets
            elif use_scenario:
                bias = scenario_bias
                entry = scenario_entry
                stop_loss = scenario_stop
                targets = scenario_targets
            else:
                # No valid signal shape — skip this timeframe entirely
                continue

            if not targets:
                targets = _fallback_targets(bias, entry, stop_loss)
            tp1 = targets[0] if len(targets) >= 1 else None

            # Final sanity check before appending
            if not _is_valid_signal_shape(bias, entry, stop_loss, tp1):
                continue

            signals.append(
                {
                    "symbol": runtime.symbol,
                    "timeframe": analysis.get("timeframe"),
                    "bias": bias or "NONE",
                    "entry": entry,
                    "sl": stop_loss,
                    "tp1": tp1,
                }
            )
    return signals


def build_dashboard_snapshot(symbol: str = "BTCUSDT") -> dict[str, Any]:
    config = load_execution_config()
    client = BinanceFuturesClient(config)
    dashboard_symbols = _resolve_dashboard_symbols(symbol)
    runtimes = [_load_runtime(item) for item in dashboard_symbols]
    try:
        current_price = get_last_price(symbol)
    except Exception:
        current_price = None
    try:
        account = client.get_account_information()
        balance_rows = client.get_balance()
        position_rows = client.get_position_risk()
        connection = "ok"
        usdt_balance = next(
            (row for row in balance_rows if (row.get("asset") or "").upper() == "USDT"),
            None,
        )
        open_positions = []
        for row in position_rows:
            amount = float(row.get("positionAmt") or 0.0)
            if amount == 0.0:
                continue
            side = "LONG" if amount > 0 else "SHORT"
            open_positions.append(
                {
                    "symbol": row.get("symbol"),
                    "side": side,
                    "qty": abs(amount),
                    "entry": float(row.get("entryPrice") or 0.0),
                    "mark": float(row.get("markPrice") or 0.0),
                    "pnl": float(row.get("unRealizedProfit") or 0.0),
                }
            )
    except Exception:
        account = {}
        connection = "auth error"
        usdt_balance = None
        open_positions = []

    return {
        "exchange": "binance futures",
        "symbol": symbol,
        "connection": connection,
        "current_price": current_price,
        "orchestrator": _service_status("elliott-wave-orchestrator.service"),
        "news_monitor": _service_status("elliott-wave-news-monitor.service"),
        "monitored_symbols": dashboard_symbols,
        "wallet": _fmt_number((usdt_balance or {}).get("balance")),
        "available": _fmt_number((usdt_balance or {}).get("availableBalance")),
        "upnl": _fmt_number((usdt_balance or {}).get("crossUnPnl")),
        "positions": open_positions,
        "signals": _build_signals(runtimes),
        "account_assets": len(account.get("assets", [])) if isinstance(account, dict) else 0,
    }


def render_terminal_dashboard(snapshot: dict[str, Any]) -> str:
    lines = [
        "● ● ●  Elliott Wave Terminal",
        "",
        "$ system status",
        f"exchange      {snapshot['exchange']}",
        f"connection    {snapshot['connection']}",
        f"orchestrator  {snapshot['orchestrator']}",
        f"news-monitor  {snapshot['news_monitor']}",
        f"symbol        {snapshot['symbol']}",
        f"monitored     {', '.join(snapshot.get('monitored_symbols') or [])}",
        f"price         {_fmt_number(snapshot.get('current_price'))}",
        "",
        "$ balance",
        f"wallet        {snapshot['wallet']} usdt",
        f"available     {snapshot['available']} usdt",
        f"uPnL          {snapshot['upnl']} usdt",
        "",
        "$ positions",
    ]

    positions = snapshot.get("positions") or []
    if positions:
        for position in positions:
            lines.append(
                f"{position['symbol']} {position['side']:<5}  "
                f"qty {_fmt_number(position['qty'])}  "
                f"entry {_fmt_number(position['entry'])}  "
                f"mark {_fmt_number(position['mark'])}  "
                f"pnl {_fmt_number(position['pnl'])}"
            )
    else:
        lines.append("no open positions")

    lines.extend(["", "$ signals"])
    for signal in snapshot.get("signals") or []:
        lines.append(
            f"{signal['symbol']:<8} "
            f"{signal['timeframe']:<3} "
            f"{str(signal['bias']).lower():<7}  "
            f"entry {_fmt_number(signal['entry'])}  "
            f"sl {_fmt_number(signal['sl'])}  "
            f"tp1 {_fmt_number(signal['tp1'])}"
        )

    return "\n".join(lines)


def run_terminal_dashboard(symbol: str = "BTCUSDT", *, watch: bool = False, refresh_seconds: float = 5.0) -> None:
    while True:
        snapshot = build_dashboard_snapshot(symbol)
        print(render_terminal_dashboard(snapshot))
        if not watch:
            return
        time.sleep(refresh_seconds)
        print("\033[2J\033[H", end="")
