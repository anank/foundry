"""Telegram push notification support for The Foundry."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    """Send Telegram messages via the Bot API.

    All public methods are fire-and-forget: they catch all exceptions and
    return False on failure so they never block the main triage flow.

    Parameters
    ----------
    token:
        Telegram bot token from BotFather.
    chat_id:
        Target chat or channel ID (string form, e.g. "-1001234567890").
    """

    def __init__(self, token: str, chat_id: str) -> None:
        self._token = token
        self._chat_id = chat_id
        self._url = _TELEGRAM_API.format(token=token)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _post(self, text: str, parse_mode: str = "Markdown") -> bool:
        """POST a message to the Telegram Bot API.

        Returns True on HTTP 200 with ok=true, False on any error.
        """
        payload: dict[str, Any] = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return bool(body.get("ok", False))
        except urllib.error.HTTPError as exc:
            logger.warning("Telegram HTTP error %s: %s", exc.code, exc.reason)
            return False
        except urllib.error.URLError as exc:
            logger.warning("Telegram URL error: %s", exc.reason)
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram unexpected error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_message(self, text: str) -> bool:
        """Send a plain text message. Returns True on success."""
        return self._post(text)

    def notify_review_ready(
        self, task_title: str, project: str, review_tag: str
    ) -> bool:
        """Send notification: new task in review queue."""
        text = (
            "\U0001f514 *Review Ready*\n"
            f"Task: {task_title}\n"
            f"Project: {project}\n"
            f"Tag: {review_tag}"
        )
        return self._post(text)

    def notify_triage_complete(self, entry_summary: str, verdict: str) -> bool:
        """Send notification: triage finished with verdict."""
        verdict_upper = verdict.upper()
        # Pick an emoji that signals the verdict at a glance
        emoji = {
            "KILL": "\U0001f480",   # skull
            "PARK": "\U0001f4a4",   # zzz
            "ADVANCE": "✅",    # green check
        }.get(verdict_upper, "ℹ️")  # info fallback

        text = (
            f"{emoji} *Triage Complete*\n"
            f"Entry: {entry_summary}\n"
            f"Verdict: *{verdict_upper}*"
        )
        return self._post(text)

    def send_daily_digest(self, stats: dict) -> bool:
        """Send daily digest.

        Parameters
        ----------
        stats:
            Expected keys: ``pending_triage``, ``building``,
            ``review_queue``, ``killed_today``.
        """
        pending = stats.get("pending_triage", 0)
        building = stats.get("building", 0)
        review = stats.get("review_queue", 0)
        killed = stats.get("killed_today", 0)

        text = (
            "\U0001f4ca *Daily Digest*\n"
            "\n"
            f"Pending triage:  `{pending}`\n"
            f"Building:        `{building}`\n"
            f"Review queue:    `{review}`\n"
            f"Killed today:    `{killed}`"
        )
        return self._post(text)
