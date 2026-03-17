from __future__ import annotations

import argparse
import json
import os
from datetime import timedelta

import pandas as pd
from analysis.portfolio_backtest import (
    build_trade_candidates,
    run_global_portfolio_backtest,
    run_portfolio_backtest,
)
from analysis.system_kpi import compute_system_kpis, write_system_kpi_report
from analysis.trade_backtest_runner import run_trade_backtest_suite
from config.markets import get_default_monitor_symbols
from config.settings import load_env_file
from data.market_data_fetcher import MarketDataFetcher
from execution.settings import load_execution_config
from services.binance_price_service import get_last_price
from services.google_sheets_sync import GoogleSheetsSignalLogger, safe_sync_signal
from services.market_data_sync import sync_market_data
from services.news_rss_monitor import run_news_monitor
from services.terminal_dashboard import run_terminal_dashboard
from services.wave_overlay_chart import build_wave_overlay_svg
from services.web_dashboard import run_web_dashboard
from services.trading_orchestrator import _load_runtime, render_runtime_snapshot, run_orchestrator
from storage.experience_store import build_experience_payload, save_experience_store
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


def _resolve_symbols(symbol: str | None = None, symbols: list[str] | None = None) -> list[str]:
    if symbols:
        resolved = [item.strip().upper() for item in symbols if item and item.strip()]
    elif symbol:
        resolved = [symbol.strip().upper()]
    else:
        resolved = get_default_monitor_symbols()

    unique_symbols: list[str] = []
    seen: set[str] = set()
    for item in resolved:
        if item not in seen:
            seen.add(item)
            unique_symbols.append(item)
    return unique_symbols


def _dataset_path(symbol: str, timeframe: str) -> str:
    interval = timeframe.lower()
    return f"data/{symbol.upper()}_{interval}.csv"


def _fetch_backtest_dataset(
    symbol: str,
    timeframe: str,
    limit: int = 500,
    years: int | None = None,
) -> str:
    interval = timeframe.lower()
    fetcher = MarketDataFetcher(symbol=symbol, interval=interval, limit=limit)
    if years and years > 0:
        end_time = pd.Timestamp.now(tz="UTC")
        start_time = end_time - timedelta(days=365 * years)
        df = fetcher.fetch_ohlcv_range(start_time=start_time, end_time=end_time)
    else:
        df = fetcher.fetch_ohlcv()
    path = _dataset_path(symbol, timeframe)
    fetcher.save_to_csv(df, path)
    return path


def _resolve_backtest_dataset(
    symbol: str,
    timeframe: str,
    refresh_data: bool = False,
    limit: int = 500,
    years: int | None = None,
) -> str:
    path = _dataset_path(symbol, timeframe)
    if refresh_data or not os.path.exists(path):
        return _fetch_backtest_dataset(symbol, timeframe, limit=limit, years=years)
    return path


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


def _run_market_data_sync(
    symbols: list[str],
    timeframes: list[str],
    years: int = 8,
) -> None:
    start_time = pd.Timestamp.now(tz="UTC") - timedelta(days=365 * years)
    summary = sync_market_data(
        symbols=symbols,
        timeframes=timeframes,
        repository=WaveRepository(),
        start_time=start_time,
    )
    print(json.dumps(summary, indent=2))


def _run_wave_overlay_chart(symbol: str, output: str | None = None) -> None:
    path = build_wave_overlay_svg(symbol=symbol, output_path=output)
    print(json.dumps({"symbol": symbol.upper(), "output_path": str(path)}, indent=2))


def _run_system_kpi(
    symbols: list[str],
    analysis_timeframes: list[str],
    data_timeframes: list[str],
    output: str | None = None,
) -> None:
    report = compute_system_kpis(
        symbols=symbols,
        analysis_timeframes=analysis_timeframes,
        data_timeframes=data_timeframes,
    )
    output_path = write_system_kpi_report(report, output_path=output)
    payload = {
        **report,
        "output_path": str(output_path),
    }
    print(json.dumps(payload, indent=2))


