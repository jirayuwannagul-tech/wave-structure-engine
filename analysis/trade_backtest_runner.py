from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from analysis.backtest_timeframe_context import resolve_backtest_higher_timeframe_context
from analysis.trade_backtest import (
    build_trade_setup_from_scenario,
    simulate_trade_from_setup,
)
from analysis.setup_filter import apply_trade_filters
from core.engine import build_dataframe_analysis


@dataclass
class TradeBacktestSummary:
    timeframe: str
    target_label: str
    fee_bps: float
    slippage_bps: float
    total_windows: int
    analyzed_cases: int
    setups_built: int
    valid_target_setups: int
    triggered_trades: int
    no_trigger_trades: int
    invalid_setups: int
    tp_hits: int
    stop_losses: int
    open_trades: int
    win_rate: float
    expectancy_r: float
    avg_r: float


def _summarize_results(
    timeframe: str,
    target_label: str,
    fee_rate: float,
    slippage_rate: float,
    total_windows: int,
    analyzed_cases: int,
    setups_built: int,
    results: list[dict],
) -> TradeBacktestSummary:
    valid_target_setups = sum(1 for r in results if r["outcome"] != "INVALID")
    triggered_trades = sum(
        1 for r in results if r["outcome"] in {target_label, "STOP_LOSS", "OPEN"}
    )
    no_trigger_trades = sum(1 for r in results if r["outcome"] == "NO_TRIGGER")
    invalid_setups = sum(1 for r in results if r["outcome"] == "INVALID")
    tp_hits = sum(1 for r in results if r["outcome"] == target_label)
    stop_losses = sum(1 for r in results if r["outcome"] == "STOP_LOSS")
    open_trades = sum(1 for r in results if r["outcome"] == "OPEN")

    closed_results = [r for r in results if r["outcome"] in {target_label, "STOP_LOSS"}]
    closed_count = len(closed_results)
    win_rate = (tp_hits / closed_count) if closed_count else 0.0
    expectancy_r = (
        sum(float(r["reward_r"]) for r in closed_results) / closed_count
        if closed_count
        else 0.0
    )
    avg_r = (
        sum(float(r["reward_r"]) for r in results if r["outcome"] != "INVALID")
        / max(1, len([r for r in results if r["outcome"] != "INVALID"]))
    )

    return TradeBacktestSummary(
        timeframe=timeframe,
        target_label=target_label,
        fee_bps=round(fee_rate * 10_000, 3),
        slippage_bps=round(slippage_rate * 10_000, 3),
        total_windows=total_windows,
        analyzed_cases=analyzed_cases,
        setups_built=setups_built,
        valid_target_setups=valid_target_setups,
        triggered_trades=triggered_trades,
        no_trigger_trades=no_trigger_trades,
        invalid_setups=invalid_setups,
        tp_hits=tp_hits,
        stop_losses=stop_losses,
        open_trades=open_trades,
        win_rate=round(win_rate, 3),
        expectancy_r=round(expectancy_r, 3),
        avg_r=round(avg_r, 3),
    )


