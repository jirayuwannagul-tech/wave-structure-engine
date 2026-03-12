from __future__ import annotations


class AlertStateStore:
    def __init__(self):
        self._states: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._states.get(key)

    def set(self, key: str, state: str) -> None:
        self._states[key] = state

    def should_alert(self, key: str, new_state: str) -> bool:
        old_state = self._states.get(key)
        if old_state == new_state:
            return False
        self._states[key] = new_state
        return True

    def clear_prefix(self, prefix: str) -> None:
        keys_to_delete = [key for key in self._states if key.startswith(prefix)]
        for key in keys_to_delete:
            del self._states[key]
