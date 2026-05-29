"""Feature Killer — triage component for brain dump entries of type 'feature'.

Reads the host project's PROJECT.md and tasks/_next.md from the vault,
builds a prompt with the entry and project context, calls the LLM, and
parses the JSON response into a FeatureKillerVerdict.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from foundry.llm.base import TriageLLM
from foundry.vault.schema import BrainDumpEntry, CheckResult, FeatureKillerVerdict

# Path to the prompt template, relative to this file's package root
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "feature_killer.md"


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _read_file_or_none(path: Path) -> Optional[str]:
    """Return file contents as a string, or None if the file does not exist."""
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def _build_user_prompt(
    entry: BrainDumpEntry,
    project_name: str,
    project_md: Optional[str],
    next_md: Optional[str],
    today: str,
) -> str:
    lines: list[str] = []

    lines.append(f"## Feature Entry")
    lines.append(f"timestamp: {entry.timestamp}")
    lines.append(f"type: {entry.type}")
    lines.append(f"project: {project_name}")
    lines.append(f"content: {entry.content}")
    if entry.context:
        lines.append(f"context: {entry.context}")
    if entry.state:
        lines.append(f"state: {entry.state}")

    lines.append("")
    lines.append(f"## Host Project: {project_name}")
    lines.append("")

    if project_md is not None:
        lines.append("### PROJECT.md")
        lines.append(project_md.strip())
    else:
        lines.append("### PROJECT.md")
        lines.append("(file not found)")

    lines.append("")

    if next_md is not None:
        lines.append("### tasks/_next.md")
        lines.append(next_md.strip())
    else:
        lines.append("### tasks/_next.md")
        lines.append("(file not found or empty — no queued tasks)")

    lines.append("")
    lines.append(f"## Today's Date")
    lines.append(today)

    return "\n".join(lines)


def _parse_verdict(text: str) -> FeatureKillerVerdict:
    """Parse the LLM's JSON response into a FeatureKillerVerdict.

    Strips markdown fences if the model wraps the JSON in them.
    Raises ValueError if the JSON is missing required fields or is malformed.
    """
    stripped = text.strip()

    # Strip optional ```json ... ``` fences
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # Drop first line (```json or ```) and last line (```)
        inner_lines = lines[1:]
        if inner_lines and inner_lines[-1].strip() == "```":
            inner_lines = inner_lines[:-1]
        stripped = "\n".join(inner_lines).strip()

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response is not valid JSON: {exc}\nRaw response:\n{text}") from exc

    # Normalise checks: each check value must have "pass" and "reasoning"
    raw_checks: dict = data.get("checks", {})
    checks: dict[str, CheckResult] = {}
    for key, val in raw_checks.items():
        if not isinstance(val, dict):
            raise ValueError(f"Check {key!r} is not a dict: {val!r}")
        checks[key] = CheckResult(**{"pass": val["pass"], "reasoning": val["reasoning"]})

    return FeatureKillerVerdict(
        verdict=data["verdict"],
        checks=checks,
        verdict_reasoning=data["verdict_reasoning"],
        park_revival_condition=data.get("park_revival_condition"),
    )


class FeatureKiller:
    """Runs the feature killer triage on a brain dump entry of type 'feature'.

    Args:
        llm: A TriageLLM implementation (real dispatcher or FakeLLM in tests).
        vault_path: Path to the vault root directory.
    """

    def __init__(self, llm: TriageLLM, vault_path: Path) -> None:
        self._llm = llm
        self._vault_path = vault_path
        self._system = _load_system_prompt()

    def kill(self, entry: BrainDumpEntry) -> FeatureKillerVerdict:
        """Triage a feature entry and return a verdict.

        Reads the host project's PROJECT.md and tasks/_next.md from the vault,
        builds the prompt, calls the LLM, and parses the response.

        Args:
            entry: A BrainDumpEntry with type='feature' and a non-None project field.

        Returns:
            FeatureKillerVerdict with verdict, per-check results, and reasoning.

        Raises:
            ValueError: If entry.project is None or the LLM response cannot be parsed.
        """
        if entry.project is None:
            raise ValueError(
                "FeatureKiller requires entry.project to be set — "
                "the classifier should have caught this before routing here."
            )

        project_name = entry.project
        project_dir = self._vault_path / "projects" / project_name

        project_md = _read_file_or_none(project_dir / "PROJECT.md")
        next_md = _read_file_or_none(project_dir / "tasks" / "_next.md")

        # Use today's date for scope_creep calculation; import here to keep
        # the module testable without mocking at import time.
        from datetime import date
        today = date.today().isoformat()

        prompt = _build_user_prompt(
            entry=entry,
            project_name=project_name,
            project_md=project_md,
            next_md=next_md,
            today=today,
        )

        response = self._llm.analyze(
            role="feature_killer",
            system=self._system,
            prompt=prompt,
            max_tokens=1024,
            content_hint=f"{entry.project} {entry.content}",
        )

        return _parse_verdict(response.text)
