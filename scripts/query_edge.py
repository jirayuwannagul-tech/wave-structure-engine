#!/usr/bin/env python3
"""CLI query tool: ask Gemini questions using stored edge context.

Usage:
    python scripts/query_edge.py "Pattern ไหนมี WR สูงสุด?"
    python scripts/query_edge.py --stats-only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import load_env_file
from services.gemini_analyst import _call_gemini


_STORE_PATH = Path(__file__).parent.parent / "storage" / "edge_store.json"
_INSIGHTS_PATH = Path(__file__).parent.parent / "storage" / "gemini_insights.json"

_QUERY_SYSTEM = """You are an Elliott Wave trading edge analyst.
Answer the user's question using ONLY the provided data.
Be concise and precise. If the data doesn't support an answer, say so."""


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _print_stats(store: dict) -> None:
    stats = store.get("stats", {})
    overall = stats.get("overall", {})
    print(f"\n=== Edge Stats ({store.get('last_updated', 'unknown')[:10]}) ===")
    print(f"Total trades : {store.get('total_closed', 0)}")
    print(f"Win rate     : {overall.get('wr', 0)*100:.1f}%")
    print(f"Avg RR       : {overall.get('avg_rr', 0):+.3f}R")
    print(f"Wins/Losses  : {overall.get('wins', 0)} / {overall.get('losses', 0)}")

    def _print_section(title: str, key: str) -> None:
        data = stats.get(key, {})
        if not data:
            return
        print(f"\n{title}:")
        for k, v in sorted(data.items(), key=lambda x: -x[1].get("n", 0)):
            wr = v.get("wr", 0) * 100
            n = v.get("n", 0)
            rr = v.get("avg_rr", 0)
            print(f"  {k:<20} n={n:>3}  WR={wr:>5.1f}%  avgRR={rr:>+.3f}R")

    _print_section("By Pattern", "by_pattern_type")
    _print_section("By Timeframe", "by_timeframe")
    _print_section("By Side", "by_side")
    _print_section("By Scenario", "by_scenario")
    _print_section("By Symbol", "by_symbol")

    leg_data = stats.get("by_leg", {})
    if leg_data:
        _print_section("By Wave Leg", "by_leg")
    else:
        print("\nBy Wave Leg   : no data yet (will populate for future signals)")

    streaks = stats.get("streaks", {})
    if streaks:
        print(
            f"\nStreaks       : current={streaks.get('current_type','?')}x{streaks.get('current_count',0)}"
            f"  max_win={streaks.get('max_win_streak',0)}  max_loss={streaks.get('max_loss_streak',0)}"
        )

    by_result = stats.get("by_result", {})
    if by_result:
        print("\nResult breakdown:")
        for k, v in sorted(by_result.items(), key=lambda x: -x[1]):
            print(f"  {k:<18} {v}")


def main() -> None:
    load_env_file()

    parser = argparse.ArgumentParser(description="Query edge data with Gemini")
    parser.add_argument("question", nargs="?", help="Question to ask Gemini")
    parser.add_argument("--stats-only", action="store_true", help="Print stats without Gemini")
    args = parser.parse_args()

    store = _load_json(_STORE_PATH)
    insights = _load_json(_INSIGHTS_PATH)

    if not store:
        print("No edge data found. Run the edge agent first.")
        print(f"Expected: {_STORE_PATH}")
        sys.exit(1)

    if args.stats_only or not args.question:
        _print_stats(store)
        if insights.get("analysis"):
            print(f"\n=== Last Gemini Analysis ({insights.get('last_analyzed','')[:10]}) ===")
            print(insights["analysis"])
        return

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("GEMINI_API_KEY not set. Showing stats only.\n")
        _print_stats(store)
        return

    stats = store.get("stats", {})
    context = (
        f"{_QUERY_SYSTEM}\n\n"
        f"Total closed trades: {store.get('total_closed', 0)}\n"
        f"Data as of: {store.get('last_updated', '')}\n\n"
        f"Statistics:\n{json.dumps(stats, indent=2, ensure_ascii=False)}\n\n"
    )
    if insights.get("analysis"):
        context += f"Previous analysis:\n{insights['analysis']}\n\n"
    context += f"Question: {args.question}"

    print("Querying Gemini...")
    answer = _call_gemini(api_key, context)
    print(f"\n{answer}")


if __name__ == "__main__":
    main()
