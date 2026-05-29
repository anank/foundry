"""Classifier — first step in The Foundry triage pipeline.

Validates the type field of a brain dump entry and ensures it has the
information needed to route it to the right killer. Never guesses when
ambiguous — always asks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

from foundry.llm.base import TriageLLM
from foundry.vault.schema import BrainDumpEntry

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "classifier.md"


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


class ClassifierResult(BaseModel):
    action: Literal["proceed", "ask"]
    type: Literal["idea", "feature", "bug"]
    project: Optional[str] = None
    question: Optional[str] = None
    reasoning: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _list_known_projects(vault_path: Path) -> list[str]:
    """Return subdirectory names under vault_path/projects/ as known project names.

    Returns an empty list if the projects directory does not exist.
    """
    projects_dir = vault_path / "projects"
    if not projects_dir.exists():
        return []
    return [
        p.name
        for p in projects_dir.iterdir()
        if p.is_dir() and not p.name.startswith("_")
    ]


def _build_user_prompt(entry: BrainDumpEntry, known_projects: list[str]) -> str:
    """Render the user-facing prompt with the entry fields and known project list."""
    lines = [
        f"## {entry.timestamp}",
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

    entry_text = "\n".join(lines)

    if known_projects:
        projects_text = "\n".join(f"- {p}" for p in sorted(known_projects))
    else:
        projects_text = "(no projects found in vault)"

    return (
        f"Known projects:\n{projects_text}\n\n"
        f"Brain dump entry:\n{entry_text}"
    )


def _strip_fences(text: str) -> str:
    """Strip optional ```json ... ``` or ``` ... ``` fences from LLM output."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        inner = lines[1:]
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        stripped = "\n".join(inner).strip()
    return stripped


def _parse_result(text: str) -> ClassifierResult:
    """Parse the LLM's JSON response into a ClassifierResult.

    Raises:
        ValueError: If the response is not valid JSON or is missing required fields.
    """
    cleaned = _strip_fences(text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM response is not valid JSON: {exc}\nRaw response:\n{text}"
        ) from exc

    try:
        return ClassifierResult(
            action=data["action"],
            type=data["type"],
            project=data.get("project"),
            question=data.get("question"),
            reasoning=data["reasoning"],
        )
    except KeyError as exc:
        raise ValueError(f"LLM response missing required field {exc}") from exc


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class Classifier:
    """Validates and routes a brain dump entry by type.

    Args:
        llm: A TriageLLM implementation (real dispatcher or FakeLLM in tests).
        vault_path: Path to the vault root directory.
    """

    def __init__(self, llm: TriageLLM, vault_path: Path) -> None:
        self._llm = llm
        self._vault_path = Path(vault_path)

    def classify(self, entry: BrainDumpEntry) -> ClassifierResult:
        """Classify a brain dump entry.

        Lists known projects from the vault, builds the prompt, calls the LLM,
        and parses the JSON response into a ClassifierResult.

        On any parse failure returns a safe fallback ClassifierResult with
        action="ask" so the entry is never silently misrouted.

        Args:
            entry: A BrainDumpEntry to classify.

        Returns:
            ClassifierResult with action, type, project, question, and reasoning.
        """
        known_projects = _list_known_projects(self._vault_path)
        system = _load_system_prompt()
        prompt = _build_user_prompt(entry, known_projects)

        response = self._llm.analyze(
            role="classifier",
            system=system,
            prompt=prompt,
            max_tokens=256,
            content_hint=entry.content,
        )

        try:
            return _parse_result(response.text)
        except (ValueError, KeyError, TypeError):
            return ClassifierResult(
                action="ask",
                type=entry.type,
                project=None,
                question=(
                    "Could not parse classifier response. "
                    "Please clarify your entry type."
                ),
                reasoning="parse error",
            )
