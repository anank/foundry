"""Tests for the Interviewer triage component.

Run with:
    pytest tests/test_interviewer.py

All tests use FakeLLM — no real API calls needed.
"""

from __future__ import annotations

import json
from typing import Optional

import pytest

from foundry.llm.base import LLMResponse, TriageLLM
from foundry.vault.schema import BrainDumpEntry
from foundry.triage.interviewer import Interviewer, InterviewerResponse


# ---------------------------------------------------------------------------
# FakeLLM
# ---------------------------------------------------------------------------


class FakeLLM(TriageLLM):
    """Returns a canned LLMResponse for any analyze() call."""

    def __init__(self, response_text: str) -> None:
        self._response_text = response_text
        self.calls: list[dict] = []

    def analyze(
        self,
        role: str,
        system: str,
        prompt: str,
        max_tokens: int = 2048,
        content_hint: Optional[str] = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "role": role,
                "system": system,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "content_hint": content_hint,
            }
        )
        return LLMResponse(
            text=self._response_text,
            provider="fake",
            model="fake-model",
            input_tokens=10,
            output_tokens=20,
            cost_usd=0.0,
        )


# ---------------------------------------------------------------------------
# Fixtures — brain dump entries
# ---------------------------------------------------------------------------


def _make_entry() -> BrainDumpEntry:
    """A survived idea entry ready for the interviewer."""
    return BrainDumpEntry(
        timestamp="2026-05-26 09:00",
        type="idea",
        content=(
            "build a CLI tool that reads the Multi-Agent Content System's output queue "
            "and auto-posts articles to WordPress via REST API"
        ),
        context="spent 40 minutes manually publishing articles again",
        state="frustrated",
        source="app",
        triage_status="advanced",
    )


# ---------------------------------------------------------------------------
# Canned LLM responses
# ---------------------------------------------------------------------------


def _needs_input_response() -> str:
    return json.dumps({
        "status": "NEEDS_USER_INPUT",
        "question": "What should happen if the WordPress REST API returns an error — retry, skip, or halt?",
        "spec_draft": None,
    })


def _spec_draft_response() -> str:
    return json.dumps({
        "status": "SPEC_DRAFT",
        "question": None,
        "spec_draft": {
            "title": "Auto-publish CLI for Multi-Agent Content System",
            "description": (
                "A CLI tool that reads the content system's output queue and posts "
                "approved articles to WordPress via REST API. Eliminates the 40-minute "
                "weekly manual publishing step."
            ),
            "success_criteria": [
                "Publishes all queued articles within 60 seconds of invocation",
                "Sets correct category, tags, and featured image on each post",
                "Exits with non-zero code and prints error if WordPress API is unreachable",
                "Dry-run flag prints what would be published without making API calls",
            ],
            "demo_script": [
                "Step 1: Add 3 approved articles to the content system output queue",
                "Step 2: Run `foundry publish --dry-run` and verify it lists all 3 articles",
                "Step 3: Run `foundry publish` and verify all 3 appear as published posts in WordPress",
                "Step 4: Verify each post has the correct category, tags, and featured image",
                "Step 5: Simulate WordPress API down — verify CLI exits with code 1 and error message",
            ],
            "files_expected": [
                "foundry/cli.py",
                "foundry/executor/publisher.py",
                "foundry/executor/wordpress_client.py",
                "tests/test_publisher.py",
            ],
            "out_of_scope": [
                "Scheduling or cron — manual invocation only for v1",
                "Multiple WordPress sites — single configured site only",
                "Editing or updating already-published posts",
                "Image upload — featured image must already exist in WordPress media library",
            ],
        },
    })


def _malformed_response() -> str:
    return "This is not JSON at all."


def _fenced_needs_input_response() -> str:
    return "```json\n" + _needs_input_response() + "\n```"


# ---------------------------------------------------------------------------
# Tests: NEEDS_USER_INPUT on first call (empty history)
# ---------------------------------------------------------------------------


