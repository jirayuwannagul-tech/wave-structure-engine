"""Per-symbol AI memory: analyzes each coin's trade history and accumulates insights over time.

Each symbol gets its own JSON memory file in storage/symbol_memory/{SYMBOL}.json.
Gemini reads previous insights + new trades, updates its understanding incrementally.

Usage:
    from services.symbol_analyst import analyze_symbol, analyze_all_symbols
"""
from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

_MEMORY_DIR = Path(__file__).parent.parent / "storage" / "symbol_memory"
_DB_PATH = Path(__file__).parent.parent / "storage" / "wave_engine.db"
_MODEL = "gemini-2.5-flash"
_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

_SYSTEM_PROMPT = """You are a trading system analyst specializing in Elliott Wave crypto trading.
You track one specific cryptocurrency symbol over time and build up institutional knowledge about it.

Your job:
1. Analyze ALL trades for this symbol — patterns, sides (LONG/SHORT), timeframes, setups
2. Identify what logic is working vs not working for THIS coin specifically
3. Compare with your previous memory (if any) — what has changed?
4. Give 2-3 specific, actionable recommendations to improve this coin's trading logic

Rules:
- n < 10 trades: label findings as "early indication, not confirmed"
- n >= 10: state findings as preliminary conclusions
- n >= 30: state findings as reliable conclusions
- Focus on THIS symbol only — ignore what works for other coins
- Be direct and specific: "LONG setups on 4H have 30% WR — consider disabling LONG on this coin"
- End with overall verdict: "promising" / "marginal" / "not working yet"
"""


def _call_gemini(api_key: str, prompt: str) -> str:
    url = f"{_API_BASE}/{_MODEL}:generateContent?key={api_key}"
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 4096,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except urllib.error.HTTPError as e:
        return f"[Gemini error {e.code}: {e.read().decode(errors='replace')}]"
    except Exception as e:
        return f"[Gemini call failed: {e}]"


