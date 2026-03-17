from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def experience_store_enabled() -> bool:
    return os.getenv("EXPERIENCE_STORE_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}


def _store_path() -> Path:
    raw = os.getenv("EXPERIENCE_STORE_PATH", "storage/experience_store.json")
    return Path(raw)


def clear_experience_store_cache() -> None:
    load_experience_store.cache_clear()


@lru_cache(maxsize=1)
def load_experience_store() -> dict:
    path = _store_path()
    if not path.exists():
        return {"version": 2, "patterns": {}, "scenarios": {}}

    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)

    if not isinstance(payload, dict):
        return {"version": 2, "patterns": {}, "scenarios": {}}

    payload.setdefault("patterns", {})
    payload.setdefault("scenarios", {})
    payload.setdefault("version", 2)
    return payload


def save_experience_store(payload: dict) -> Path:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
    clear_experience_store_cache()
    return path


def _edge_key(symbol: str, timeframe: str, pattern: str, side: str) -> str:
    return f"{symbol.upper()}|{timeframe.upper()}|{pattern.upper()}|{side.upper()}"


def _scenario_key(symbol: str, timeframe: str, pattern: str, scenario_name: str, side: str) -> str:
    return (
        f"{symbol.upper()}|{timeframe.upper()}|{pattern.upper()}|"
        f"{scenario_name.strip().upper()}|{side.upper()}"
    )


@dataclass
class PatternEdge:
    sample_count: int
    win_count: int
    loss_count: int
    win_rate: float
    avg_r: float
    total_r: float

    @property
    def positive(self) -> bool:
        return self.sample_count >= 2 and self.avg_r >= 0.12 and self.win_rate >= 0.5

    @property
    def negative(self) -> bool:
        return self.sample_count >= 3 and self.avg_r <= -0.35 and self.win_rate <= 0.34

    @property
    def severe_negative(self) -> bool:
        return self.sample_count >= 3 and self.avg_r <= -0.6 and self.win_rate <= 0.2


def _record_group_edge(grouped: dict, key: str, reward_r: float) -> None:
    grouped[key]["sample_count"] += 1
    grouped[key]["total_r"] += reward_r
    if reward_r > 0:
        grouped[key]["win_count"] += 1
    else:
        grouped[key]["loss_count"] += 1


def _summarize_grouped_edges(grouped: dict) -> dict[str, dict]:
    edges: dict[str, dict] = {}
    for key, value in grouped.items():
        sample_count = value["sample_count"]
        win_rate = value["win_count"] / sample_count if sample_count else 0.0
        avg_r = value["total_r"] / sample_count if sample_count else 0.0
        edges[key] = {
            "sample_count": sample_count,
            "win_count": value["win_count"],
            "loss_count": value["loss_count"],
            "win_rate": round(win_rate, 3),
            "avg_r": round(avg_r, 3),
            "total_r": round(value["total_r"], 3),
        }
    return edges


def build_experience_payload(records: list[dict]) -> dict:
    grouped_patterns = defaultdict(
        lambda: {"sample_count": 0, "win_count": 0, "loss_count": 0, "total_r": 0.0}
    )
    grouped_scenarios = defaultdict(
        lambda: {"sample_count": 0, "win_count": 0, "loss_count": 0, "total_r": 0.0}
    )

    for record in records:
        reward_r = float(record["reward_r"])
        pattern_key = _edge_key(
            record["symbol"],
            record["timeframe"],
            record["pattern"],
            record["side"],
        )
        _record_group_edge(grouped_patterns, pattern_key, reward_r)

        scenario_name = str(record.get("scenario_name") or "").strip()
        if scenario_name:
            scenario_key = _scenario_key(
                record["symbol"],
                record["timeframe"],
                record["pattern"],
                scenario_name,
                record["side"],
            )
            _record_group_edge(grouped_scenarios, scenario_key, reward_r)

    return {
        "version": 2,
        "patterns": _summarize_grouped_edges(grouped_patterns),
        "scenarios": _summarize_grouped_edges(grouped_scenarios),
    }


def get_pattern_edge(symbol: str, timeframe: str, pattern: str | None, side: str | None) -> PatternEdge | None:
    if not experience_store_enabled():
        return None
    if not pattern or not side:
        return None

    payload = load_experience_store()
    item = (payload.get("patterns") or {}).get(_edge_key(symbol, timeframe, pattern, side))
    if not item:
        return None

    return PatternEdge(
        sample_count=int(item["sample_count"]),
        win_count=int(item["win_count"]),
        loss_count=int(item["loss_count"]),
        win_rate=float(item["win_rate"]),
        avg_r=float(item["avg_r"]),
        total_r=float(item["total_r"]),
    )


def get_scenario_edge(
    symbol: str,
    timeframe: str,
    pattern: str | None,
    scenario_name: str | None,
    side: str | None,
) -> PatternEdge | None:
    if not experience_store_enabled():
        return None
    if not pattern or not scenario_name or not side:
        return None

    payload = load_experience_store()
    item = (payload.get("scenarios") or {}).get(
        _scenario_key(symbol, timeframe, pattern, scenario_name, side)
    )
    if not item:
        return None

    return PatternEdge(
        sample_count=int(item["sample_count"]),
        win_count=int(item["win_count"]),
        loss_count=int(item["loss_count"]),
        win_rate=float(item["win_rate"]),
        avg_r=float(item["avg_r"]),
        total_r=float(item["total_r"]),
    )