def run_trade_backtest(
    csv_path: str,
    timeframe: str,
    min_window: int,
    step: int = 1,
    target_label: str = "TP1",
    symbol: str = "BTCUSDT",
    fee_rate: float = 0.0,
    slippage_rate: float = 0.0,
    higher_timeframe_csv_path: str | None = None,
    higher_timeframe_min_window: int | None = None,
    parent_timeframe_csv_path: str | None = None,
    parent_timeframe_min_window: int | None = None,
) -> dict:
    df = pd.read_csv(csv_path).copy()

    if "open_time" in df.columns:
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True, errors="coerce")

    higher_timeframe_df = None
    if higher_timeframe_csv_path:
        higher_timeframe_df = pd.read_csv(higher_timeframe_csv_path).copy()
        if "open_time" in higher_timeframe_df.columns:
            higher_timeframe_df["open_time"] = pd.to_datetime(
                higher_timeframe_df["open_time"],
                utc=True,
                errors="coerce",
            )

    parent_timeframe_df = None
    if parent_timeframe_csv_path:
        parent_timeframe_df = pd.read_csv(parent_timeframe_csv_path).copy()
        if "open_time" in parent_timeframe_df.columns:
            parent_timeframe_df["open_time"] = pd.to_datetime(
                parent_timeframe_df["open_time"],
                utc=True,
                errors="coerce",
            )

    results: list[dict] = []
    total_windows = 0
    analyzed_cases = 0
    setups_built = 0

    for end_idx in range(min_window, len(df) - 1, step):
        total_windows += 1
        sample_df = df.iloc[:end_idx].copy()
        future_df = df.iloc[end_idx:].copy()

        analysis = build_dataframe_analysis(
            symbol=symbol,
            timeframe=timeframe,
            df=sample_df,
            current_price=float(sample_df.iloc[-1]["close"]),
        )
        higher_timeframe_bias, higher_timeframe_context, allow_analysis = (
            resolve_backtest_higher_timeframe_context(
                symbol=symbol,
                timeframe=timeframe,
                sample_df=sample_df,
                higher_timeframe_df=higher_timeframe_df,
                higher_timeframe_min_window=higher_timeframe_min_window,
                parent_timeframe_df=parent_timeframe_df,
                parent_timeframe_min_window=parent_timeframe_min_window,
            )
        )
        if not allow_analysis:
            continue

        analysis = apply_trade_filters(
            analysis,
            higher_timeframe_bias=higher_timeframe_bias,
            higher_timeframe_context=higher_timeframe_context,
        )

        if not analysis.get("has_pattern"):
            continue

        analyzed_cases += 1
        scenarios = analysis.get("scenarios") or []
        if not scenarios:
            continue

        main_scenario = scenarios[0]
        setup = build_trade_setup_from_scenario(main_scenario)
        if setup is None:
            results.append(
                {
                    "end_idx": end_idx,
                    "outcome": "INVALID",
                    "reward_r": 0.0,
                    "structure": analysis.get("primary_pattern_type"),
                    "bias": getattr(main_scenario, "bias", None),
                }
            )
            continue

        setups_built += 1
        trade_result = simulate_trade_from_setup(
            future_df,
            setup,
            target_label=target_label,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
        )

        results.append(
            {
                "end_idx": end_idx,
                "outcome": trade_result.outcome,
                "reward_r": trade_result.reward_r,
                "entry_index": trade_result.entry_index,
                "exit_index": trade_result.exit_index,
                "entry_price": trade_result.entry_price,
                "exit_price": trade_result.exit_price,
                "gross_pnl_per_unit": trade_result.gross_pnl_per_unit,
                "net_pnl_per_unit": trade_result.net_pnl_per_unit,
                "fee_paid_per_unit": trade_result.fee_paid_per_unit,
                "structure": analysis.get("primary_pattern_type"),
                "bias": getattr(main_scenario, "bias", None),
            }
        )

    summary = _summarize_results(
        timeframe=timeframe.upper(),
        target_label=target_label.upper(),
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        total_windows=total_windows,
        analyzed_cases=analyzed_cases,
        setups_built=setups_built,
        results=results,
    )

    return {
        "summary": asdict(summary),
        "trades": results,
    }


def run_trade_backtest_suite(
    csv_path: str,
    timeframe: str,
    min_window: int,
    step: int = 1,
    symbol: str = "BTCUSDT",
    fee_rate: float = 0.0,
    slippage_rate: float = 0.0,
    higher_timeframe_csv_path: str | None = None,
    higher_timeframe_min_window: int | None = None,
    parent_timeframe_csv_path: str | None = None,
    parent_timeframe_min_window: int | None = None,
) -> dict[str, dict]:
    output: dict[str, dict] = {}
    for target_label in ("TP1", "TP2", "TP3"):
        output[target_label] = run_trade_backtest(
            csv_path=csv_path,
            timeframe=timeframe,
            min_window=min_window,
            step=step,
            target_label=target_label,
            symbol=symbol,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
            higher_timeframe_csv_path=higher_timeframe_csv_path,
            higher_timeframe_min_window=higher_timeframe_min_window,
            parent_timeframe_csv_path=parent_timeframe_csv_path,
            parent_timeframe_min_window=parent_timeframe_min_window,
        )
    return output
