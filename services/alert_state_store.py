from __future__ import annotations

import json
import os
import time
from pathlib import Path


_DEFAULT_STATE_PATH = "state/alert_state.json"


class AlertStateStore:
    """Tracks alert states to prevent duplicate notifications.

    States are persisted to a JSON file so they survive service restarts.
    If the file cannot be read or written, the store degrades gracefully
    to in-memory-only operation (no crash).
    """

    def __init__(self, state_path: str | None = None):
        self._path = Path(state_path or os.getenv("ALERT_STATE_PATH", _DEFAULT_STATE_PATH))
        self._states: dict[str, str] = self._load()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, object]:
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    # Backward compatible:
                    # - old format: {"key": "STATE"}
                    # - new format: {"key": {"state": "STATE", "ts": 1234567890.0}}
                    cleaned: dict[str, object] = {}
                    for k, v in data.items():
                        key = str(k)
                        if isinstance(v, dict) and "state" in v:
                            cleaned[key] = {"state": str(v.get("state")), "ts": float(v.get("ts") or 0.0)}
                        else:
                            cleaned[key] = str(v)
                    return cleaned
        except Exception as exc:
            print(f"[alert_state_store] Could not load state from {self._path}: {exc}")
        return {}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._states, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            print(f"[alert_state_store] Could not save state to {self._path}: {exc}")

    # ------------------------------------------------------------------
    # Public API (unchanged interface)
    # ------------------------------------------------------------------

    def get(self, key: str) -> str | None:
        value = self._states.get(key)
        if isinstance(value, dict):
            return str(value.get("state")) if value.get("state") is not None else None
        if value is None:
            return None
        return str(value)

    def set(self, key: str, state: str) -> None:
        self._states[key] = {"state": str(state), "ts": float(time.time())}
        self._save()

    def should_alert(self, key: str, new_state: str, *, cooldown_seconds: float = 0.0) -> bool:
        """Return True when an alert should be emitted.

        - Suppresses duplicates (same state as last time)
        - Optional cooldown to prevent flapping (rapid toggling)
        """
        now = float(time.time())
        new_state_s = str(new_state)

        raw = self._states.get(key)
        if isinstance(raw, dict):
            old_state = str(raw.get("state")) if raw.get("state") is not None else None
            last_ts = float(raw.get("ts") or 0.0)
        else:
            old_state = str(raw) if raw is not None else None
            last_ts = 0.0

        if old_state == new_state_s:
            return False

        if cooldown_seconds and (now - last_ts) < float(cooldown_seconds):
            # Update state in-memory so we still converge, but don't alert yet.
            self._states[key] = {"state": new_state_s, "ts": last_ts}
            self._save()
            return False

        self._states[key] = {"state": new_state_s, "ts": now}
        self._save()
        return True

    def clear_prefix(self, prefix: str) -> None:
        keys_to_delete = [key for key in self._states if key.startswith(prefix)]
        for key in keys_to_delete:
            del self._states[key]
        if keys_to_delete:
            self._save()