def _run_trade_backtest(
    symbols: list[str],
    timeframes: list[str],
    step: int,
    fee_bps: float,
    slippage_bps: float,
    refresh_data: bool = False,
    fetch_limit: int = 500,
    years: int | None = None,
) -> None:
    fee_rate = fee_bps / 10_000.0
    slippage_rate = slippage_bps / 10_000.0
    output: dict[str, dict] = {}

    for symbol in symbols:
        symbol_output: dict[str, dict] = {}
        for timeframe in _resolve_timeframes(timeframes):
            _, min_window = TIMEFRAME_CONFIG[timeframe]
            csv_path = _resolve_backtest_dataset(
                symbol=symbol,
                timeframe=timeframe,
                refresh_data=refresh_data,
                limit=fetch_limit,
                years=years,
            )
            higher_timeframe_csv_path = None
            higher_timeframe_min_window = None
            parent_timeframe_csv_path = None
            parent_timeframe_min_window = None
            if timeframe.upper() == "1D":
                _, parent_timeframe_min_window = TIMEFRAME_CONFIG["1W"]
                parent_timeframe_csv_path = _resolve_backtest_dataset(
                    symbol=symbol,
                    timeframe="1W",
                    refresh_data=refresh_data,
                    limit=fetch_limit,
                    years=years,
                )
            if timeframe.upper() == "4H":
                _, higher_timeframe_min_window = TIMEFRAME_CONFIG["1D"]
                higher_timeframe_csv_path = _resolve_backtest_dataset(
                    symbol=symbol,
                    timeframe="1D",
                    refresh_data=refresh_data,
                    limit=fetch_limit,
                    years=years,
                )
                _, parent_timeframe_min_window = TIMEFRAME_CONFIG["1W"]
                parent_timeframe_csv_path = _resolve_backtest_dataset(
                    symbol=symbol,
                    timeframe="1W",
                    refresh_data=refresh_data,
                    limit=fetch_limit,
                    years=years,
                )
            suite = run_trade_backtest_suite(
                csv_path=csv_path,
                timeframe=timeframe,
                min_window=min_window,
                step=step,
                symbol=symbol,
                fee_rate=fee_rate,
                slippage_rate=slippage_rate,
                higher_timeframe_csv_path=higher_timeframe_csv_path,
                higher_timeframe_min_window=higher_timeframe_min_window,
                parent_timeframe_csv_path=parent_timeframe_csv_path,
                parent_timeframe_min_window=parent_timeframe_min_window,
            )
            symbol_output[timeframe] = {target: result["summary"] for target, result in suite.items()}
        output[symbol] = symbol_output

    print(json.dumps(output, indent=2))


def _run_portfolio_backtest(
    symbols: list[str],
    timeframes: list[str],
    step: int,
    fee_bps: float,
    slippage_bps: float,
    refresh_data: bool = False,
    fetch_limit: int = 500,
    years: int | None = None,
    initial_capital: float = 1000.0,
    risk_per_trade: float | None = None,
    max_concurrent: int = 1,
) -> None:
    fee_rate = fee_bps / 10_000.0
    slippage_rate = slippage_bps / 10_000.0
    execution_config = load_execution_config()
    tp_allocations = (
        float(execution_config.tp1_size_pct),
        float(execution_config.tp2_size_pct),
        float(execution_config.tp3_size_pct),
    )
    resolved_risk = float(execution_config.risk_per_trade if risk_per_trade is None else risk_per_trade)

    output: dict[str, dict] = {}
    for symbol in symbols:
        symbol_output: dict[str, dict] = {}
        for timeframe in _resolve_timeframes(timeframes):
            _, min_window = TIMEFRAME_CONFIG[timeframe]
            csv_path = _resolve_backtest_dataset(
                symbol=symbol,
                timeframe=timeframe,
                refresh_data=refresh_data,
                limit=fetch_limit,
                years=years,
            )
            higher_timeframe_csv_path = None
            higher_timeframe_min_window = None
            parent_timeframe_csv_path = None
            parent_timeframe_min_window = None
            if timeframe.upper() == "1D":
                _, parent_timeframe_min_window = TIMEFRAME_CONFIG["1W"]
                parent_timeframe_csv_path = _resolve_backtest_dataset(
                    symbol=symbol,
                    timeframe="1W",
                    refresh_data=refresh_data,
                    limit=fetch_limit,
                    years=years,
                )
            if timeframe.upper() == "4H":
                _, higher_timeframe_min_window = TIMEFRAME_CONFIG["1D"]
                higher_timeframe_csv_path = _resolve_backtest_dataset(
                    symbol=symbol,
                    timeframe="1D",
                    refresh_data=refresh_data,
                    limit=fetch_limit,
                    years=years,
                )
                _, parent_timeframe_min_window = TIMEFRAME_CONFIG["1W"]
                parent_timeframe_csv_path = _resolve_backtest_dataset(
                    symbol=symbol,
                    timeframe="1W",
                    refresh_data=refresh_data,
                    limit=fetch_limit,
                    years=years,
                )
            result = run_portfolio_backtest(
                csv_path=csv_path,
                symbol=symbol,
                timeframe=timeframe,
                min_window=min_window,
                step=step,
                fee_rate=fee_rate,
                slippage_rate=slippage_rate,
                initial_capital=initial_capital,
                risk_per_trade=resolved_risk,
                max_concurrent=max_concurrent,
                tp_allocations=tp_allocations,
                higher_timeframe_csv_path=higher_timeframe_csv_path,
                higher_timeframe_min_window=higher_timeframe_min_window,
                parent_timeframe_csv_path=parent_timeframe_csv_path,
                parent_timeframe_min_window=parent_timeframe_min_window,
            )
            symbol_output[timeframe] = result["summary"]
        output[symbol] = symbol_output

    print(json.dumps(output, indent=2))


