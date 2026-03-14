from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ManualWaveContext:
    symbol: str
    timeframe: str
    bias: str
    wave_number: str
    structure: str | None = None
    position: str | None = None
    note: str | None = None
    source: str = "manual"


def _store_path() -> Path:
    raw = os.getenv("MANUAL_WAVE_CONTEXT_PATH", "storage/manual_wave_context.json")
    return Path(raw)


def load_manual_wave_contexts() -> dict:
    path = _store_path()
    if not path.exists():
        return {"version": 1, "contexts": {}}

    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def get_manual_wave_context(symbol: str, timeframe: str) -> ManualWaveContext | None:
    payload = load_manual_wave_contexts()
    key = f"{symbol.upper()}|{timeframe.upper()}"
    item = (payload.get("contexts") or {}).get(key)
    if not item:
        return None

    return ManualWaveContext(
        symbol=symbol.upper(),
        timeframe=timeframe.upper(),
        bias=str(item.get("bias") or "").upper(),
        wave_number=str(item.get("wave_number") or ""),
        structure=item.get("structure"),
        position=item.get("position"),
        note=item.get("note"),
        source=str(item.get("source") or "manual"),
    )


def serialize_manual_wave_context(context: ManualWaveContext | None) -> dict | None:
    if context is None:
        return None
    if hasattr(context, "__dataclass_fields__"):
        return asdict(context)
    return dict(vars(context))
