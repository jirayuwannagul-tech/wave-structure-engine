from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.portfolio_backtest import run_portfolio_backtest
from config.markets import DEFAULT_MONITOR_SYMBOLS
from core.engine import build_dataframe_analysis


DEFAULT_SYMBOLS = DEFAULT_MONITOR_SYMBOLS
DEFAULT_ANALYSIS_TIMEFRAMES = ("1D", "4H")
DEFAULT_DATA_TIMEFRAMES = ("1W", "1D", "4H")
GENERIC_STRUCTURES = {"UNKNOWN", "CORRECTION", "IMPULSE"}
BACKTEST_MIN_WINDOWS = {"1W": 80, "1D": 120, "4H": 150}
KPI_BACKTEST_STEP = 10
KPI_INITIAL_CAPITAL = 1000.0
KPI_RISK_PER_TRADE = 0.01
KPI_FEE_RATE = 0.0004
KPI_SLIPPAGE_RATE = 0.0002
KPI_TP_ALLOCATIONS = (0.4, 0.3, 0.3)
PROFITABILITY_PASS_THRESHOLD_PCT = 70.0
PROFITABILITY_STRONG_THRESHOLD_PCT = 80.0


@dataclass(frozen=True)
class MetricTarget:
    name: str
    description: str
    target_pct: float
    weight: float


SECTION_TARGETS: dict[str, dict[str, MetricTarget]] = {
    "data": {
        "dataset_coverage_pct": MetricTarget(
            name="Dataset Coverage",
            description="Required Binance candle datasets exist locally and are non-empty.",
            target_pct=90.0,
            weight=1.0,
        ),
    },
    "wave_counting": {
        "weekly_validation_accuracy_pct": MetricTarget(
            name="Weekly Validation Accuracy",
            description="Ground-truth 1W wave labels matched by the weekly validation suite.",
            target_pct=90.0,
            weight=0.45,
        ),
        "position_resolution_pct": MetricTarget(
            name="Position Resolution",
            description="1D/4H analyses resolve to a concrete wave position instead of UNKNOWN.",
            target_pct=90.0,
            weight=0.20,
        ),
        "structure_retention_pct": MetricTarget(
            name="Structure Retention",
            description="Detailed detected pattern subtype survives into the resolved position structure.",
            target_pct=90.0,
            weight=0.20,
        ),
        "projection_resolution_pct": MetricTarget(
            name="Projection Resolution",
            description="Projection layer returns a non-UNKNOWN next-structure expectation.",
            target_pct=90.0,
            weight=0.15,
        ),
    },
    "entry_pipeline": {
        "scenario_coverage_pct": MetricTarget(
            name="Scenario Coverage",
            description="Analyses that produce at least one scenario candidate.",
            target_pct=90.0,
            weight=0.35,
        ),
        "actionable_entry_pct": MetricTarget(
            name="Actionable Entry Rate",
            description="Analyses that produce at least one scenario with entry, stop, and targets.",
            target_pct=90.0,
            weight=0.35,
        ),
        "valid_entry_geometry_pct": MetricTarget(
            name="Valid Entry Geometry",
            description="Actionable scenarios whose entry, stop, and targets are on the correct side for their bias.",
            target_pct=95.0,
            weight=0.30,
        ),
    },
    "profitability": {
        "profitable_backtest_pct": MetricTarget(
            name="Profitable Backtest Rate",
            description="Symbol/timeframe backtests with positive net profit.",
            target_pct=70.0,
            weight=0.65,
        ),
        "positive_expectancy_pct": MetricTarget(
            name="Positive Expectancy Rate",
            description="Symbol/timeframe backtests with positive average R per trade.",
            target_pct=80.0,
            weight=0.35,
        ),
    },
}


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _dataset_path(symbol: str, timeframe: str) -> Path:
    return Path("data") / f"{symbol.upper()}_{timeframe.lower()}.csv"


