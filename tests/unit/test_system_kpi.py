import json

from analysis import system_kpi


def test_compute_system_kpis_aggregates_section_scores(monkeypatch):
    monkeypatch.setattr(
        "analysis.system_kpi._safe_weekly_validation",
        lambda: {"total": 20, "passed": 18, "accuracy_pct": 90.0, "status": "ok"},
    )
    monkeypatch.setattr(
        "analysis.system_kpi._load_dataframe",
        lambda path: __import__("pandas").DataFrame({"open_time": ["2026-01-01"], "close": [1.0]}),
    )
    monkeypatch.setattr(
        "analysis.system_kpi.Path.exists",
        lambda self: True,
    )
    monkeypatch.setattr(
        "analysis.system_kpi._analyze_symbol_timeframe",
        lambda symbol, timeframe: {
            "symbol": symbol,
            "timeframe": timeframe,
            "dataset_exists": True,
            "dataset_non_empty": True,
            "position_resolved": True,
            "structure_retained": timeframe == "1D",
            "projection_resolved": True,
            "scenario_exists": True,
            "actionable_entry": True,
            "valid_entry_geometry": timeframe == "1D",
        },
    )
    monkeypatch.setattr(
        "analysis.system_kpi._run_profitability_backtests",
        lambda symbols, analysis_timeframes: [
            {
                "symbol": "BTCUSDT",
                "timeframe": "1D",
                "has_backtest": True,
                "profitable": True,
                "positive_expectancy": True,
            },
            {
                "symbol": "BTCUSDT",
                "timeframe": "4H",
                "has_backtest": True,
                "profitable": False,
                "positive_expectancy": False,
            },
        ],
    )

    report = system_kpi.compute_system_kpis(
        symbols=["BTCUSDT"],
        analysis_timeframes=["1D", "4H"],
        data_timeframes=["1W", "1D", "4H"],
    )

    assert report["section_scores"]["data"] == 100.0
    assert report["metrics"]["wave_counting"]["weekly_validation_accuracy_pct"] == 90.0
    assert report["metrics"]["entry_pipeline"]["scenario_coverage_pct"] == 100.0
    assert report["metrics"]["entry_pipeline"]["valid_entry_geometry_pct"] == 50.0
    assert report["metrics"]["profitability"]["profitable_backtest_pct"] == 50.0
    assert report["profitability_gate"]["passes_minimum"] is False


def test_write_system_kpi_report_writes_json(tmp_path):
    report = {
        "section_scores": {"data": 90.0},
        "metrics": {"data": {"dataset_coverage_pct": 90.0}},
    }

    output_path = tmp_path / "kpi_report.json"
    path = system_kpi.write_system_kpi_report(report, output_path=str(output_path))

    assert path == output_path
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["section_scores"]["data"] == 90.0
