"""Shared helper to build a LiteLLMDispatcher from the DB."""

from __future__ import annotations

import os
from pathlib import Path

from foundry.llm.dispatcher import LiteLLMDispatcher


def get_dispatcher() -> LiteLLMDispatcher:
    return LiteLLMDispatcher.from_db()


def get_db_path() -> Path:
    raw = os.environ.get("FOUNDRY_DB_PATH", "")
    if raw:
        return Path(raw)
    return Path.home() / ".foundry" / "foundry.db"