def _load_trades(symbol: str, db_path: Path) -> list[dict]:
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT id, timeframe, side, status,
                   entry_price, entry_triggered_price, stop_loss,
                   rr_tp1, rr_tp2, rr_tp3,
                   tp1_hit_at, tp2_hit_at, tp3_hit_at,
                   closed_at, analysis_summary_json
            FROM signals
            WHERE symbol = ? AND status IN ('TP3_HIT','STOPPED')
              AND entry_triggered_at IS NOT NULL
            ORDER BY closed_at ASC
        """, (symbol,)).fetchall()
        conn.close()
    except Exception:
        return []

    trades = []
    for r in rows:
        entry = float(r["entry_triggered_price"] or r["entry_price"] or 0)
        sl = float(r["stop_loss"] or 0)
        if r["tp3_hit_at"]:
            result = "TP3_HIT"
        elif r["tp2_hit_at"]:
            result = "TP2_THEN_SL"
        elif r["tp1_hit_at"]:
            result = "TP1_THEN_SL"
        else:
            result = "SL_HIT"

        pattern, leg = None, None
        try:
            s = json.loads(r["analysis_summary_json"] or "{}")
            pattern = s.get("pattern_type") or s.get("pattern")
            leg = s.get("current_leg")
        except Exception:
            pass

        trades.append({
            "id": r["id"],
            "side": r["side"],
            "timeframe": r["timeframe"],
            "result": result,
            "rr_tp3": round(float(r["rr_tp3"] or 0), 2),
            "sl_pct": round(abs(entry - sl) / entry * 100, 2) if entry and sl else None,
            "pattern": pattern,
            "leg": leg,
            "closed_at": (r["closed_at"] or "")[:10],
        })
    return trades


def _compute_stats(trades: list[dict]) -> dict:
    if not trades:
        return {}
    n = len(trades)
    wins = sum(1 for t in trades if t["result"] != "SL_HIT")

    def bucket(items, key):
        out: dict = {}
        for t in items:
            k = str(t.get(key) or "unknown")
            if k not in out:
                out[k] = {"n": 0, "wins": 0}
            out[k]["n"] += 1
            if t["result"] != "SL_HIT":
                out[k]["wins"] += 1
        for k in out:
            d = out[k]
            d["wr"] = round(d["wins"] / d["n"], 2)
        return out

    rr_vals = [t["rr_tp3"] for t in trades if t["rr_tp3"]]
    return {
        "n": n,
        "wr": round(wins / n, 2),
        "avg_rr_tp3": round(sum(rr_vals) / len(rr_vals), 2) if rr_vals else 0,
        "by_result": bucket(trades, "result"),
        "by_side": bucket(trades, "side"),
        "by_timeframe": bucket(trades, "timeframe"),
        "by_pattern": bucket(trades, "pattern"),
        "by_leg": bucket(trades, "leg"),
    }


def analyze_symbol(
    symbol: str,
    db_path: Path | None = None,
    api_key: str | None = None,
    memory_dir: Path | None = None,
    force: bool = False,
) -> dict | None:
    """Analyze one symbol and update its memory file. Returns memory dict or None."""
    key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None

    db = db_path or _DB_PATH
    mem_dir = memory_dir or _MEMORY_DIR
    mem_dir.mkdir(parents=True, exist_ok=True)
    mem_path = mem_dir / f"{symbol}.json"

    existing: dict = {}
    if mem_path.exists():
        try:
            existing = json.loads(mem_path.read_text())
        except Exception:
            existing = {}

    trades = _load_trades(symbol, db)
    if not trades:
        return None

    prev_n = existing.get("ai_memory", {}).get("n_trades_at_analysis", 0)
    if not force and len(trades) <= prev_n:
        return existing  # no new data

    stats = _compute_stats(trades)
    prev_insights = existing.get("ai_memory", {}).get("cumulative_insights", "")
    prev_recs = existing.get("ai_memory", {}).get("recommendations", [])

    parts = [_SYSTEM_PROMPT, f"\n\nSymbol: **{symbol}**\n"]
    if prev_insights:
        parts.append(
            f"\n--- PREVIOUS MEMORY (from {existing.get('ai_memory',{}).get('last_analyzed','?')[:10]}, "
            f"{prev_n} trades) ---\n{prev_insights}\n"
            f"Previous recommendations: {json.dumps(prev_recs, ensure_ascii=False)}\n---\n\n"
        )
        parts.append(f"NEW DATA: {len(trades) - prev_n} new trade(s) added. Total now {len(trades)}.\n\n")
    else:
        parts.append(f"\nFirst analysis. Total trades: {len(trades)}\n\n")

    parts.append(f"Statistics:\n{json.dumps(stats, indent=2, ensure_ascii=False)}\n\n")
    parts.append(f"All trades:\n{json.dumps(trades, indent=2, ensure_ascii=False)}\n")

    analysis = _call_gemini(key, "".join(parts))

    change_log = existing.get("ai_memory", {}).get("change_log", [])
    change_log.append({
        "date": datetime.now(UTC).isoformat()[:19],
        "n_trades": len(trades),
        "new_trades": len(trades) - prev_n,
        "snippet": analysis[:200].replace("\n", " "),
    })

    memory = {
        "symbol": symbol,
        "last_updated": datetime.now(UTC).isoformat(),
        "total_trades": len(trades),
        "stats": stats,
        "trades": trades,
        "ai_memory": {
            "last_analyzed": datetime.now(UTC).isoformat(),
            "n_trades_at_analysis": len(trades),
            "cumulative_insights": analysis,
            "change_log": change_log[-30:],
        },
    }

    mem_path.write_text(json.dumps(memory, indent=2, ensure_ascii=False))
    return memory


def analyze_all_symbols(
    db_path: Path | None = None,
    api_key: str | None = None,
    memory_dir: Path | None = None,
) -> dict[str, dict]:
    """Analyze all symbols that have new trades. Returns {symbol: memory}."""
    db = db_path or _DB_PATH
    try:
        conn = sqlite3.connect(str(db))
        rows = conn.execute("""
            SELECT DISTINCT symbol FROM signals
            WHERE status IN ('TP3_HIT','STOPPED') AND entry_triggered_at IS NOT NULL
        """).fetchall()
        conn.close()
        symbols = [r[0] for r in rows]
    except Exception:
        return {}

    results = {}
    for sym in symbols:
        mem = analyze_symbol(sym, db_path=db, api_key=api_key, memory_dir=memory_dir)
        if mem:
            results[sym] = mem
    return results


def load_all_memories(memory_dir: Path | None = None) -> dict[str, dict]:
    """Load all existing symbol memory files from disk."""
    mem_dir = memory_dir or _MEMORY_DIR
    if not mem_dir.exists():
        return {}
    result = {}
    for f in mem_dir.glob("*.json"):
        try:
            result[f.stem] = json.loads(f.read_text())
        except Exception:
            pass
    return result