def _load_dataframe(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "open_time" in df.columns:
        df["open_time"] = pd.to_datetime(df["open_time"])
    return df


def _safe_weekly_validation() -> dict[str, Any]:
    try:
        from tests.wave_validation_labels import run_validation

        result = run_validation(verbose=False)
        total = int(result.get("total", 0))
        passed = int(result.get("passed", 0))
        return {
            "total": total,
            "passed": passed,
            "accuracy_pct": round(_ratio(passed, total) * 100.0, 2),
            "status": "ok",
        }
    except Exception as exc:  # pragma: no cover - defensive path for local tooling
        return {
            "total": 0,
            "passed": 0,
            "accuracy_pct": 0.0,
            "status": "error",
            "error": str(exc),
        }


def _scenario_is_actionable(scenario) -> bool:
    return bool(
        scenario
        and getattr(scenario, "confirmation", None) is not None
        and getattr(scenario, "stop_loss", None) is not None
        and bool(getattr(scenario, "targets", None))
    )


def _scenario_has_valid_geometry(scenario) -> bool:
    if not _scenario_is_actionable(scenario):
        return False

    try:
        entry = float(scenario.confirmation)
        stop = float(scenario.stop_loss)
        targets = [float(target) for target in scenario.targets]
    except (TypeError, ValueError):
        return False

    bias = str(getattr(scenario, "bias", "")).upper()
    if bias == "BULLISH":
        return stop < entry and all(target > entry for target in targets)
    if bias == "BEARISH":
        return stop > entry and all(target < entry for target in targets)
    return False


def _structure_is_retained(primary_pattern_type: str | None, position_structure: str | None) -> bool:
    primary = (primary_pattern_type or "").upper()
    position = (position_structure or "").upper()

    if not primary or position == "UNKNOWN":
        return False
    if primary in GENERIC_STRUCTURES:
        return position != "UNKNOWN"
    return position == primary


def _build_backtest_context(symbol: str, timeframe: str) -> dict[str, Any]:
    timeframe = timeframe.upper()
    context = {
        "higher_timeframe_csv_path": None,
        "higher_timeframe_min_window": None,
        "parent_timeframe_csv_path": None,
        "parent_timeframe_min_window": None,
    }

    if timeframe == "1D":
        path = _dataset_path(symbol, "1W")
        if path.exists():
            context["parent_timeframe_csv_path"] = str(path)
            context["parent_timeframe_min_window"] = BACKTEST_MIN_WINDOWS["1W"]
    elif timeframe == "4H":
        higher_path = _dataset_path(symbol, "1D")
        parent_path = _dataset_path(symbol, "1W")
        if higher_path.exists():
            context["higher_timeframe_csv_path"] = str(higher_path)
            context["higher_timeframe_min_window"] = BACKTEST_MIN_WINDOWS["1D"]
        if parent_path.exists():
            context["parent_timeframe_csv_path"] = str(parent_path)
            context["parent_timeframe_min_window"] = BACKTEST_MIN_WINDOWS["1W"]

    return context


def _run_profitability_backtests(symbols: list[str], analysis_timeframes: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for symbol in symbols:
        for timeframe in analysis_timeframes:
            csv_path = _dataset_path(symbol, timeframe)
            if not csv_path.exists():
                rows.append(
                    {
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "dataset_path": str(csv_path),
                        "has_backtest": False,
                        "net_profit_usdt": None,
                        "avg_r_per_trade": None,
                        "final_equity_usdt": None,
                        "profitable": False,
                        "positive_expectancy": False,
                    }
                )
                continue

            context = _build_backtest_context(symbol, timeframe)
            result = run_portfolio_backtest(
                csv_path=str(csv_path),
                symbol=symbol,
                timeframe=timeframe,
                min_window=BACKTEST_MIN_WINDOWS[timeframe],
                step=KPI_BACKTEST_STEP,
                fee_rate=KPI_FEE_RATE,
                slippage_rate=KPI_SLIPPAGE_RATE,
                initial_capital=KPI_INITIAL_CAPITAL,
                risk_per_trade=KPI_RISK_PER_TRADE,
                max_concurrent=1,
                tp_allocations=KPI_TP_ALLOCATIONS,
                higher_timeframe_csv_path=context["higher_timeframe_csv_path"],
                higher_timeframe_min_window=context["higher_timeframe_min_window"],
                parent_timeframe_csv_path=context["parent_timeframe_csv_path"],
                parent_timeframe_min_window=context["parent_timeframe_min_window"],
            )
            summary = result.get("summary", {})
            net_profit = float(summary.get("net_profit_usdt") or 0.0)
            avg_r = float(summary.get("avg_r_per_trade") or 0.0)

            rows.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "dataset_path": str(csv_path),
                    "has_backtest": True,
                    "net_profit_usdt": net_profit,
                    "avg_r_per_trade": avg_r,
                    "final_equity_usdt": float(summary.get("final_equity_usdt") or 0.0),
                    "profitable": net_profit > 0.0,
                    "positive_expectancy": avg_r > 0.0,
                }
            )

    return rows


