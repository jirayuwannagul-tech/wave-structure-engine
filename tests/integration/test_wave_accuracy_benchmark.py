import pandas as pd

from analysis.pivot_detector import detect_pivots
from analysis.wave_detector import detect_latest_abc, detect_latest_impulse
from analysis.wave_position import detect_wave_position


def evaluate_direction_correctness(current_price: float, future_price: float, bias: str) -> bool:
    if bias == "BULLISH":
        return future_price > current_price
    if bias == "BEARISH":
        return future_price < current_price
    return False


def run_wave_benchmark(csv_path: str, lookahead: int = 5) -> dict:
    df = pd.read_csv(csv_path).copy()

    if "open_time" in df.columns:
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True, errors="coerce")

    if len(df) < 60:
        return {"has_pattern": False, "direction_correct": None}

    sample_df = df.iloc[:-lookahead].copy()
    current_price = float(sample_df.iloc[-1]["close"])
    future_price = float(df.iloc[-1]["close"])

    pivots = detect_pivots(sample_df)
    abc = detect_latest_abc(pivots)
    impulse = detect_latest_impulse(pivots)

    if abc is None and impulse is None:
        return {"has_pattern": False, "direction_correct": None}

    position = detect_wave_position(abc_pattern=abc, impulse_pattern=impulse)

    print(
        f"\nTF REPORT -> bias={position.bias} | structure={position.structure}"
    )

    is_correct = evaluate_direction_correctness(
        current_price, future_price, position.bias
    )

    return {
        "has_pattern": True,
        "direction_correct": is_correct,
        "bias": position.bias,
        "structure": position.structure,
    }


def test_wave_accuracy_benchmark_1d():
    result = run_wave_benchmark("data/BTCUSDT_1d.csv", lookahead=5)

    assert result["has_pattern"] is True
    assert result["bias"] in ["BULLISH", "BEARISH"]
    assert result["structure"] in ["ABC_CORRECTION", "IMPULSE"]


def test_wave_accuracy_benchmark_1w():
    result = run_wave_benchmark("data/BTCUSDT_1w.csv", lookahead=2)

    assert result["has_pattern"] is True
    assert result["bias"] in ["BULLISH", "BEARISH"]
    assert result["structure"] in ["ABC_CORRECTION", "IMPULSE"]


def test_wave_accuracy_benchmark_4h():
    result = run_wave_benchmark("data/BTCUSDT_4h.csv", lookahead=10)

    assert result["has_pattern"] is True
    assert result["bias"] in ["BULLISH", "BEARISH"]
    assert result["structure"] in ["ABC_CORRECTION", "IMPULSE"]