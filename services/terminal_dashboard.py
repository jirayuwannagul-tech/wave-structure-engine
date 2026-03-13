from __future__ import annotations

import subprocess
import time
from typing import Any

from execution.binance_futures_client import BinanceFuturesClient
from execution.settings import load_execution_config
from services.binance_price_service import get_last_price
from services.trading_orchestrator import _load_runtime, _select_display_scenario


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


def _build_signals(runtime) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for analysis in runtime.analyses:
        scenarios = analysis.get("scenarios") or []
        scenario, _ = _select_display_scenario(scenarios, analysis.get("current_price"))
        targets = list(getattr(scenario, "targets", []) or [])
        tp1 = targets[0] if len(targets) >= 1 else None
        signals.append(
            {
                "timeframe": analysis.get("timeframe"),
                "bias": getattr(scenario, "bias", None) or "NONE",
                "entry": getattr(scenario, "confirmation", None),
                "sl": getattr(scenario, "stop_loss", None),
                "tp1": tp1,
            }
        )
    return signals


def build_dashboard_snapshot(symbol: str = "BTCUSDT") -> dict[str, Any]:
    config = load_execution_config()
    client = BinanceFuturesClient(config)
    runtime = _load_runtime(symbol)
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
        "wallet": _fmt_number((usdt_balance or {}).get("balance")),
        "available": _fmt_number((usdt_balance or {}).get("availableBalance")),
        "upnl": _fmt_number((usdt_balance or {}).get("crossUnPnl")),
        "positions": open_positions,
        "signals": _build_signals(runtime),
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
