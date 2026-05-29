"""Idea Killer — triage component for brain dump entries of type 'idea'.

Reads goals.md, existing-systems.md, and principles.md from the vault,
builds a prompt with the entry and vault context, calls the LLM, and
parses the JSON response into an IdeaKillerVerdict.

On KILL or PARK verdicts the graveyard file is written via VaultWriter.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from foundry.llm.base import TriageLLM
from foundry.vault.schema import BrainDumpEntry, CheckResult, IdeaKillerVerdict
from foundry.vault.writer import VaultWriter

# Prompt template lives next to the other prompts
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "idea_killer.md"


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _read_file_or_fallback(path: Path, label: str) -> str:
    """Return file contents, or a clear placeholder if the file is missing."""
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"({label} not found at {path})"


def _build_user_prompt(
    entry: BrainDumpEntry,
    goals: str,
    existing_systems: str,
    principles: str,
) -> str:
    """Render the prompt template with the entry and vault context."""
    template = _load_system_prompt()
    # Format the entry as the same key:value block used in brain-dump files
    entry_lines = [
        f"## {entry.timestamp}",
        f"type: {entry.type}",
    ]
    if entry.project:
        entry_lines.append(f"project: {entry.project}")
    entry_lines.append(f"content: {entry.content}")
    if entry.context:
        entry_lines.append(f"context: {entry.context}")
    if entry.state:
        entry_lines.append(f"state: {entry.state}")
    if entry.source:
        entry_lines.append(f"source: {entry.source}")
    entry_lines.append(f"triage_status: {entry.triage_status}")
    entry_text = "\n".join(entry_lines)

    return (
        template
        .replace("{entry}", entry_text)
        .replace("{goals}", goals.strip())
        .replace("{existing_systems}", existing_systems.strip())
        .replace("{principles}", principles.strip())
    )


def _parse_verdict(text: str) -> IdeaKillerVerdict:
    """Parse the LLM's JSON response into an IdeaKillerVerdict.

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

    # Normalise checks: each value must have "pass" and "reasoning"
    raw_checks: dict = data.get("checks", {})
    checks: dict[str, CheckResult] = {}
    for key, val in raw_checks.items():
        if not isinstance(val, dict):
            raise ValueError(f"Check {key!r} is not a dict: {val!r}")
        try:
            checks[key] = CheckResult(**{"pass": val["pass"], "reasoning": val["reasoning"]})
        except KeyError as exc:
            raise ValueError(
                f"Check {key!r} is missing field {exc}: {val!r}"
            ) from exc

    try:
        return IdeaKillerVerdict(
            verdict=data["verdict"],
            checks=checks,
            verdict_reasoning=data["verdict_reasoning"],
            park_revival_condition=data.get("park_revival_condition"),
            related_killed_ideas=data.get("related_killed_ideas", []),
        )
    except KeyError as exc:
        raise ValueError(f"LLM response missing required field {exc}") from exc


def _idea_title(entry: BrainDumpEntry) -> str:
    """Derive a short title from the entry content for graveyard filenames."""
    # Take the first 60 characters of content, up to the first sentence boundary
    content = entry.content.strip()
    for sep in (".", "—", "-", ","):
        idx = content.find(sep)
        if 10 < idx < 60:
            return content[:idx].strip()
    return content[:60].strip()


class IdeaKiller:
    """Runs the idea killer triage on a brain dump entry of type 'idea'.

    Args:
        llm: A TriageLLM implementation (real dispatcher or FakeLLM in tests).
        vault_path: Path to the vault root directory.
    """

    def __init__(self, llm: TriageLLM, vault_path: Path) -> None:
        self._llm = llm
        self._vault_path = Path(vault_path)
        self._writer = VaultWriter(self._vault_path)

    def _load_vault_context(self) -> dict[str, str]:
        """Read goals.md, existing-systems.md, and principles.md from the vault.

        Returns a dict with keys 'goals', 'existing_systems', 'principles'.
        Missing files produce a clear placeholder string rather than raising.
        """
        return {
            "goals": _read_file_or_fallback(
                self._vault_path / "goals.md", "goals.md"
            ),
            "existing_systems": _read_file_or_fallback(
                self._vault_path / "existing-systems.md", "existing-systems.md"
            ),
            "principles": _read_file_or_fallback(
                self._vault_path / "principles.md", "principles.md"
            ),
        }

    def kill(self, entry: BrainDumpEntry) -> IdeaKillerVerdict:
        """Triage an idea entry and return a verdict.

        Reads vault context, builds the prompt, calls the LLM, parses the
        response, and writes a graveyard file for KILL or PARK verdicts.

        Args:
            entry: A BrainDumpEntry with type='idea'.

        Returns:
            IdeaKillerVerdict with verdict, per-check results, and reasoning.

        Raises:
            ValueError: If the LLM response cannot be parsed as a valid verdict.
        """
        ctx = self._load_vault_context()

        prompt = _build_user_prompt(
            entry=entry,
            goals=ctx["goals"],
            existing_systems=ctx["existing_systems"],
            principles=ctx["principles"],
        )

        response = self._llm.analyze(
            role="idea_killer",
            system="",  # system prompt is embedded in the template
            prompt=prompt,
            max_tokens=1024,
            content_hint=entry.content,
        )

        verdict = _parse_verdict(response.text)

        # Write graveyard file for killed or parked ideas
        if verdict.verdict in ("KILL", "PARK"):
            title = _idea_title(entry)
            self._writer.write_graveyard(
                idea_title=title,
                verdict=verdict,
                original_entry=entry,
            )

        return verdict
