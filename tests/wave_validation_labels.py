"""Ground-truth Elliott Wave labels for Primary degree (1W) — manually verified.

Each entry describes a KEY PIVOT in the 5-wave bull cycle:
  W3  — Wave 3 high (the first extended high)
  W4  — Wave 4 low  (the retracement before final rally)
  W5  — Wave 5 high (all-time high / cycle top)
  WA  — Wave A low  (first leg of ABC correction after the cycle top)

What the system SHOULD detect a few weeks AFTER each pivot:
  After W3: Primary IMPULSE bullish, wave_number="4", cw=3  (W4 retracement building)
  After W4: Primary IMPULSE bullish, wave_number="5", cw=4  (W5 rally building)
  After W5: Primary CORRECTION bearish, wave_number="A",  cw=5  (Wave A decline building)
  At   WA:  Primary CORRECTION bearish, wave_number="B",  cw=6  (Wave B bounce building)

Test dates are set 3 weeks after each pivot so right=2 confirmation is satisfied.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Ground-truth pivot prices (confirmed manually)
# ---------------------------------------------------------------------------

PIVOT_PRICES: dict[str, dict[str, tuple[str, float]]] = {
    # symbol → label → (date, pivot_price)
    "BTCUSDT": {
        "W3": ("2024-03-11", 73_777.00),
        "W4": ("2024-08-05", 49_000.00),
        "W5": ("2025-10-06", 126_200.00),
        "WA": ("2026-02-02",  60_000.00),
    },
    "ETHUSDT": {
        "W3": ("2024-03-11",  4_093.92),
        "W4": ("2024-08-05",  2_111.00),
        "W5": ("2025-08-18",  4_956.78),
        "WA": ("2026-02-02",  1_747.80),
    },
    "BNBUSDT": {
        "W3": ("2024-06-03",    721.80),
        "W4": ("2024-08-05",    400.00),
        "W5": ("2025-10-13",  1_375.11),
        "WA": ("2026-02-02",    570.06),
    },
    "SOLUSDT": {
        "W3": ("2024-03-18",    210.18),
        "W4": ("2024-08-05",    110.00),
        "W5": ("2025-01-13",    295.83),
        "WA": ("2026-02-02",     67.50),
    },
    "DOGEUSDT": {
        "W3": ("2024-12-02",      0.4843),
        "W4": ("2025-06-16",      0.1427),
        "W5": ("2025-09-08",      0.3068),
        "WA": ("2026-02-02",      0.0800),
    },
}

# ---------------------------------------------------------------------------
# What the detector should return 3 weeks AFTER each pivot date
# (structure, direction, wave_number, completed_waves)
# ---------------------------------------------------------------------------

EXPECTED_AFTER: dict[str, tuple[str, str, str, int]] = {
    # label → (structure, direction, wave_number, completed_waves)
    "W3": ("IMPULSE",    "bullish", "4", 3),
    "W4": ("IMPULSE",    "bullish", "5", 4),
    "W5": ("CORRECTION", "bearish", "A", 5),
    "WA": ("CORRECTION", "bearish", "B", 6),
}

# ---------------------------------------------------------------------------
# Validation runner
# ---------------------------------------------------------------------------


def run_validation(verbose: bool = True) -> dict:
    """Run the validation and return a results dict."""
    import os
    import pandas as pd
    from analysis.hierarchical_wave_counter import build_hierarchical_count_from_dfs
    from analysis.indicator_engine import calculate_atr
    from analysis.pivot_detector import detect_pivots, compress_pivots
    from analysis.inprogress_detector import detect_inprogress_wave

    results: dict[str, list[dict]] = {}
    total = 0
    passed = 0

    for sym, pivots_info in PIVOT_PRICES.items():
        w1_path = f"data/{sym}_1w.csv"
        w1d_path = f"data/{sym}_1d.csv"
        if not os.path.exists(w1_path):
            continue

        df_1w_full = pd.read_csv(w1_path)
        df_1w_full["open_time"] = pd.to_datetime(df_1w_full["open_time"]).dt.tz_localize(None)

        df_1d_full = pd.read_csv(w1d_path) if os.path.exists(w1d_path) else None
        if df_1d_full is not None:
            df_1d_full["open_time"] = pd.to_datetime(df_1d_full["open_time"]).dt.tz_localize(None)

        results[sym] = []

        for label, (pivot_date, pivot_price) in pivots_info.items():
            expected = EXPECTED_AFTER[label]
            exp_structure, exp_direction, exp_wave, exp_cw = expected

            # test date = 3 weeks after the pivot
            pivot_ts = pd.Timestamp(pivot_date)
            test_ts = pivot_ts + pd.Timedelta(weeks=3)

            # slice data up to test date
            df_1w = df_1w_full[df_1w_full["open_time"] <= test_ts].copy()
            if len(df_1w) < 10:
                continue

            df_1d = None
            if df_1d_full is not None:
                df_1d = df_1d_full[df_1d_full["open_time"] <= test_ts].copy()

            if df_1d is None or len(df_1d) < 10:
                df_1d = df_1w  # fallback

            count = build_hierarchical_count_from_dfs(
                symbol=sym,
                primary_df=df_1w,
                intermediate_df=df_1d,
                current_price=float(df_1w.iloc[-1]["close"]),
            )

            p = count.primary
            if p is None:
                actual_structure = "None"
                actual_direction = "None"
                actual_wave = "None"
                actual_cw = -1
            else:
                actual_structure = p.structure
                actual_direction = p.direction
                actual_wave = p.wave_number
                actual_cw = p.completed_waves

            ok = (
                actual_structure == exp_structure
                and actual_direction == exp_direction
                and actual_wave == exp_wave
                and actual_cw == exp_cw
            )

            total += 1
            if ok:
                passed += 1

            entry = {
                "symbol": sym,
                "label": label,
                "pivot_date": pivot_date,
                "pivot_price": pivot_price,
                "test_date": str(test_ts.date()),
                "expected": f"{exp_structure} {exp_direction} W{exp_wave} cw={exp_cw}",
                "actual": f"{actual_structure} {actual_direction} W{actual_wave} cw={actual_cw}",
                "pass": ok,
            }
            results[sym].append(entry)

            if verbose:
                status = "✅ PASS" if ok else "❌ FAIL"
                print(f"{status}  {sym:10} {label}  expected={entry['expected']}  got={entry['actual']}")

    if verbose:
        print(f"\n{'='*60}")
        print(f"RESULT: {passed}/{total} passed  ({100*passed//total if total else 0}%)")

    return {"total": total, "passed": passed, "details": results}


if __name__ == "__main__":
    run_validation(verbose=True)
