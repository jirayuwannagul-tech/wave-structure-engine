from __future__ import annotations

import argparse
import json

from analysis.trade_backtest_runner import run_trade_backtest_suite
from config.settings import load_env_file
from services.binance_price_service import get_last_price
from services.google_sheets_sync import GoogleSheetsSignalLogger, safe_sync_signal
from services.news_rss_monitor import run_news_monitor
from services.terminal_dashboard import run_terminal_dashboard
from services.web_dashboard import run_web_dashboard
from services.trading_orchestrator import _load_runtime, render_runtime_snapshot, run_orchestrator
from storage.wave_repository import WaveRepository


TIMEFRAME_CONFIG = {
    "1D": ("data/BTCUSDT_1d.csv", 120),
    "1W": ("data/BTCUSDT_1w.csv", 80),
    "4H": ("data/BTCUSDT_4h.csv", 150),
}


def _resolve_timeframes(timeframes: list[str] | None) -> list[str]:
    if not timeframes:
        return ["1D", "1W", "4H"]

    normalized = [timeframe.upper() for timeframe in timeframes]
    invalid = [timeframe for timeframe in normalized if timeframe not in TIMEFRAME_CONFIG]
    if invalid:
        raise ValueError(f"Unsupported timeframe(s): {', '.join(invalid)}")
    return normalized


def _run_dry_run(symbol: str) -> None:
    runtime = _load_runtime(symbol)
    repository = WaveRepository()
    sheets_logger = GoogleSheetsSignalLogger.from_env()
    try:
        current_price = get_last_price(symbol)
    except Exception:
        current_price = None

    signal_ids = repository.sync_runtime(runtime, current_price=current_price)
    for signal_id in signal_ids:
        safe_sync_signal(repository.fetch_signal(signal_id), sheets_logger)
    print(render_runtime_snapshot(runtime, current_price=current_price))


def _run_trade_backtest(
    symbol: str,
    timeframes: list[str],
    step: int,
    fee_bps: float,
    slippage_bps: float,
) -> None:
    fee_rate = fee_bps / 10_000.0
    slippage_rate = slippage_bps / 10_000.0
    output: dict[str, dict] = {}

    for timeframe in _resolve_timeframes(timeframes):
        csv_path, min_window = TIMEFRAME_CONFIG[timeframe]
        suite = run_trade_backtest_suite(
            csv_path=csv_path,
            timeframe=timeframe,
            min_window=min_window,
            step=step,
            symbol=symbol,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
        )
        output[timeframe] = {target: result["summary"] for target, result in suite.items()}

    print(json.dumps(output, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic Elliott Wave Engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    orchestrator_parser = subparsers.add_parser("orchestrator", help="Run live monitor/orchestrator")
    orchestrator_parser.add_argument("--symbol", default="BTCUSDT")
    orchestrator_parser.add_argument("--poll-interval", type=float, default=5.0)
    orchestrator_parser.add_argument("--once", action="store_true")

    dry_run_parser = subparsers.add_parser("dry-run", help="Print current live snapshot")
    dry_run_parser.add_argument("--symbol", default="BTCUSDT")

    backtest_parser = subparsers.add_parser("trade-backtest", help="Run trade backtest on local BTC datasets")
    backtest_parser.add_argument("--symbol", default="BTCUSDT")
    backtest_parser.add_argument("--timeframes", nargs="*", default=["1D", "1W", "4H"])
    backtest_parser.add_argument("--step", type=int, default=1)
    backtest_parser.add_argument("--fee-bps", type=float, default=4.0)
    backtest_parser.add_argument("--slippage-bps", type=float, default=2.0)

    news_parser = subparsers.add_parser("news-monitor", help="Run BTC RSS news context monitor")
    news_parser.add_argument("--once", action="store_true")

    dashboard_parser = subparsers.add_parser("terminal-dashboard", help="Render read-only terminal dashboard")
    dashboard_parser.add_argument("--symbol", default="BTCUSDT")
    dashboard_parser.add_argument("--watch", action="store_true")
    dashboard_parser.add_argument("--refresh-seconds", type=float, default=5.0)

    web_dashboard_parser = subparsers.add_parser("web-dashboard", help="Run read-only web dashboard")
    web_dashboard_parser.add_argument("--symbol", default="BTCUSDT")
    web_dashboard_parser.add_argument("--host", default="127.0.0.1")
    web_dashboard_parser.add_argument("--port", type=int, default=8080)
    web_dashboard_parser.add_argument("--refresh-seconds", type=float, default=5.0)

    return parser


def main() -> None:
    load_env_file()
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "orchestrator":
        run_orchestrator(
            symbol=args.symbol,
            poll_interval=args.poll_interval,
            once=args.once,
            sheets_logger=GoogleSheetsSignalLogger.from_env(),
        )
        return

    if args.command == "dry-run":
        _run_dry_run(args.symbol)
        return

    if args.command == "trade-backtest":
        _run_trade_backtest(
            symbol=args.symbol,
            timeframes=args.timeframes,
            step=args.step,
            fee_bps=args.fee_bps,
            slippage_bps=args.slippage_bps,
        )
        return

    if args.command == "news-monitor":
        run_news_monitor(
            once=args.once,
        )
        return

    if args.command == "terminal-dashboard":
        run_terminal_dashboard(
            symbol=args.symbol,
            watch=args.watch,
            refresh_seconds=args.refresh_seconds,
        )
        return

    if args.command == "web-dashboard":
        run_web_dashboard(
            symbol=args.symbol,
            host=args.host,
            port=args.port,
            refresh_seconds=args.refresh_seconds,
        )
        return

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
