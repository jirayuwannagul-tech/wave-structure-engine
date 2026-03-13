"""Tests for error handling in notifier.send_notification."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
import requests

from services.notifier import send_notification


class TestSendNotificationRetry:
    def test_prints_and_returns_false_when_no_token(self, capsys):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}):
            result = send_notification("hello")
        assert result is False
        captured = capsys.readouterr()
        assert "hello" in captured.out

    def test_returns_true_on_success(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "fake_token", "TELEGRAM_CHAT_ID": "-100123"}), \
             patch("services.notifier.requests.post", return_value=mock_resp):
            result = send_notification("hello")
        assert result is True

    def test_retries_on_connection_error_then_succeeds(self):
        good_resp = MagicMock()
        good_resp.raise_for_status.return_value = None

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "fake_token", "TELEGRAM_CHAT_ID": "-100123"}), \
             patch("services.notifier.requests.post") as mock_post, \
             patch("services.notifier.time.sleep"):
            mock_post.side_effect = [requests.ConnectionError("timeout"), good_resp]
            result = send_notification("hello")

        assert result is True
        assert mock_post.call_count == 2

    def test_returns_false_after_all_retries_fail(self, capsys):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "fake_token", "TELEGRAM_CHAT_ID": "-100123"}), \
             patch("services.notifier.requests.post") as mock_post, \
             patch("services.notifier.time.sleep"):
            mock_post.side_effect = requests.ConnectionError("no network")
            result = send_notification("hello")

        assert result is False
        assert mock_post.call_count == 3
        captured = capsys.readouterr()
        assert "failed" in captured.out
