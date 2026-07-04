"""Sends edge statistics to Gemini and stores the analysis in gemini_insights.json.

Requires GEMINI_API_KEY env var. If not set, does nothing (safe no-op).
Uses gemini-1.5-flash (free tier eligible).
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from datetime import UTC, datetime
from pathlib import Path


_INSIGHTS_PATH = Path(__file__).parent.parent / "storage" / "gemini_insights.json"
_MODEL = "gemini-2.0-flash-lite"
_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

_SYSTEM_PROMPT = """You are an Elliott Wave trading edge analyst.
You receive a JSON snapshot of actual trade results from a live trading engine.
Your job: identify patterns, strengths, weaknesses, and risks in the data.

Rules:
- Only draw conclusions from the data provided. Do not invent or assume facts.
- Be concise. Use bullet points.
- Focus on actionable findings (e.g. "LONG trades significantly underperform SHORT",
  "Pattern X has <40% WR — consider filtering", "Losses cluster at UTC hours 08-10").
- If sample size for a sub-group is < 10, flag it as "insufficient data".
- Report the overall edge assessment: "positive", "marginal", or "negative".
"""


def _call_gemini(api_key: str, prompt: str) -> str:
    url = f"{_API_BASE}/{_MODEL}:generateContent?key={api_key}"
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048},
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except urllib.error.HTTPError as e:
        return f"[Gemini API error {e.code}: {e.read().decode(errors='replace')}]"
    except Exception as e:
        return f"[Gemini call failed: {e}]"


def analyze(edge_store: dict, insights_path: Path | None = None) -> dict | None:
    """Run Gemini analysis on edge_store. Returns insights dict or None if no API key."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None

    out = insights_path or _INSIGHTS_PATH

    stats = edge_store.get("stats", {})
    prompt = (
        f"{_SYSTEM_PROMPT}\n\n"
        f"Total closed trades: {edge_store.get('total_closed', 0)}\n"
        f"Last updated: {edge_store.get('last_updated', '')}\n\n"
        f"Statistics:\n{json.dumps(stats, indent=2, ensure_ascii=False)}"
    )

    text = _call_gemini(api_key, prompt)

    insights = {
        "last_analyzed": datetime.now(UTC).isoformat(),
        "analyzed_through_signal_id": edge_store.get("last_processed_id"),
        "total_trades_analyzed": edge_store.get("total_closed", 0),
        "analysis": text,
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(insights, indent=2, ensure_ascii=False))
    return insights
