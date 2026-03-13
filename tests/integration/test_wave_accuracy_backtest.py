import pandas as pd

from analysis.multi_count_engine import generate_labeled_wave_counts, generate_wave_counts
from analysis.pivot_detector import detect_pivots
from analysis.wave_decision_engine import build_wave_summary


def evaluate_direction_correctness(current_price: float, future_price: float, bias: str) -> bool:
    if bias == "BULLISH":
        return future_price > current_price
    if bias == "BEARISH":
        return future_price < current_price
    return False


def run_backtest(csv_path: str, lookahead: int, min_window: int, step: int):
    df = pd.read_csv(csv_path).copy()

    if "open_time" in df.columns:
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True, errors="coerce")

    results = []
    total_len = len(df)

    for end_idx in range(min_window, total_len - lookahead, step):
        sample_df = df.iloc[:end_idx].copy()

        current_price = float(sample_df.iloc[-1]["close"])
        future_price = float(df.iloc[end_idx + lookahead - 1]["close"])

        pivots = detect_pivots(sample_df)
        wave_counts = generate_wave_counts(pivots, df=sample_df)
        labeled_wave_counts = generate_labeled_wave_counts(
            pivots,
            timeframe="BACKTEST",
            df=sample_df,
        )

        if not wave_counts or not labeled_wave_counts:
            continue

        wave_summary = build_wave_summary(labeled_wave_counts)
        bias = wave_summary.get("bias")

        if not bias:
            continue

        correct = evaluate_direction_correctness(current_price, future_price, bias)

        results.append(
            {
                "end_idx": end_idx,
                "bias": bias,
                "structure": wave_summary.get("current_wave"),
                "current_price": current_price,
                "future_price": future_price,
                "correct": correct,
            }
        )

    return results


def summarize_accuracy(results, label: str):
    assert isinstance(results, list)
    assert len(results) > 0

    correct_count = sum(1 for r in results if r["correct"] is True)
    accuracy = correct_count / len(results)

    print(f"\n{label} backtest samples = {len(results)}")
    print(f"{label} accuracy = {accuracy:.3f}")

    assert 0.0 <= accuracy <= 1.0

    return {
        "samples": len(results),
        "accuracy": accuracy,
    }


def test_wave_accuracy_backtest_1d_runs():
    results = run_backtest("data/BTCUSDT_1d.csv", lookahead=5, min_window=120, step=1)
    summary = summarize_accuracy(results, "1D")
    assert summary["samples"] >= 10
    assert summary["accuracy"] >= 0.35


def test_wave_accuracy_backtest_1w_runs():
    results = run_backtest("data/BTCUSDT_1w.csv", lookahead=2, min_window=80, step=1)
    summary = summarize_accuracy(results, "1W")
    assert summary["samples"] >= 50
    assert summary["accuracy"] >= 0.55


def test_wave_accuracy_backtest_4h_runs():
    results = run_backtest("data/BTCUSDT_4h.csv", lookahead=10, min_window=150, step=1)
    summary = summarize_accuracy(results, "4H")
    assert summary["samples"] >= 60
    assert summary["accuracy"] >= 0.46


def test_wave_accuracy_backtest_total_acceptance():
    cases = [
        ("data/BTCUSDT_1d.csv", 5, 120, 1),
        ("data/BTCUSDT_1w.csv", 2, 80, 1),
        ("data/BTCUSDT_4h.csv", 10, 150, 1),
    ]

    total_results = []
    for csv_path, lookahead, min_window, step in cases:
        total_results.extend(
            run_backtest(
                csv_path,
                lookahead=lookahead,
                min_window=min_window,
                step=step,
            )
        )

    summary = summarize_accuracy(total_results, "ALL")
    assert summary["samples"] >= 130
    assert summary["accuracy"] >= 0.45