def _run_global_portfolio_backtest(
    symbols: list[str],
    timeframes: list[str],
    step: int,
    fee_bps: float,
    slippage_bps: float,
    refresh_data: bool = False,
    fetch_limit: int = 500,
    years: int | None = None,
    initial_capital: float = 1000.0,
    risk_per_trade: float | None = None,
    max_concurrent: int = 1,
) -> None:
    fee_rate = fee_bps / 10_000.0
    slippage_rate = slippage_bps / 10_000.0
    execution_config = load_execution_config()
    tp_allocations = (
        float(execution_config.tp1_size_pct),
        float(execution_config.tp2_size_pct),
        float(execution_config.tp3_size_pct),
    )
    resolved_risk = float(execution_config.risk_per_trade if risk_per_trade is None else risk_per_trade)

    datasets: list[dict] = []
    for symbol in symbols:
        for timeframe in _resolve_timeframes(timeframes):
            _, min_window = TIMEFRAME_CONFIG[timeframe]
            csv_path = _resolve_backtest_dataset(
                symbol=symbol,
                timeframe=timeframe,
                refresh_data=refresh_data,
                limit=fetch_limit,
                years=years,
            )
            datasets.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "csv_path": csv_path,
                    "min_window": min_window,
                    "step": step,
                    "higher_timeframe_csv_path": (
                        _resolve_backtest_dataset(
                            symbol=symbol,
                            timeframe="1D",
                            refresh_data=refresh_data,
                            limit=fetch_limit,
                            years=years,
                        )
                        if timeframe.upper() == "4H"
                        else None
                    ),
                    "higher_timeframe_min_window": (
                        TIMEFRAME_CONFIG["1D"][1]
                        if timeframe.upper() == "4H"
                        else None
                    ),
                    "parent_timeframe_csv_path": (
                        _resolve_backtest_dataset(
                            symbol=symbol,
                            timeframe="1W",
                            refresh_data=refresh_data,
                            limit=fetch_limit,
                            years=years,
                        )
                        if timeframe.upper() in {"1D", "4H"}
                        else None
                    ),
                    "parent_timeframe_min_window": (
                        TIMEFRAME_CONFIG["1W"][1]
                        if timeframe.upper() in {"1D", "4H"}
                        else None
                    ),
                }
            )

    result = run_global_portfolio_backtest(
        datasets=datasets,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        initial_capital=initial_capital,
        risk_per_trade=resolved_risk,
        max_concurrent=max_concurrent,
        tp_allocations=tp_allocations,
    )
    print(json.dumps(result, indent=2))


