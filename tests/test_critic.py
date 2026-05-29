"""Tests for the Critic triage component.

Run with:
    pytest tests/test_critic.py

All tests use FakeLLM — no real API calls needed.
"""

from __future__ import annotations

import json
from typing import Optional

import pytest

from foundry.llm.base import LLMResponse, TriageLLM
from foundry.triage.critic import Critic, CriticResponse, CriticStatus


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
            {"role": role, "system": system, "prompt": prompt, "content_hint": content_hint}
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
# Fixtures
# ---------------------------------------------------------------------------


def _make_strong_spec() -> dict:
    """A spec that satisfies all three LOCKED conditions."""
    return {
        "title": "Add /health endpoint to FastAPI dashboard",
        "spec": (
            "Add a GET /health endpoint to the FastAPI dashboard app. "
            "The endpoint must return HTTP 200 with a JSON body "
            '{"status": "ok", "version": "<semver from pyproject.toml>"}. '
            "No authentication required. The version is read once at startup "
            "and cached for the lifetime of the process."
        ),
        "acceptance_criteria": [
            'GET /health returns HTTP 200.',
            'Response body is valid JSON with keys "status" and "version".',
            '"status" value is exactly the string "ok".',
            '"version" matches the version field in pyproject.toml.',
            "Endpoint responds in under 50ms on the VPS (measured with curl -w '%{time_total}').",
        ],
        "demo_script": (
            "1. Start the dashboard with `uvicorn foundry.dashboard.app:app --port 8000`.\n"
            "2. Run `curl -s http://localhost:8000/health`.\n"
            '3. Observe: HTTP 200, body contains \'"status": "ok"\' and a semver string for "version".\n'
            "4. Stop the server."
        ),
        "out_of_scope": [
            "No authentication or API key on this endpoint.",
            "No database connectivity check.",
            "No dependency version reporting beyond the app version.",
        ],
        "files_expected": [
            "foundry/dashboard/app.py",
            "foundry/dashboard/routes/health.py",
        ],
    }


def _make_weak_spec() -> dict:
    """A spec with vague acceptance criteria and missing demo script."""
    return {
        "title": "Improve dashboard performance",
        "spec": (
            "Make the dashboard faster. Users have complained it feels slow. "
            "Optimize the queries and make sure the UI is responsive."
        ),
        "acceptance_criteria": [
            "Dashboard loads faster.",
            "Queries are optimized.",
            "UI feels responsive on mobile.",
        ],
        "out_of_scope": [
            "Keep it simple.",
        ],
        "files_expected": [],
    }


def _locked_response() -> str:
    return json.dumps({
        "status": "LOCKED",
        "gaps": [],
        "questions": [],
        "reasoning": (
            "The spec is fully buildable: every requirement is unambiguous, "
            "all acceptance criteria are measurable with automated tests, "
            "and the demo script is executable step-by-step."
        ),
    })


def _return_response() -> str:
    return json.dumps({
        "status": "RETURN",
        "gaps": [
            "Acceptance criterion 'Dashboard loads faster' has no numeric baseline or target — "
            "it cannot be verified with a test.",
            "Acceptance criterion 'Queries are optimized' does not specify which queries, "
            "what optimization means, or how to measure it.",
            "Acceptance criterion 'UI feels responsive on mobile' requires human judgment — "
            "no specific breakpoint, device, or interaction latency is defined.",
            "Out-of-scope item 'Keep it simple' is not specific enough to prevent scope creep — "
            "a developer could add caching, CDN integration, or a rewrite and consider it in scope.",
            "No demo script provided. The task affects user-visible behavior and requires one.",
        ],
        "questions": [
            "What is the current baseline load time for the dashboard, and what is the target? "
            "(e.g. 'currently 3s, target under 1s on a 4G connection')",
            "Which specific queries are slow? Please list the endpoints or database operations "
            "that need optimization.",
            "What does 'responsive on mobile' mean concretely? "
            "Which breakpoint (e.g. 375px), which interactions, and what latency threshold?",
            "What is explicitly out of scope? "
            "(e.g. 'no CDN changes', 'no schema migrations', 'no frontend framework changes')",
            "Please provide a demo script: which page to open, what action to take, "
            "and what the measurable expected result is?",
        ],
        "reasoning": (
            "All three LOCKED conditions fail. Acceptance criteria are unmeasurable — "
            "none can be verified without human judgment. The out-of-scope list is too vague "
            "to prevent drift. No demo script exists for a behavioral task."
        ),
    })