class TestInterviewerNeedsInput:
    def test_empty_history_returns_needs_user_input(self):
        llm = FakeLLM(_needs_input_response())
        interviewer = Interviewer(llm)
        result = interviewer.interview(_make_entry(), history=[])
        assert result.status == "NEEDS_USER_INPUT"

    def test_needs_user_input_has_question(self):
        llm = FakeLLM(_needs_input_response())
        interviewer = Interviewer(llm)
        result = interviewer.interview(_make_entry(), history=[])
        assert result.question is not None
        assert len(result.question) > 0

    def test_needs_user_input_spec_draft_is_none(self):
        llm = FakeLLM(_needs_input_response())
        interviewer = Interviewer(llm)
        result = interviewer.interview(_make_entry(), history=[])
        assert result.spec_draft is None

    def test_needs_user_input_returns_interviewer_response_instance(self):
        llm = FakeLLM(_needs_input_response())
        interviewer = Interviewer(llm)
        result = interviewer.interview(_make_entry(), history=[])
        assert isinstance(result, InterviewerResponse)

    def test_fenced_json_is_parsed_correctly(self):
        """LLMs sometimes wrap JSON in ```json ... ``` — must handle gracefully."""
        llm = FakeLLM(_fenced_needs_input_response())
        interviewer = Interviewer(llm)
        result = interviewer.interview(_make_entry(), history=[])
        assert result.status == "NEEDS_USER_INPUT"
        assert result.question is not None


# ---------------------------------------------------------------------------
# Tests: SPEC_DRAFT with full history
# ---------------------------------------------------------------------------


class TestInterviewerSpecDraft:
    def _full_history(self) -> list[dict]:
        return [
            {
                "question": "What should happen if the WordPress REST API returns an error?",
                "answer": "Exit with non-zero code and print the error. Don't retry automatically.",
            },
            {
                "question": "Should the tool support a dry-run mode?",
                "answer": "Yes, a --dry-run flag that lists what would be published without calling the API.",
            },
            {
                "question": "Which files in the existing codebase will this touch?",
                "answer": "foundry/cli.py for the command, and new files under foundry/executor/.",
            },
            {
                "question": "What should explicitly NOT be in scope for v1?",
                "answer": "No scheduling, no multiple sites, no editing existing posts, no image upload.",
            },
        ]

    def test_full_history_returns_spec_draft(self):
        llm = FakeLLM(_spec_draft_response())
        interviewer = Interviewer(llm)
        result = interviewer.interview(_make_entry(), history=self._full_history())
        assert result.status == "SPEC_DRAFT"

    def test_spec_draft_question_is_none(self):
        llm = FakeLLM(_spec_draft_response())
        interviewer = Interviewer(llm)
        result = interviewer.interview(_make_entry(), history=self._full_history())
        assert result.question is None

    def test_spec_draft_is_populated(self):
        llm = FakeLLM(_spec_draft_response())
        interviewer = Interviewer(llm)
        result = interviewer.interview(_make_entry(), history=self._full_history())
        assert result.spec_draft is not None
        assert isinstance(result.spec_draft, dict)

    def test_spec_draft_has_required_keys(self):
        llm = FakeLLM(_spec_draft_response())
        interviewer = Interviewer(llm)
        result = interviewer.interview(_make_entry(), history=self._full_history())
        required = {"title", "description", "success_criteria", "demo_script",
                    "files_expected", "out_of_scope"}
        assert required.issubset(result.spec_draft.keys())

    def test_spec_draft_title_is_string(self):
        llm = FakeLLM(_spec_draft_response())
        interviewer = Interviewer(llm)
        result = interviewer.interview(_make_entry(), history=self._full_history())
        assert isinstance(result.spec_draft["title"], str)
        assert len(result.spec_draft["title"]) > 0

    def test_spec_draft_success_criteria_are_list(self):
        llm = FakeLLM(_spec_draft_response())
        interviewer = Interviewer(llm)
        result = interviewer.interview(_make_entry(), history=self._full_history())
        assert isinstance(result.spec_draft["success_criteria"], list)
        assert len(result.spec_draft["success_criteria"]) >= 2

    def test_spec_draft_demo_script_are_list(self):
        llm = FakeLLM(_spec_draft_response())
        interviewer = Interviewer(llm)
        result = interviewer.interview(_make_entry(), history=self._full_history())
        assert isinstance(result.spec_draft["demo_script"], list)
        assert len(result.spec_draft["demo_script"]) >= 3

    def test_spec_draft_files_expected_are_list(self):
        llm = FakeLLM(_spec_draft_response())
        interviewer = Interviewer(llm)
        result = interviewer.interview(_make_entry(), history=self._full_history())
        assert isinstance(result.spec_draft["files_expected"], list)
        assert len(result.spec_draft["files_expected"]) >= 1

    def test_spec_draft_out_of_scope_are_list(self):
        llm = FakeLLM(_spec_draft_response())
        interviewer = Interviewer(llm)
        result = interviewer.interview(_make_entry(), history=self._full_history())
        assert isinstance(result.spec_draft["out_of_scope"], list)
        assert len(result.spec_draft["out_of_scope"]) >= 2