def _analyze_symbol_timeframe(symbol: str, timeframe: str) -> dict[str, Any]:
    path = _dataset_path(symbol, timeframe)
    if not path.exists():
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "dataset_path": str(path),
            "dataset_exists": False,
            "dataset_non_empty": False,
        }

    df = _load_dataframe(path)
    if df.empty:
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "dataset_path": str(path),
            "dataset_exists": True,
            "dataset_non_empty": False,
        }

    analysis = build_dataframe_analysis(symbol=symbol, timeframe=timeframe, df=df)
    position = analysis.get("position")
    projection = analysis.get("projection")
    scenarios = analysis.get("scenarios") or []

    actionable_scenarios = [scenario for scenario in scenarios if _scenario_is_actionable(scenario)]
    geometry_valid_scenarios = [scenario for scenario in actionable_scenarios if _scenario_has_valid_geometry(scenario)]

    row = {
        "symbol": symbol,
        "timeframe": timeframe,
        "dataset_path": str(path),
        "dataset_exists": True,
        "dataset_non_empty": True,
        "primary_pattern_type": analysis.get("primary_pattern_type"),
        "position_structure": getattr(position, "structure", None),
        "position_bias": getattr(position, "bias", None),
        "wave_number": getattr(position, "wave_number", None),
        "projection_structure": getattr(projection, "expected_structure", None),
        "projection_direction": getattr(projection, "expected_direction", None),
        "scenario_count": len(scenarios),
        "scenario_exists": bool(scenarios),
        "actionable_entry": bool(actionable_scenarios),
        "valid_entry_geometry": bool(geometry_valid_scenarios),
        "position_resolved": getattr(position, "structure", "UNKNOWN") != "UNKNOWN",
        "structure_retained": _structure_is_retained(
            analysis.get("primary_pattern_type"),
            getattr(position, "structure", None),
        ),
        "projection_resolved": getattr(projection, "expected_structure", "UNKNOWN") != "UNKNOWN",
    }

    if scenarios:
        first = scenarios[0]
        row["first_scenario"] = {
            "name": first.name,
            "bias": first.bias,
            "entry": first.confirmation,
            "stop_loss": first.stop_loss,
            "targets": list(first.targets or []),
        }

    return row


def _section_score(metrics: dict[str, float], targets: dict[str, MetricTarget]) -> float:
    total_weight = sum(item.weight for item in targets.values())
    if total_weight <= 0:
        return 0.0

    weighted = 0.0
    for key, target in targets.items():
        weighted += metrics.get(key, 0.0) * target.weight
    return round(weighted / total_weight, 2)