# ---------------------------------------------------------------------------
# Tests: strong spec → LOCKED
# ---------------------------------------------------------------------------


class TestCriticLocked:
    def test_strong_spec_returns_locked_status(self):
        llm = FakeLLM(_locked_response())
        critic = Critic(llm)
        result = critic.review(_make_strong_spec())
        assert result.status == "LOCKED"

    def test_locked_response_has_empty_gaps(self):
        llm = FakeLLM(_locked_response())
        critic = Critic(llm)
        result = critic.review(_make_strong_spec())
        assert result.gaps == []

    def test_locked_response_has_empty_questions(self):
        llm = FakeLLM(_locked_response())
        critic = Critic(llm)
        result = critic.review(_make_strong_spec())
        assert result.questions == []

    def test_locked_response_has_reasoning(self):
        llm = FakeLLM(_locked_response())
        critic = Critic(llm)
        result = critic.review(_make_strong_spec())
        assert isinstance(result.reasoning, str)
        assert len(result.reasoning) > 0

    def test_llm_called_with_critic_role(self):
        llm = FakeLLM(_locked_response())
        critic = Critic(llm)
        critic.review(_make_strong_spec())
        assert len(llm.calls) == 1
        assert llm.calls[0]["role"] == "critic"

    def test_llm_prompt_contains_spec_title(self):
        llm = FakeLLM(_locked_response())
        critic = Critic(llm)
        critic.review(_make_strong_spec())
        assert "Add /health endpoint" in llm.calls[0]["prompt"]

    def test_llm_prompt_contains_acceptance_criteria(self):
        llm = FakeLLM(_locked_response())
        critic = Critic(llm)
        critic.review(_make_strong_spec())
        assert "Acceptance Criteria" in llm.calls[0]["prompt"]

    def test_llm_prompt_contains_demo_script(self):
        llm = FakeLLM(_locked_response())
        critic = Critic(llm)
        critic.review(_make_strong_spec())
        assert "Demo Script" in llm.calls[0]["prompt"]

    def test_result_is_critic_response_instance(self):
        llm = FakeLLM(_locked_response())
        critic = Critic(llm)
        result = critic.review(_make_strong_spec())
        assert isinstance(result, CriticResponse)


# ---------------------------------------------------------------------------
# Tests: weak spec → RETURN with gaps
# ---------------------------------------------------------------------------


class TestCriticReturn:
    def test_weak_spec_returns_return_status(self):
        llm = FakeLLM(_return_response())
        critic = Critic(llm)
        result = critic.review(_make_weak_spec())
        assert result.status == "RETURN"

    def test_return_response_has_gaps(self):
        llm = FakeLLM(_return_response())
        critic = Critic(llm)
        result = critic.review(_make_weak_spec())
        assert len(result.gaps) > 0

    def test_return_response_has_questions(self):
        llm = FakeLLM(_return_response())
        critic = Critic(llm)
        result = critic.review(_make_weak_spec())
        assert len(result.questions) > 0

    def test_return_gaps_are_strings(self):
        llm = FakeLLM(_return_response())
        critic = Critic(llm)
        result = critic.review(_make_weak_spec())
        for gap in result.gaps:
            assert isinstance(gap, str)
            assert len(gap) > 0

    def test_return_questions_are_strings(self):
        llm = FakeLLM(_return_response())
        critic = Critic(llm)
        result = critic.review(_make_weak_spec())
        for question in result.questions:
            assert isinstance(question, str)
            assert len(question) > 0

    def test_return_reasoning_mentions_failure(self):
        llm = FakeLLM(_return_response())
        critic = Critic(llm)
        result = critic.review(_make_weak_spec())
        # Reasoning should explain why it failed, not just say "ok"
        assert len(result.reasoning) > 20

    def test_gaps_reference_vague_criteria(self):
        llm = FakeLLM(_return_response())
        critic = Critic(llm)
        result = critic.review(_make_weak_spec())
        combined = " ".join(result.gaps).lower()
        # At least one gap should call out the unmeasurable criteria
        assert "measur" in combined or "numeric" in combined or "baseline" in combined or "judgment" in combined

    def test_questions_are_actionable(self):
        llm = FakeLLM(_return_response())
        critic = Critic(llm)
        result = critic.review(_make_weak_spec())
        # Each question should end with "?" — they are questions, not statements
        for question in result.questions:
            assert "?" in question


