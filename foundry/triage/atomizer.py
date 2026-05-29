"""Atomizer — splits a locked spec into ≤200-line independently reviewable tasks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from foundry.llm.base import TriageLLM


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


class AtomizedTask(BaseModel):
    """A single task produced by the Atomizer."""

    title: str
    spec: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    files_expected: list[str] = Field(default_factory=list)
    estimated_diff: int
    out_of_scope: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Atomizer
# ---------------------------------------------------------------------------

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "atomizer.md"


class Atomizer:
    """Splits a locked spec dict into a list of AtomizedTask objects.

    Each task is ≤200 lines of expected diff and independently reviewable.
    """

    def __init__(self, llm: TriageLLM) -> None:
        self._llm = llm
        self._system = _PROMPT_PATH.read_text(encoding="utf-8")

    def atomize(
        self,
        spec_draft: dict,
        content_hint: Optional[str] = None,
    ) -> list[AtomizedTask]:
        """Split spec_draft into a list of AtomizedTask objects.

        Args:
            spec_draft: Dict with keys title, description, tech_spec,
                mvp_definition, acceptance_criteria, files_expected.
            content_hint: Optional string for sensitive content routing
                (passed through to the LLM dispatcher unchanged).

        Returns:
            List of AtomizedTask, ordered so dependencies come first.

        Raises:
            ValueError: If the LLM returns malformed JSON or the JSON does
                not match the expected schema.
        """
        prompt = json.dumps(spec_draft, ensure_ascii=False, indent=2)

        response = self._llm.analyze(
            role="atomizer",
            system=self._system,
            prompt=prompt,
            max_tokens=4096,
            content_hint=content_hint,
        )

        return self._parse(response.text)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse(text: str) -> list[AtomizedTask]:
        """Parse the LLM response text into a list of AtomizedTask.

        Raises:
            ValueError: On JSON decode error or schema mismatch.
        """
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Atomizer: LLM returned invalid JSON: {exc}") from exc

        if not isinstance(data, dict) or "tasks" not in data:
            raise ValueError(
                f"Atomizer: expected JSON object with 'tasks' key, got: {type(data).__name__}"
            )

        raw_tasks = data["tasks"]
        if not isinstance(raw_tasks, list):
            raise ValueError(
                f"Atomizer: 'tasks' must be a list, got: {type(raw_tasks).__name__}"
            )

        tasks: list[AtomizedTask] = []
        for i, raw in enumerate(raw_tasks):
            try:
                tasks.append(AtomizedTask.model_validate(raw))
            except Exception as exc:
                raise ValueError(f"Atomizer: task[{i}] failed validation: {exc}") from exc

        return tasks
