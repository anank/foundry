"""Critic — adversarial spec review.

Receives a spec_draft dict and returns LOCKED or RETURN with specific gaps
and questions for the Interviewer to resolve.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from foundry.llm.base import TriageLLM


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

CriticStatus = Literal["LOCKED", "RETURN"]


class CriticResponse(BaseModel):
    model_config = {"populate_by_name": True}

    status: CriticStatus
    gaps: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    reasoning: str


# ---------------------------------------------------------------------------
# Critic
# ---------------------------------------------------------------------------

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "critic.md"


class Critic:
    """Adversarial spec reviewer.

    Calls the LLM with the critic system prompt and the provided spec_draft,
    then parses the structured JSON response into a CriticResponse.
    """

    def __init__(self, llm: TriageLLM) -> None:
        self._llm = llm
        self._system = _PROMPT_PATH.read_text(encoding="utf-8")

    def review(self, spec_draft: dict) -> CriticResponse:
        """Review a spec draft and return LOCKED or RETURN with gaps.

        Args:
            spec_draft: The draft spec as a dict. Expected keys mirror the
                        Task model: spec, acceptance_criteria, out_of_scope,
                        files_expected, and optionally demo_script.

        Returns:
            CriticResponse with status, gaps, questions, and reasoning.

        Raises:
            ValueError: If the LLM returns malformed or unparseable JSON.
        """
        prompt = _build_prompt(spec_draft)

        response = self._llm.analyze(
            role="critic",
            system=self._system,
            prompt=prompt,
            max_tokens=2048,
        )

        return _parse_response(response.text)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_prompt(spec_draft: dict) -> str:
    """Render the spec_draft into a prompt string for the LLM."""
    lines = ["Review the following spec draft and return your verdict as JSON.\n"]

    if spec_draft.get("title"):
        lines.append(f"## Title\n{spec_draft['title']}\n")

    if spec_draft.get("spec"):
        lines.append(f"## Spec\n{spec_draft['spec']}\n")

    acceptance = spec_draft.get("acceptance_criteria", [])
    if acceptance:
        lines.append("## Acceptance Criteria")
        for criterion in acceptance:
            lines.append(f"- {criterion}")
        lines.append("")

    demo = spec_draft.get("demo_script")
    if demo:
        lines.append(f"## Demo Script\n{demo}\n")

    out_of_scope = spec_draft.get("out_of_scope", [])
    if out_of_scope:
        lines.append("## Out of Scope")
        for item in out_of_scope:
            lines.append(f"- {item}")
        lines.append("")

    files_expected = spec_draft.get("files_expected", [])
    if files_expected:
        lines.append("## Files Expected to Change")
        for f in files_expected:
            lines.append(f"- {f}")
        lines.append("")

    lines.append(
        'Return only a JSON object with keys: "status", "gaps", "questions", "reasoning".'
    )

    return "\n".join(lines)


def _parse_response(text: str) -> CriticResponse:
    """Parse the LLM text response into a CriticResponse.

    Strips markdown code fences if present, then parses JSON.

    Raises:
        ValueError: If the text cannot be parsed as valid JSON or does not
                    match the CriticResponse schema.
    """
    cleaned = text.strip()

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        # Drop first line (```json or ```) and last line (```)
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        cleaned = "\n".join(inner).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Critic LLM returned non-JSON response: {exc}\nRaw text: {text!r}"
        ) from exc

    try:
        return CriticResponse.model_validate(data)
    except Exception as exc:
        raise ValueError(
            f"Critic LLM response did not match expected schema: {exc}\nParsed data: {data!r}"
        ) from exc