# ---------------------------------------------------------------------------
# Tests: malformed JSON → raises ValueError
# ---------------------------------------------------------------------------


class TestCriticMalformedResponse:
    def test_plain_text_raises_value_error(self):
        llm = FakeLLM("This is not JSON at all.")
        critic = Critic(llm)
        with pytest.raises(ValueError, match="non-JSON"):
            critic.review(_make_strong_spec())

    def test_partial_json_raises_value_error(self):
        llm = FakeLLM('{"status": "LOCKED"')  # truncated
        critic = Critic(llm)
        with pytest.raises(ValueError):
            critic.review(_make_strong_spec())

    def test_json_missing_required_field_raises_value_error(self):
        # Valid JSON but missing "reasoning"
        bad = json.dumps({"status": "LOCKED", "gaps": [], "questions": []})
        llm = FakeLLM(bad)
        critic = Critic(llm)
        with pytest.raises(ValueError, match="schema"):
            critic.review(_make_strong_spec())

    def test_invalid_status_value_raises_value_error(self):
        bad = json.dumps({
            "status": "MAYBE",  # not a valid CriticStatus
            "gaps": [],
            "questions": [],
            "reasoning": "some reasoning",
        })
        llm = FakeLLM(bad)
        critic = Critic(llm)
        with pytest.raises(ValueError, match="schema"):
            critic.review(_make_strong_spec())

    def test_markdown_fenced_json_is_parsed_correctly(self):
        """LLMs sometimes wrap JSON in ```json ... ``` — must handle gracefully."""
        fenced = "```json\n" + _locked_response() + "\n```"
        llm = FakeLLM(fenced)
        critic = Critic(llm)
        result = critic.review(_make_strong_spec())
        assert result.status == "LOCKED"

    def test_markdown_fenced_no_lang_tag_is_parsed_correctly(self):
        fenced = "```\n" + _locked_response() + "\n```"
        llm = FakeLLM(fenced)
        critic = Critic(llm)
        result = critic.review(_make_strong_spec())
        assert result.status == "LOCKED"

    def test_empty_string_raises_value_error(self):
        llm = FakeLLM("")
        critic = Critic(llm)
        with pytest.raises(ValueError):
            critic.review(_make_strong_spec())


# ---------------------------------------------------------------------------
# Tests: prompt construction edge cases
# ---------------------------------------------------------------------------


class TestCriticPromptConstruction:
    def test_spec_without_demo_script_omits_demo_section(self):
        spec = _make_weak_spec()  # no demo_script key
        llm = FakeLLM(_return_response())
        critic = Critic(llm)
        critic.review(spec)
        assert "Demo Script" not in llm.calls[0]["prompt"]

    def test_spec_with_demo_script_includes_demo_section(self):
        spec = _make_strong_spec()  # has demo_script
        llm = FakeLLM(_locked_response())
        critic = Critic(llm)
        critic.review(spec)
        assert "Demo Script" in llm.calls[0]["prompt"]

    def test_empty_spec_dict_still_calls_llm(self):
        llm = FakeLLM(_locked_response())
        critic = Critic(llm)
        critic.review({})
        assert len(llm.calls) == 1

    def test_out_of_scope_items_appear_in_prompt(self):
        spec = _make_strong_spec()
        llm = FakeLLM(_locked_response())
        critic = Critic(llm)
        critic.review(spec)
        assert "Out of Scope" in llm.calls[0]["prompt"]
        assert "No authentication" in llm.calls[0]["prompt"]

    def test_files_expected_appear_in_prompt(self):
        spec = _make_strong_spec()
        llm = FakeLLM(_locked_response())
        critic = Critic(llm)
        critic.review(spec)
        assert "Files Expected" in llm.calls[0]["prompt"]
        assert "foundry/dashboard/app.py" in llm.calls[0]["prompt"]
