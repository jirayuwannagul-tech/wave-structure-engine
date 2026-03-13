"""Tests for AlertStateStore persistence."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from services.alert_state_store import AlertStateStore


class TestAlertStateStorePersistence:
    def test_should_alert_first_time(self, tmp_path):
        store = AlertStateStore(state_path=str(tmp_path / "state.json"))
        assert store.should_alert("btc_1d", "CONFIRMED") is True

    def test_should_not_alert_same_state(self, tmp_path):
        store = AlertStateStore(state_path=str(tmp_path / "state.json"))
        store.should_alert("btc_1d", "CONFIRMED")
        assert store.should_alert("btc_1d", "CONFIRMED") is False

    def test_should_alert_on_state_change(self, tmp_path):
        store = AlertStateStore(state_path=str(tmp_path / "state.json"))
        store.should_alert("btc_1d", "CONFIRMED")
        assert store.should_alert("btc_1d", "INVALIDATED") is True

    def test_state_persists_across_instances(self, tmp_path):
        path = str(tmp_path / "state.json")
        store1 = AlertStateStore(state_path=path)
        store1.set("btc_1d", "CONFIRMED")

        store2 = AlertStateStore(state_path=path)
        assert store2.get("btc_1d") == "CONFIRMED"

    def test_should_alert_respects_persisted_state(self, tmp_path):
        path = str(tmp_path / "state.json")
        store1 = AlertStateStore(state_path=path)
        store1.should_alert("btc_1d", "CONFIRMED")

        store2 = AlertStateStore(state_path=path)
        # Same state — no alert
        assert store2.should_alert("btc_1d", "CONFIRMED") is False

    def test_survives_corrupted_state_file(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text("not valid json {{{{", encoding="utf-8")
        store = AlertStateStore(state_path=str(path))
        # Should start with empty state, no crash
        assert store.get("anything") is None

    def test_clear_prefix_removes_matching_keys(self, tmp_path):
        store = AlertStateStore(state_path=str(tmp_path / "state.json"))
        store.set("btc_1d_level", "NEAR")
        store.set("btc_4h_level", "NEAR")
        store.set("eth_1d_level", "FAR")
        store.clear_prefix("btc_")
        assert store.get("btc_1d_level") is None
        assert store.get("btc_4h_level") is None
        assert store.get("eth_1d_level") == "FAR"
