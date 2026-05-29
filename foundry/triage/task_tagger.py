"""Task Tagger — assigns a review tag to each atomized task."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Optional

from foundry.llm.base import TriageLLM
from foundry.triage.atomizer import AtomizedTask


# ---------------------------------------------------------------------------
# Task Tagger
# ---------------------------------------------------------------------------

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "task_tagger.md"

ReviewTag = Literal["behavioral", "output", "code"]


class TaskTagger:
    """Tags each AtomizedTask with a review type.

    Tags:
        behavioral — UI flows, user-facing behavior, Chrome demo required.
        output     — data pipelines, file writers, report generators.
        code       — security, money, production data, auth, access controls.
    """

    def __init__(self, llm: TriageLLM) -> None:
        self._llm = llm
        self._system = _PROMPT_PATH.read_text(encoding="utf-8")

    def tag(
        self,
        task: AtomizedTask,
        content_hint: Optional[str] = None,
    ) -> ReviewTag:
        """Return the review tag for a single AtomizedTask.

        Args:
            task: The atomized task to tag.
            content_hint: Optional string for sensitive content routing.

        Returns:
            One of "behavioral", "output", or "code".

        Raises:
            ValueError: If the LLM returns malformed JSON, an unknown tag,
                or a response missing the required fields.
        """
        prompt = json.dumps(task.model_dump(), ensure_ascii=False, indent=2)

        response = self._llm.analyze(
            role="task_tagger",
            system=self._system,
            prompt=prompt,
            max_tokens=256,
            content_hint=content_hint,
        )

        return self._parse(response.text)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse(text: str) -> ReviewTag:
        """Parse the LLM response into a ReviewTag.

        Raises:
            ValueError: On JSON decode error, missing fields, or unknown tag.
        """
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"TaskTagger: LLM returned invalid JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError(
                f"TaskTagger: expected JSON object, got: {type(data).__name__}"
            )

        if "review_tag" not in data:
            raise ValueError("TaskTagger: response missing 'review_tag' field")

        tag = data["review_tag"]
        valid: tuple[ReviewTag, ...] = ("behavioral", "output", "code")
        if tag not in valid:
            raise ValueError(
                f"TaskTagger: unknown review_tag {tag!r}, must be one of {valid}"
            )

        return tag  # type: ignore[return-value]