# ---------------------------------------------------------------------------
# Tests: malformed JSON → raises ValueError
# ---------------------------------------------------------------------------


class TestInterviewerMalformedResponse:
    def test_plain_text_raises_value_error(self):
        llm = FakeLLM(_malformed_response())
        interviewer = Interviewer(llm)
        with pytest.raises(ValueError, match="not valid JSON"):
            interviewer.interview(_make_entry(), history=[])

    def test_truncated_json_raises_value_error(self):
        llm = FakeLLM('{"status": "NEEDS_USER_INPUT"')  # truncated
        interviewer = Interviewer(llm)
        with pytest.raises(ValueError):
            interviewer.interview(_make_entry(), history=[])

    def test_json_missing_status_raises_value_error(self):
        bad = json.dumps({"question": "What is the output format?", "spec_draft": None})
        llm = FakeLLM(bad)
        interviewer = Interviewer(llm)
        with pytest.raises(ValueError):
            interviewer.interview(_make_entry(), history=[])

    def test_empty_string_raises_value_error(self):
        llm = FakeLLM("")
        interviewer = Interviewer(llm)
        with pytest.raises(ValueError):
            interviewer.interview(_make_entry(), history=[])

    def test_invalid_status_value_raises_value_error(self):
        bad = json.dumps({
            "status": "UNKNOWN_STATUS",
            "question": "something",
            "spec_draft": None,
        })
        llm = FakeLLM(bad)
        interviewer = Interviewer(llm)
        with pytest.raises(ValueError):
            interviewer.interview(_make_entry(), history=[])


# ---------------------------------------------------------------------------
# Tests: LLM called with role="interviewer"
# ---------------------------------------------------------------------------


class TestInterviewerLLMCall:
    def test_llm_called_with_interviewer_role(self):
        llm = FakeLLM(_needs_input_response())
        interviewer = Interviewer(llm)
        interviewer.interview(_make_entry(), history=[])
        assert len(llm.calls) == 1
        assert llm.calls[0]["role"] == "interviewer"

    def test_llm_called_exactly_once_per_interview(self):
        llm = FakeLLM(_needs_input_response())
        interviewer = Interviewer(llm)
        interviewer.interview(_make_entry(), history=[])
        assert len(llm.calls) == 1

    def test_llm_prompt_contains_entry_content(self):
        llm = FakeLLM(_needs_input_response())
        interviewer = Interviewer(llm)
        entry = _make_entry()
        interviewer.interview(entry, history=[])
        assert "Multi-Agent Content System" in llm.calls[0]["prompt"]

    def test_llm_prompt_contains_history_questions(self):
        llm = FakeLLM(_spec_draft_response())
        interviewer = Interviewer(llm)
        history = [
            {"question": "What is the error handling strategy?", "answer": "Exit with code 1."}
        ]
        interviewer.interview(_make_entry(), history=history)
        assert "What is the error handling strategy?" in llm.calls[0]["prompt"]

    def test_llm_prompt_contains_history_answers(self):
        llm = FakeLLM(_spec_draft_response())
        interviewer = Interviewer(llm)
        history = [
            {"question": "What is the error handling strategy?", "answer": "Exit with code 1."}
        ]
        interviewer.interview(_make_entry(), history=history)
        assert "Exit with code 1." in llm.calls[0]["prompt"]

    def test_llm_system_prompt_is_set(self):
        llm = FakeLLM(_needs_input_response())
        interviewer = Interviewer(llm)
        interviewer.interview(_make_entry(), history=[])
        assert len(llm.calls[0]["system"]) > 0

    def test_llm_content_hint_is_entry_content(self):
        llm = FakeLLM(_needs_input_response())
        interviewer = Interviewer(llm)
        entry = _make_entry()
        interviewer.interview(entry, history=[])
        assert llm.calls[0]["content_hint"] == entry.content

    def test_empty_history_note_appears_in_prompt(self):
        llm = FakeLLM(_needs_input_response())
        interviewer = Interviewer(llm)
        interviewer.interview(_make_entry(), history=[])
        assert "first turn" in llm.calls[0]["prompt"]
