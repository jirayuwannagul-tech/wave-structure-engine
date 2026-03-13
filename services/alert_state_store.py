from __future__ import annotations

import json
import os
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

    def _load(self) -> dict[str, str]:
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items()}
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
        return self._states.get(key)

    def set(self, key: str, state: str) -> None:
        self._states[key] = state
        self._save()

    def should_alert(self, key: str, new_state: str) -> bool:
        old_state = self._states.get(key)
        if old_state == new_state:
            return False
        self._states[key] = new_state
        self._save()
        return True

    def clear_prefix(self, prefix: str) -> None:
        keys_to_delete = [key for key in self._states if key.startswith(prefix)]
        for key in keys_to_delete:
            del self._states[key]
        if keys_to_delete:
            self._save()
