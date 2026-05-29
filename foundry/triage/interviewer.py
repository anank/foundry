"""Interviewer — triage component for ideas that have survived the Idea Killer.

Conducts a Q&A loop with the user to build a concrete spec. Each call either
returns a clarifying question (NEEDS_USER_INPUT) or a fully populated spec
draft (SPEC_DRAFT) when enough information has been gathered.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

from foundry.llm.base import TriageLLM
from foundry.vault.schema import BrainDumpEntry

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "interviewer.md"


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class InterviewerResponse(BaseModel):
    """Parsed response from the Interviewer LLM call.

    When status is NEEDS_USER_INPUT: question is set, spec_draft is None.
    When status is SPEC_DRAFT: question is None, spec_draft is fully populated.
    """

    status: Literal["SPEC_DRAFT", "NEEDS_USER_INPUT"]
    question: Optional[str] = None
    spec_draft: Optional[dict] = None


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _format_entry(entry: BrainDumpEntry) -> str:
    lines = [
        f"timestamp: {entry.timestamp}",
        f"type: {entry.type}",
    ]
    if entry.project:
        lines.append(f"project: {entry.project}")
    lines.append(f"content: {entry.content}")
    if entry.context:
        lines.append(f"context: {entry.context}")
    if entry.state:
        lines.append(f"state: {entry.state}")
    if entry.source:
        lines.append(f"source: {entry.source}")
    lines.append(f"triage_status: {entry.triage_status}")
    return "\n".join(lines)


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(no prior questions — this is the first turn)"
    parts = []
    for i, qa in enumerate(history, start=1):
        parts.append(f"Q{i}: {qa['question']}")
        parts.append(f"A{i}: {qa['answer']}")
    return "\n".join(parts)


def _build_user_prompt(entry: BrainDumpEntry, history: list[dict]) -> str:
    entry_text = _format_entry(entry)
    history_text = _format_history(history)
    return (
        "BRAIN DUMP ENTRY:\n"
        f"{entry_text}\n\n"
        "CONVERSATION HISTORY:\n"
        f"{history_text}"
    )


# ---------------------------------------------------------------------------
# JSON parser
# ---------------------------------------------------------------------------


def _parse_response(text: str) -> InterviewerResponse:
    """Parse the LLM's JSON response into an InterviewerResponse.

    Strips markdown fences if the model wraps the JSON in them.

    Raises:
        ValueError: If the response is not valid JSON or is missing required fields.
    """
    stripped = text.strip()

    # Strip optional ```json ... ``` or ``` ... ``` fences
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        inner = lines[1:]
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        stripped = "\n".join(inner).strip()

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM response is not valid JSON: {exc}\nRaw response:\n{text}"
        ) from exc

    try:
        return InterviewerResponse(**data)
    except Exception as exc:
        raise ValueError(
            f"LLM response does not match InterviewerResponse schema: {exc}\nData: {data}"
        ) from exc


# ---------------------------------------------------------------------------
# Interviewer class
# ---------------------------------------------------------------------------


class Interviewer:
    """Runs one turn of the interviewer Q&A loop.

    Each call to interview() either asks the next clarifying question or
    returns a complete spec draft, depending on how much information has
    been gathered so far.

    Args:
        llm: A TriageLLM implementation (real dispatcher or FakeLLM in tests).
    """

    def __init__(self, llm: TriageLLM) -> None:
        self._llm = llm

    def interview(
        self,
        entry: BrainDumpEntry,
        history: list[dict],
    ) -> InterviewerResponse:
        """Run one interviewer turn.

        Args:
            entry: The brain dump entry being specced out.
            history: List of prior Q&A pairs, each a dict with keys
                     "question" and "answer". Empty list on the first turn.

        Returns:
            InterviewerResponse with status NEEDS_USER_INPUT (question set,
            spec_draft None) or SPEC_DRAFT (question None, spec_draft populated).

        Raises:
            ValueError: If the LLM response cannot be parsed as a valid
                        InterviewerResponse.
        """
        system = _load_system_prompt()
        prompt = _build_user_prompt(entry, history)

        response = self._llm.analyze(
            role="interviewer",
            system=system,
            prompt=prompt,
            max_tokens=2048,
            content_hint=entry.content,
        )

        return _parse_response(response.text)