def _refresh_experience_store(
    symbols: list[str],
    timeframes: list[str],
    step: int,
    fee_bps: float,
    slippage_bps: float,
    refresh_data: bool = False,
    fetch_limit: int = 500,
    years: int | None = None,
) -> None:
    fee_rate = fee_bps / 10_000.0
    slippage_rate = slippage_bps / 10_000.0
    execution_config = load_execution_config()
    tp_allocations = (
        float(execution_config.tp1_size_pct),
        float(execution_config.tp2_size_pct),
        float(execution_config.tp3_size_pct),
    )

    records: list[dict] = []
    by_symbol_timeframe: dict[str, dict] = {}
    previous_enabled = os.getenv("EXPERIENCE_STORE_ENABLED")
    os.environ["EXPERIENCE_STORE_ENABLED"] = "false"

    try:
        for symbol in symbols:
            for timeframe in _resolve_timeframes(timeframes):
                _, min_window = TIMEFRAME_CONFIG[timeframe]
                csv_path = _resolve_backtest_dataset(
                    symbol=symbol,
                    timeframe=timeframe,
                    refresh_data=refresh_data,
                    limit=fetch_limit,
                    years=years,
                )
                higher_timeframe_csv_path = None
                higher_timeframe_min_window = None
                parent_timeframe_csv_path = None
                parent_timeframe_min_window = None
                if timeframe.upper() == "1D":
                    _, parent_timeframe_min_window = TIMEFRAME_CONFIG["1W"]
                    parent_timeframe_csv_path = _resolve_backtest_dataset(
                        symbol=symbol,
                        timeframe="1W",
                        refresh_data=refresh_data,
                        limit=fetch_limit,
                        years=years,
                    )
                if timeframe.upper() == "4H":
                    _, higher_timeframe_min_window = TIMEFRAME_CONFIG["1D"]
                    higher_timeframe_csv_path = _resolve_backtest_dataset(
                        symbol=symbol,
                        timeframe="1D",
                        refresh_data=refresh_data,
                        limit=fetch_limit,
                        years=years,
                    )
                    _, parent_timeframe_min_window = TIMEFRAME_CONFIG["1W"]
                    parent_timeframe_csv_path = _resolve_backtest_dataset(
                        symbol=symbol,
                        timeframe="1W",
                        refresh_data=refresh_data,
                        limit=fetch_limit,
                        years=years,
                    )

                result = build_trade_candidates(
                    csv_path=csv_path,
                    symbol=symbol,
                    timeframe=timeframe,
                    min_window=min_window,
                    step=step,
                    fee_rate=fee_rate,
                    slippage_rate=slippage_rate,
                    tp_allocations=tp_allocations,
                    higher_timeframe_csv_path=higher_timeframe_csv_path,
                    higher_timeframe_min_window=higher_timeframe_min_window,
                    parent_timeframe_csv_path=parent_timeframe_csv_path,
                    parent_timeframe_min_window=parent_timeframe_min_window,
                    use_all_scenarios=True,
                )

                key = f"{symbol.upper()}:{timeframe.upper()}"
                by_symbol_timeframe[key] = result["summary"]
                records.extend(
                    {
                        "symbol": candidate["symbol"],
                        "timeframe": candidate["timeframe"],
                        "pattern": candidate["structure"] or "UNKNOWN",
                        "scenario_name": candidate.get("scenario_name"),
                        "side": candidate["side"],
                        "reward_r": candidate["reward_r"],
                    }
                    for candidate in result["candidates"]
                )
    finally:
        if previous_enabled is None:
            os.environ.pop("EXPERIENCE_STORE_ENABLED", None)
        else:
            os.environ["EXPERIENCE_STORE_ENABLED"] = previous_enabled

    payload = build_experience_payload(records)
    path = save_experience_store(payload)
    summary = {
        "experience_store_path": str(path),
        "record_count": len(records),
        "pattern_edges": len(payload.get("patterns") or {}),
        "by_symbol_timeframe": by_symbol_timeframe,
    }
    print(json.dumps(summary, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic Elliott Wave Engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    orchestrator_parser = subparsers.add_parser("orchestrator", help="Run live monitor/orchestrator")
    orchestrator_parser.add_argument("--symbol", default="BTCUSDT")
    orchestrator_parser.add_argument("--symbols", nargs="*")
    orchestrator_parser.add_argument("--poll-interval", type=float, default=5.0)
    orchestrator_parser.add_argument("--once", action="store_true")

    dry_run_parser = subparsers.add_parser("dry-run", help="Print current live snapshot")
    dry_run_parser.add_argument("--symbol", default="BTCUSDT")

    backtest_parser = subparsers.add_parser("trade-backtest", help="Run trade backtest on local BTC datasets")
    backtest_parser.add_argument("--symbol", default="BTCUSDT")
    backtest_parser.add_argument("--symbols", nargs="*")
    backtest_parser.add_argument("--timeframes", nargs="*", default=["1D", "1W", "4H"])
    backtest_parser.add_argument("--step", type=int, default=1)
    backtest_parser.add_argument("--fee-bps", type=float, default=4.0)
    backtest_parser.add_argument("--slippage-bps", type=float, default=2.0)
    backtest_parser.add_argument("--refresh-data", action="store_true")
    backtest_parser.add_argument("--fetch-limit", type=int, default=500)
    backtest_parser.add_argument("--years", type=int, default=2)

    portfolio_parser = subparsers.add_parser(
        "portfolio-backtest",
        help="Run realistic portfolio backtest with split targets and compounding",
    )
    portfolio_parser.add_argument("--symbol", default="BTCUSDT")
    portfolio_parser.add_argument("--symbols", nargs="*")
    portfolio_parser.add_argument("--timeframes", nargs="*", default=["1D", "4H"])
    portfolio_parser.add_argument("--step", type=int, default=1)
    portfolio_parser.add_argument("--fee-bps", type=float, default=4.0)
    portfolio_parser.add_argument("--slippage-bps", type=float, default=2.0)
    portfolio_parser.add_argument("--refresh-data", action="store_true")
    portfolio_parser.add_argument("--fetch-limit", type=int, default=500)
    portfolio_parser.add_argument("--years", type=int, default=2)
    portfolio_parser.add_argument("--initial-capital", type=float, default=1000.0)
    portfolio_parser.add_argument("--risk-per-trade", type=float)
    portfolio_parser.add_argument("--max-concurrent", type=int, default=1)

    global_portfolio_parser = subparsers.add_parser(
        "global-portfolio-backtest",
        help="Run shared-balance portfolio backtest across all symbols/timeframes",
    )
    global_portfolio_parser.add_argument("--symbol", default="BTCUSDT")
    global_portfolio_parser.add_argument("--symbols", nargs="*")
    global_portfolio_parser.add_argument("--timeframes", nargs="*", default=["1D", "4H"])
    global_portfolio_parser.add_argument("--step", type=int, default=1)
    global_portfolio_parser.add_argument("--fee-bps", type=float, default=4.0)
    global_portfolio_parser.add_argument("--slippage-bps", type=float, default=2.0)
    global_portfolio_parser.add_argument("--refresh-data", action="store_true")
    global_portfolio_parser.add_argument("--fetch-limit", type=int, default=500)
    global_portfolio_parser.add_argument("--years", type=int, default=2)
    global_portfolio_parser.add_argument("--initial-capital", type=float, default=1000.0)
    global_portfolio_parser.add_argument("--risk-per-trade", type=float)
    global_portfolio_parser.add_argument("--max-concurrent", type=int, default=1)

    experience_parser = subparsers.add_parser(
        "refresh-experience-store",
        help="Build pattern win/loss experience store from historical trade candidates",
    )
    experience_parser.add_argument("--symbol", default="BTCUSDT")
    experience_parser.add_argument("--symbols", nargs="*")
    experience_parser.add_argument("--timeframes", nargs="*", default=["1D", "4H"])
    experience_parser.add_argument("--step", type=int, default=10)
    experience_parser.add_argument("--fee-bps", type=float, default=4.0)
    experience_parser.add_argument("--slippage-bps", type=float, default=2.0)
    experience_parser.add_argument("--refresh-data", action="store_true")
    experience_parser.add_argument("--fetch-limit", type=int, default=500)
    experience_parser.add_argument("--years", type=int, default=2)

    news_parser = subparsers.add_parser("news-monitor", help="Run BTC RSS news context monitor")
    news_parser.add_argument("--once", action="store_true")

    market_data_parser = subparsers.add_parser(
        "sync-market-data",
        help="Backfill and persist market candles to CSV and SQLite",
    )
    market_data_parser.add_argument("--symbol", default="BTCUSDT")
    market_data_parser.add_argument("--symbols", nargs="*")
    market_data_parser.add_argument("--timeframes", nargs="*", default=["1W", "1D", "4H"])
    market_data_parser.add_argument("--years", type=int, default=8)

    wave_overlay_parser = subparsers.add_parser(
        "wave-overlay-chart",
        help="Render a single SVG with 1D wave and 4H sub-wave overlay",
    )
    wave_overlay_parser.add_argument("--symbol", default="BTCUSDT")
    wave_overlay_parser.add_argument("--output")

    system_kpi_parser = subparsers.add_parser(
        "system-kpi",
        help="Compute local KPI report for data, wave counting, and entry quality",
    )
    system_kpi_parser.add_argument("--symbol", default="BTCUSDT")
    system_kpi_parser.add_argument("--symbols", nargs="*")
    system_kpi_parser.add_argument("--analysis-timeframes", nargs="*", default=["1D", "4H"])
    system_kpi_parser.add_argument("--data-timeframes", nargs="*", default=["1W", "1D", "4H"])
    system_kpi_parser.add_argument("--output")

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
            symbols=_resolve_symbols(args.symbol, args.symbols),
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
            symbols=_resolve_symbols(args.symbol, args.symbols),
            timeframes=args.timeframes,
            step=args.step,
            fee_bps=args.fee_bps,
            slippage_bps=args.slippage_bps,
            refresh_data=args.refresh_data,
            fetch_limit=args.fetch_limit,
            years=args.years,
        )
        return

    if args.command == "portfolio-backtest":
        _run_portfolio_backtest(
            symbols=_resolve_symbols(args.symbol, args.symbols),
            timeframes=args.timeframes,
            step=args.step,
            fee_bps=args.fee_bps,
            slippage_bps=args.slippage_bps,
            refresh_data=args.refresh_data,
            fetch_limit=args.fetch_limit,
            years=args.years,
            initial_capital=args.initial_capital,
            risk_per_trade=args.risk_per_trade,
            max_concurrent=args.max_concurrent,
        )
        return

    if args.command == "global-portfolio-backtest":
        _run_global_portfolio_backtest(
            symbols=_resolve_symbols(args.symbol, args.symbols),
            timeframes=args.timeframes,
            step=args.step,
            fee_bps=args.fee_bps,
            slippage_bps=args.slippage_bps,
            refresh_data=args.refresh_data,
            fetch_limit=args.fetch_limit,
            years=args.years,
            initial_capital=args.initial_capital,
            risk_per_trade=args.risk_per_trade,
            max_concurrent=args.max_concurrent,
        )
        return

    if args.command == "refresh-experience-store":
        _refresh_experience_store(
            symbols=_resolve_symbols(args.symbol, args.symbols),
            timeframes=args.timeframes,
            step=args.step,
            fee_bps=args.fee_bps,
            slippage_bps=args.slippage_bps,
            refresh_data=args.refresh_data,
            fetch_limit=args.fetch_limit,
            years=args.years,
        )
        return

    if args.command == "sync-market-data":
        _run_market_data_sync(
            symbols=_resolve_symbols(args.symbol, args.symbols),
            timeframes=args.timeframes,
            years=args.years,
        )
        return

    if args.command == "wave-overlay-chart":
        _run_wave_overlay_chart(
            symbol=args.symbol,
            output=args.output,
        )
        return

    if args.command == "system-kpi":
        _run_system_kpi(
            symbols=_resolve_symbols(args.symbol, args.symbols),
            analysis_timeframes=args.analysis_timeframes,
            data_timeframes=args.data_timeframes,
            output=args.output,
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
