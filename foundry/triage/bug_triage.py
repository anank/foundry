"""Bug Triage — triage component for brain dump entries of type 'bug'.

Assesses reproducibility, impact, workaround availability, and severity.
Reproducible bugs are written directly to the host project's task queue.
Critical bugs get a CRITICAL- prefix on their task id.
Non-reproducible bugs are returned with severity='low' and a note asking
for more information — no task is written.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from foundry.llm.base import TriageLLM
from foundry.vault.schema import BrainDumpEntry, BugTriageResult, Task
from foundry.vault.writer import VaultWriter

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "bug_triage.md"


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _build_user_prompt(entry: BrainDumpEntry) -> str:
    lines: list[str] = []
    lines.append("## Bug Report")
    lines.append(f"timestamp: {entry.timestamp}")
    lines.append(f"type: {entry.type}")
    if entry.project:
        lines.append(f"project: {entry.project}")
    lines.append(f"content: {entry.content}")
    if entry.context:
        lines.append(f"context: {entry.context}")
    if entry.state:
        lines.append(f"state: {entry.state}")
    return "\n".join(lines)


def _parse_result(text: str) -> BugTriageResult:
    """Parse the LLM's JSON response into a BugTriageResult.

    Strips markdown fences if the model wraps the JSON in them.
    Raises ValueError if the JSON is missing required fields or is malformed.
    """
    stripped = text.strip()

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

    return BugTriageResult(
        reproducible=data["reproducible"],
        impact=data["impact"],
        workaround_exists=data["workaround_exists"],
        severity=data["severity"],
        notes=data["notes"],
    )


def _next_task_id(tasks_dir: Path, prefix: str) -> str:
    """Return the next available numeric task id, optionally with a prefix.

    Scans existing task files (NNN-*.md) to find the highest numeric id,
    then returns prefix + str(highest + 1) zero-padded to 3 digits.
    If no tasks exist, starts at 1.
    """
    highest = 0
    if tasks_dir.exists():
        for f in tasks_dir.iterdir():
            # Match both plain "001-slug.md" and prefixed "CRITICAL-001-slug.md"
            m = re.search(r"(?:^|-)(\d{3})-", f.name)
            if m:
                n = int(m.group(1))
                if n > highest:
                    highest = n
    numeric = f"{highest + 1:03d}"
    return f"{prefix}{numeric}" if prefix else numeric


def _slugify_title(content: str) -> str:
    """Derive a short task title from the bug content."""
    # Take first sentence or first 60 chars, whichever is shorter
    first = content.split(".")[0].strip()
    if len(first) > 60:
        first = first[:60].rsplit(" ", 1)[0]
    return first or "bug fix"


class BugTriager:
    """Runs bug triage on a brain dump entry of type 'bug'.

    Args:
        llm: A TriageLLM implementation (real dispatcher or FakeLLM in tests).
        vault_path: Path to the vault root directory.
    """

    def __init__(self, llm: TriageLLM, vault_path: Path) -> None:
        self._llm = llm
        self._vault_path = vault_path
        self._system = _load_system_prompt()
        self._writer = VaultWriter(vault_path)

    def triage(self, entry: BrainDumpEntry) -> BugTriageResult:
        """Triage a bug entry and return a BugTriageResult.

        If the bug is not reproducible, returns a result with severity='low'
        and notes asking for more information. No task is written.

        If the bug is reproducible, writes a task spec to the host project's
        task queue via VaultWriter. Critical bugs get a 'CRITICAL-' prefix on
        their task id.

        Args:
            entry: A BrainDumpEntry with type='bug'.

        Returns:
            BugTriageResult with reproducibility, impact, workaround, severity,
            and notes.

        Raises:
            ValueError: If the LLM response cannot be parsed.
        """
        prompt = _build_user_prompt(entry)

        response = self._llm.analyze(
            role="bug_triage",
            system=self._system,
            prompt=prompt,
            max_tokens=1024,
            content_hint=f"{entry.project or ''} {entry.content}",
        )

        result = _parse_result(response.text)

        if not result.reproducible:
            # Do not queue — return as-is with low severity and info request
            return result

        # Reproducible: write task to project queue
        project = entry.project or "unknown"
        tasks_dir = self._vault_path / "projects" / project / "tasks"

        id_prefix = "CRITICAL-" if result.severity == "critical" else ""
        task_id = _next_task_id(tasks_dir, id_prefix)

        title = _slugify_title(entry.content)

        spec_lines = [
            f"**Bug report:** {entry.content}",
        ]
        if entry.context:
            spec_lines.append(f"\n**Context:** {entry.context}")
        spec_lines.append(f"\n**Impact:** {result.impact}")
        spec_lines.append(f"**Severity:** {result.severity}")
        spec_lines.append(f"**Workaround exists:** {result.workaround_exists}")
        spec_lines.append(f"\n**Triage notes:** {result.notes}")

        task = Task(
            id=task_id,
            title=title,
            status="queued",
            project=project,
            review_tag="code",
            created=date.today(),
            spec_locked=True,
            spec="\n".join(spec_lines),
            acceptance_criteria=[
                "Bug is no longer reproducible following the fix.",
                "Existing tests pass.",
            ],
            out_of_scope=[
                "Refactoring unrelated code.",
                "Adding new features.",
            ],
        )

        self._writer.write_task(project=project, task=task)

        return result