def compute_system_kpis(
    symbols: list[str] | None = None,
    analysis_timeframes: list[str] | None = None,
    data_timeframes: list[str] | None = None,
) -> dict[str, Any]:
    symbols = [symbol.upper() for symbol in (symbols or list(DEFAULT_SYMBOLS))]
    analysis_timeframes = [timeframe.upper() for timeframe in (analysis_timeframes or list(DEFAULT_ANALYSIS_TIMEFRAMES))]
    data_timeframes = [timeframe.upper() for timeframe in (data_timeframes or list(DEFAULT_DATA_TIMEFRAMES))]

    dataset_expected = len(symbols) * len(data_timeframes)
    dataset_non_empty = 0
    dataset_rows: list[dict[str, Any]] = []
    for symbol in symbols:
        for timeframe in data_timeframes:
            path = _dataset_path(symbol, timeframe)
            exists = path.exists()
            non_empty = False
            if exists:
                try:
                    non_empty = not _load_dataframe(path).empty
                except Exception:
                    non_empty = False
            if non_empty:
                dataset_non_empty += 1
            dataset_rows.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "dataset_path": str(path),
                    "dataset_exists": exists,
                    "dataset_non_empty": non_empty,
                }
            )

    analysis_rows = [
        _analyze_symbol_timeframe(symbol, timeframe)
        for symbol in symbols
        for timeframe in analysis_timeframes
    ]
    profitability_rows = _run_profitability_backtests(symbols, analysis_timeframes)

    weekly_validation = _safe_weekly_validation()
    analysis_count = len(analysis_rows)
    actionable_count = sum(1 for row in analysis_rows if row.get("actionable_entry"))
    backtest_count = sum(1 for row in profitability_rows if row.get("has_backtest"))

    metrics = {
        "data": {
            "dataset_coverage_pct": round(_ratio(dataset_non_empty, dataset_expected) * 100.0, 2),
        },
        "wave_counting": {
            "weekly_validation_accuracy_pct": weekly_validation["accuracy_pct"],
            "position_resolution_pct": round(_ratio(sum(1 for row in analysis_rows if row.get("position_resolved")), analysis_count) * 100.0, 2),
            "structure_retention_pct": round(_ratio(sum(1 for row in analysis_rows if row.get("structure_retained")), analysis_count) * 100.0, 2),
            "projection_resolution_pct": round(_ratio(sum(1 for row in analysis_rows if row.get("projection_resolved")), analysis_count) * 100.0, 2),
        },
        "entry_pipeline": {
            "scenario_coverage_pct": round(_ratio(sum(1 for row in analysis_rows if row.get("scenario_exists")), analysis_count) * 100.0, 2),
            "actionable_entry_pct": round(_ratio(actionable_count, analysis_count) * 100.0, 2),
            "valid_entry_geometry_pct": round(_ratio(sum(1 for row in analysis_rows if row.get("valid_entry_geometry")), actionable_count) * 100.0, 2),
        },
        "profitability": {
            "profitable_backtest_pct": round(_ratio(sum(1 for row in profitability_rows if row.get("profitable")), backtest_count) * 100.0, 2),
            "positive_expectancy_pct": round(_ratio(sum(1 for row in profitability_rows if row.get("positive_expectancy")), backtest_count) * 100.0, 2),
        },
    }

    section_scores = {
        section: _section_score(metrics[section], SECTION_TARGETS[section])
        for section in SECTION_TARGETS
    }

    targets = {
        section: {
            key: asdict(value)
            for key, value in target_group.items()
        }
        for section, target_group in SECTION_TARGETS.items()
    }

    profitability_gate = {
        "minimum_pass_threshold_pct": PROFITABILITY_PASS_THRESHOLD_PCT,
        "strong_pass_threshold_pct": PROFITABILITY_STRONG_THRESHOLD_PCT,
        "current_profitability_score_pct": section_scores["profitability"],
        "passes_minimum": section_scores["profitability"] >= PROFITABILITY_PASS_THRESHOLD_PCT,
        "passes_strong": section_scores["profitability"] >= PROFITABILITY_STRONG_THRESHOLD_PCT,
    }

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbols": symbols,
        "analysis_timeframes": analysis_timeframes,
        "data_timeframes": data_timeframes,
        "targets": targets,
        "section_scores": section_scores,
        "metrics": metrics,
        "profitability_gate": profitability_gate,
        "weekly_validation": weekly_validation,
        "dataset_rows": dataset_rows,
        "analysis_rows": analysis_rows,
        "profitability_rows": profitability_rows,
    }


def write_system_kpi_report(report: dict[str, Any], output_path: str | None = None) -> Path:
    path = Path(output_path) if output_path else Path("storage/local_system_kpi_report.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path
