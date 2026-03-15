"""
Full portfolio backtest using real analysis logic.
Runs 1D timeframe with 1W context for all available symbols.
"""
from __future__ import annotations

import json
from pathlib import Path

from analysis.portfolio_backtest import run_global_portfolio_backtest

DATA_DIR = Path("data")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "DOGEUSDT"]

datasets = []
for symbol in SYMBOLS:
    csv_1d = DATA_DIR / f"{symbol}_1d.csv"
    csv_1w = DATA_DIR / f"{symbol}_1w.csv"
    csv_4h = DATA_DIR / f"{symbol}_4h.csv"

    if not csv_1d.exists():
        print(f"[SKIP] {symbol}: 1D data not found")
        continue

    # 1D analysis with 1W higher context
    datasets.append({
        "symbol": symbol,
        "timeframe": "1d",
        "csv_path": str(csv_1d),
        "min_window": 100,
        "step": 3,
        "higher_timeframe_csv_path": str(csv_1w) if csv_1w.exists() else None,
        "higher_timeframe_min_window": 30 if csv_1w.exists() else None,
    })

    # 4H analysis with 1D as higher, 1W as parent
    if csv_4h.exists():
        datasets.append({
            "symbol": symbol,
            "timeframe": "4h",
            "csv_path": str(csv_4h),
            "min_window": 200,
            "step": 12,
            "higher_timeframe_csv_path": str(csv_1d) if csv_1d.exists() else None,
            "higher_timeframe_min_window": 100 if csv_1d.exists() else None,
            "parent_timeframe_csv_path": str(csv_1w) if csv_1w.exists() else None,
            "parent_timeframe_min_window": 30 if csv_1w.exists() else None,
        })

print(f"Running backtest on {len(datasets)} dataset(s)...")
print(f"Symbols: {SYMBOLS}")
print("-" * 60)

result = run_global_portfolio_backtest(
    datasets=datasets,
    fee_rate=0.001,       # 10 bps per side
    slippage_rate=0.0005, # 5 bps slippage
    initial_capital=1000.0,
    risk_per_trade=0.02,  # 2% risk per trade
    max_concurrent=3,
    tp_allocations=(0.4, 0.3, 0.3),
)

overall = result["overall"]
by_symbol = result["by_symbol"]
by_timeframe = result["by_timeframe"]
by_symbol_timeframe = result["by_symbol_timeframe"]
trades = result["trades"]

print("\n=== PORTFOLIO OVERALL ===")
print(f"Initial capital   : ${overall['final_equity_usdt'] - overall['net_profit_usdt']:.2f}")
print(f"Final equity      : ${overall['final_equity_usdt']:.2f}")
print(f"Net profit        : ${overall['net_profit_usdt']:+.2f}")
print(f"Total trades      : {overall['triggered_trades']}")
print(f"Closed trades     : {overall['closed_trades']}")
print(f"Open trades       : {overall['open_trades']}")
print(f"Win rate          : {overall['win_rate']*100:.1f}%")
print(f"Avg R per trade   : {overall['avg_r_per_trade']:+.3f}R")
print(f"Avg win R         : {overall['avg_win_r']:+.3f}R")
print(f"Avg loss R        : {overall['avg_loss_r']:+.3f}R")
print(f"Max drawdown      : {overall['max_drawdown_pct']*100:.1f}%  (${overall['max_drawdown_usdt']:.2f})")
print(f"Skipped (concur.) : {overall['skipped_max_concurrent']}")

print("\n=== BY TIMEFRAME ===")
for tf, s in sorted(by_timeframe.items()):
    closed = s['closed_trades']
    wr = s['win_rate'] * 100
    avg_r = s['avg_r_per_trade']
    print(f"  {tf.upper():4}  trades={closed:4}  WR={wr:5.1f}%  avgR={avg_r:+.3f}R")

print("\n=== BY SYMBOL+TIMEFRAME ===")
header = f"{'Key':18} {'Windows':>8} {'Cases':>7} {'Setups':>7} {'Trades':>7} {'WR':>6} {'AvgR':>8}"
print(header)
print("-" * len(header))
for key, s in sorted(by_symbol_timeframe.items()):
    windows = s.get("candidate_total_windows", 0)
    cases   = s.get("candidate_analyzed_cases", 0)
    setups  = s.get("candidate_setups_built", 0)
    trades_n = s['closed_trades']
    wr       = s['win_rate'] * 100
    avg_r    = s['avg_r_per_trade']
    print(f"  {key:16}  {windows:>8}  {cases:>7}  {setups:>7}  {trades_n:>7}  {wr:>5.1f}%  {avg_r:>+8.3f}R")

print("\n=== TRADE LOG ===")
print(f"{'#':>3} {'Symbol':10} {'TF':4} {'Side':6} {'Structure':20} {'Outcome':15} {'R':>7} {'Equity':>10}")
print("-" * 85)
for i, rec in enumerate(trades[:50]):
    eq = rec.get("equity_after", 0)
    print(
        f"{i+1:>3} {rec['symbol']:10} {str(rec.get('timeframe','')).upper():4} "
        f"{str(rec.get('side','?')):6} {str(rec.get('structure') or '?'):20} "
        f"{rec['outcome']:15} {rec['reward_r']:>+7.3f}R  ${eq:>8.2f}"
    )

if len(trades) > 50:
    print(f"  ... and {len(trades)-50} more trades")

# Save full result to JSON
out_path = Path("backtest_result.json")
with open(out_path, "w") as f:
    json.dump(result, f, indent=2, default=str)
print(f"\nFull result saved to {out_path}")
