"""Tests for foundry.notifications.telegram — no real HTTP calls."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from foundry.notifications.telegram import TelegramNotifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_notifier() -> TelegramNotifier:
    return TelegramNotifier(token="test-token", chat_id="123456")


def _ok_response(ok: bool = True) -> MagicMock:
    """Return a mock context-manager response with a JSON body."""
    body = json.dumps({"ok": ok}).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# ---------------------------------------------------------------------------
# send_message — success path
# ---------------------------------------------------------------------------

def test_send_message_success():
    """send_message returns True when the API responds with ok=true."""
    notifier = _make_notifier()
    with patch("urllib.request.urlopen", return_value=_ok_response(True)) as mock_open:
        result = notifier.send_message("hello world")

    assert result is True
    mock_open.assert_called_once()
    # Verify the request was built with the right URL
    req: urllib.request.Request = mock_open.call_args[0][0]
    assert "test-token" in req.full_url
    assert req.get_header("Content-type") == "application/json"


# ---------------------------------------------------------------------------
# send_message — HTTP error returns False
# ---------------------------------------------------------------------------

def test_send_message_http_error_returns_false():
    """send_message returns False on an HTTP error and does not raise."""
    notifier = _make_notifier()
    http_err = urllib.error.HTTPError(
        url="https://api.telegram.org/...",
        code=401,
        msg="Unauthorized",
        hdrs=None,  # type: ignore[arg-type]
        fp=None,
    )
    with patch("urllib.request.urlopen", side_effect=http_err):
        result = notifier.send_message("should fail")

    assert result is False


# ---------------------------------------------------------------------------
# send_message — API returns ok=false
# ---------------------------------------------------------------------------

def test_send_message_api_ok_false_returns_false():
    """send_message returns False when the API body contains ok=false."""
    notifier = _make_notifier()
    with patch("urllib.request.urlopen", return_value=_ok_response(False)):
        result = notifier.send_message("bad request")

    assert result is False


# ---------------------------------------------------------------------------
# notify_review_ready — message format
# ---------------------------------------------------------------------------

def test_notify_review_ready_formats_message():
    """notify_review_ready sends a message containing the task, project, and tag."""
    notifier = _make_notifier()
    captured: list[str] = []

    def fake_urlopen(req, timeout=None):
        body = req.data.decode("utf-8")
        payload = json.loads(body)
        captured.append(payload["text"])
        return _ok_response(True)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = notifier.notify_review_ready(
            task_title="Add trailing stop",
            project="Pipnesiatest EA",
            review_tag="behavioral",
        )

    assert result is True
    assert len(captured) == 1
    msg = captured[0]
    assert "Review Ready" in msg
    assert "Add trailing stop" in msg
    assert "Pipnesiatest EA" in msg
    assert "behavioral" in msg


# ---------------------------------------------------------------------------
# send_daily_digest — message format
# ---------------------------------------------------------------------------

def test_send_daily_digest_formats_stats():
    """send_daily_digest sends a message containing all four stat values."""
    notifier = _make_notifier()
    stats = {
        "pending_triage": 5,
        "building": 2,
        "review_queue": 3,
        "killed_today": 7,
    }
    captured: list[str] = []

    def fake_urlopen(req, timeout=None):
        payload = json.loads(req.data.decode("utf-8"))
        captured.append(payload["text"])
        return _ok_response(True)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = notifier.send_daily_digest(stats)

    assert result is True
    assert len(captured) == 1
    msg = captured[0]
    assert "5" in msg
    assert "2" in msg
    assert "3" in msg
    assert "7" in msg
    assert "Digest" in msg


# ---------------------------------------------------------------------------
# notify_triage_complete — verdict in message
# ---------------------------------------------------------------------------

def test_notify_triage_complete_includes_verdict():
    """notify_triage_complete includes the verdict in the sent message."""
    notifier = _make_notifier()
    captured: list[str] = []

    def fake_urlopen(req, timeout=None):
        payload = json.loads(req.data.decode("utf-8"))
        captured.append(payload["text"])
        return _ok_response(True)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = notifier.notify_triage_complete(
            entry_summary="Build a new trading dashboard",
            verdict="KILL",
        )

    assert result is True
    msg = captured[0]
    assert "KILL" in msg
    assert "Build a new trading dashboard" in msg


# ---------------------------------------------------------------------------
# Network failure (URLError) returns False
# ---------------------------------------------------------------------------

def test_send_message_url_error_returns_false():
    """send_message returns False on a network-level URLError."""
    notifier = _make_notifier()
    url_err = urllib.error.URLError(reason="Name or service not known")
    with patch("urllib.request.urlopen", side_effect=url_err):
        result = notifier.send_message("network down")

    assert result is False
