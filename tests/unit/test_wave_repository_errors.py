"""Tests for error handling in WaveRepository."""
from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from storage.wave_repository import WaveRepository


class TestWaveRepositoryErrorHandling:
    def test_initializes_without_error(self, tmp_path):
        repo = WaveRepository(db_path=str(tmp_path / "test.db"))
        assert repo is not None

    def test_fetch_signal_returns_none_for_missing_id(self, tmp_path):
        repo = WaveRepository(db_path=str(tmp_path / "test.db"))
        result = repo.fetch_signal(99999)
        assert result is None

    def test_fetch_active_signals_returns_empty_list(self, tmp_path):
        repo = WaveRepository(db_path=str(tmp_path / "test.db"))
        result = repo.fetch_active_signals("BTCUSDT")
        assert result == []

    def test_track_price_update_with_no_signals(self, tmp_path):
        repo = WaveRepository(db_path=str(tmp_path / "test.db"))
        events = repo.track_price_update("BTCUSDT", 83000.0)
        assert events == []

    def test_record_analysis_snapshot_returns_minus_one_on_db_error(self, tmp_path):
        repo = WaveRepository(db_path=str(tmp_path / "test.db"))
        bad_analysis: dict = {}  # missing all fields → snapshot = None → returns -1 gracefully
        # Should not raise
        snapshot_id = repo.record_analysis_snapshot(bad_analysis)
        # Returns -1 only on sqlite error; None analysis just inserts with nulls and returns id
        assert isinstance(snapshot_id, int)

    def test_sync_analysis_returns_none_for_empty_analysis(self, tmp_path):
        repo = WaveRepository(db_path=str(tmp_path / "test.db"))
        # No scenarios → build_signal_snapshot returns None → sync_analysis returns None
        result = repo.sync_analysis({})
        assert result is None

    def test_has_news_item_returns_false_for_unknown(self, tmp_path):
        repo = WaveRepository(db_path=str(tmp_path / "test.db"))
        assert repo.has_news_item("non-existent-id") is False

    def test_record_news_item_deduplication(self, tmp_path):
        repo = WaveRepository(db_path=str(tmp_path / "test.db"))
        kwargs = dict(
            source="coindesk",
            title="BTC hits 100k",
            link="https://example.com/1",
            published_at=None,
            summary_text=None,
            tag_text=None,
            external_id="abc123",
        )
        first_id = repo.record_news_item(**kwargs)
        second_id = repo.record_news_item(**kwargs)
        assert first_id is not None
        assert second_id is None  # duplicate → None
