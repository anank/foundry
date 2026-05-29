"""Tests for the Classifier triage component.

Run with:
    pytest tests/test_classifier.py

All tests use FakeLLM — no real API calls needed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest

from foundry.llm.base import LLMResponse, TriageLLM
from foundry.vault.schema import BrainDumpEntry
from foundry.triage.classifier import Classifier, ClassifierResult


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
# Vault helpers
# ---------------------------------------------------------------------------


def _make_vault(tmp_path: Path, projects: list[str] | None = None) -> Path:
    """Create a minimal vault directory with an optional projects/ subdirectory."""
    vault = tmp_path / "vault"
    vault.mkdir()
    if projects:
        projects_dir = vault / "projects"
        projects_dir.mkdir()
        for name in projects:
            (projects_dir / name).mkdir()
    return vault


# ---------------------------------------------------------------------------
# Canned entries
# ---------------------------------------------------------------------------


def _idea_entry() -> BrainDumpEntry:
    """Clean idea entry — no project, type=idea."""
    return BrainDumpEntry(
        timestamp="2026-05-26 09:00",
        type="idea",
        content="build a telegram bot that posts daily equity curve from the EA",
        context="watching MT5 charts, friction of opening laptop",
        state="energized",
        source="app",
        triage_status="pending",
    )


def _feature_no_project_entry() -> BrainDumpEntry:
    """Feature entry with no project set — should trigger ask."""
    return BrainDumpEntry(
        timestamp="2026-05-26 10:00",
        type="feature",
        content="add dark mode to the dashboard",
        context=None,
        state="tired",
        source="app",
        triage_status="pending",
    )


def _feature_not_idea_entry() -> BrainDumpEntry:
    """Mirrors tests/fixtures/brain_dumps/feature_not_idea.md.

    type=idea but project is set and content describes a modification to an
    existing project — classifier should flag for confirmation.
    """
    return BrainDumpEntry(
        timestamp="2026-05-22 13:15",
        type="idea",
        project="pipnesiatest-ea",
        content=(
            "add a trailing stop to the EA — once trade is 15 pips in profit, "
            "move SL to breakeven, then trail at 10 pips behind the high water mark until closed"
        ),
        context=(
            "reviewing last month's trades, saw 3 winners that gave back 20+ pips before hitting TP "
            "— a trailing stop would have captured more"
        ),
        state="energized",
        source="app",
        triage_status="pending",
    )


# ---------------------------------------------------------------------------
# Canned LLM responses
# ---------------------------------------------------------------------------


def _proceed_idea_response() -> str:
    return json.dumps({
        "action": "proceed",
        "type": "idea",
        "project": None,
        "question": None,
        "reasoning": "Valid idea entry with no project field.",
    })


def _ask_feature_no_project_response() -> str:
    return json.dumps({
        "action": "ask",
        "type": "feature",
        "project": None,
        "question": "Which project should this feature be added to?",
        "reasoning": "Feature entries require a project field.",
    })


def _ask_feature_not_idea_response() -> str:
    return json.dumps({
        "action": "ask",
        "type": "feature",
        "project": "pipnesiatest-ea",
        "question": (
            "This looks like a feature for pipnesiatest-ea rather than a new idea. "
            "Should I reclassify it as type: feature for that project?"
        ),
        "reasoning": (
            "Content describes a modification to an existing project but type is idea."
        ),
    })


def _malformed_response() -> str:
    return "This is not JSON at all, just plain text from a confused model."


# ---------------------------------------------------------------------------
# Tests: valid idea entry → proceed
# ---------------------------------------------------------------------------


class TestClassifierProceedIdea:
    def test_valid_idea_returns_proceed(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_proceed_idea_response())
        classifier = Classifier(llm, vault)
        result = classifier.classify(_idea_entry())
        assert result.action == "proceed"

    def test_valid_idea_type_is_idea(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_proceed_idea_response())
        classifier = Classifier(llm, vault)
        result = classifier.classify(_idea_entry())
        assert result.type == "idea"

    def test_valid_idea_project_is_none(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_proceed_idea_response())
        classifier = Classifier(llm, vault)
        result = classifier.classify(_idea_entry())
        assert result.project is None

    def test_valid_idea_question_is_none(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_proceed_idea_response())
        classifier = Classifier(llm, vault)
        result = classifier.classify(_idea_entry())
        assert result.question is None

    def test_valid_idea_reasoning_is_string(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_proceed_idea_response())
        classifier = Classifier(llm, vault)
        result = classifier.classify(_idea_entry())
        assert isinstance(result.reasoning, str)
        assert len(result.reasoning) > 0

    def test_result_is_classifier_result_instance(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_proceed_idea_response())
        classifier = Classifier(llm, vault)
        result = classifier.classify(_idea_entry())
        assert isinstance(result, ClassifierResult)


# ---------------------------------------------------------------------------
# Tests: feature entry with no project → ask
# ---------------------------------------------------------------------------


class TestClassifierAskFeatureNoProject:
    def test_feature_no_project_returns_ask(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_ask_feature_no_project_response())
        classifier = Classifier(llm, vault)
        result = classifier.classify(_feature_no_project_entry())
        assert result.action == "ask"

    def test_feature_no_project_type_is_feature(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_ask_feature_no_project_response())
        classifier = Classifier(llm, vault)
        result = classifier.classify(_feature_no_project_entry())
        assert result.type == "feature"

    def test_feature_no_project_question_is_set(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_ask_feature_no_project_response())
        classifier = Classifier(llm, vault)
        result = classifier.classify(_feature_no_project_entry())
        assert result.question is not None
        assert len(result.question) > 0

    def test_feature_no_project_project_is_none(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_ask_feature_no_project_response())
        classifier = Classifier(llm, vault)
        result = classifier.classify(_feature_no_project_entry())
        assert result.project is None


# ---------------------------------------------------------------------------
# Tests: feature_not_idea fixture → ask
# ---------------------------------------------------------------------------


class TestClassifierFeatureNotIdea:
    def test_feature_not_idea_returns_ask(self, tmp_path):
        vault = _make_vault(tmp_path, projects=["pipnesiatest-ea"])
        llm = FakeLLM(_ask_feature_not_idea_response())
        classifier = Classifier(llm, vault)
        result = classifier.classify(_feature_not_idea_entry())
        assert result.action == "ask"

    def test_feature_not_idea_type_reclassified_to_feature(self, tmp_path):
        vault = _make_vault(tmp_path, projects=["pipnesiatest-ea"])
        llm = FakeLLM(_ask_feature_not_idea_response())
        classifier = Classifier(llm, vault)
        result = classifier.classify(_feature_not_idea_entry())
        assert result.type == "feature"

    def test_feature_not_idea_project_preserved(self, tmp_path):
        vault = _make_vault(tmp_path, projects=["pipnesiatest-ea"])
        llm = FakeLLM(_ask_feature_not_idea_response())
        classifier = Classifier(llm, vault)
        result = classifier.classify(_feature_not_idea_entry())
        assert result.project == "pipnesiatest-ea"

    def test_feature_not_idea_question_mentions_reclassify(self, tmp_path):
        vault = _make_vault(tmp_path, projects=["pipnesiatest-ea"])
        llm = FakeLLM(_ask_feature_not_idea_response())
        classifier = Classifier(llm, vault)
        result = classifier.classify(_feature_not_idea_entry())
        assert result.question is not None
        assert "feature" in result.question.lower()

    def test_feature_not_idea_reasoning_is_string(self, tmp_path):
        vault = _make_vault(tmp_path, projects=["pipnesiatest-ea"])
        llm = FakeLLM(_ask_feature_not_idea_response())
        classifier = Classifier(llm, vault)
        result = classifier.classify(_feature_not_idea_entry())
        assert isinstance(result.reasoning, str)
        assert len(result.reasoning) > 0


# ---------------------------------------------------------------------------
# Tests: malformed LLM response → safe fallback
# ---------------------------------------------------------------------------


class TestClassifierMalformedResponse:
    def test_malformed_returns_ask(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_malformed_response())
        classifier = Classifier(llm, vault)
        result = classifier.classify(_idea_entry())
        assert result.action == "ask"

    def test_malformed_preserves_entry_type(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_malformed_response())
        classifier = Classifier(llm, vault)
        result = classifier.classify(_idea_entry())
        assert result.type == "idea"

    def test_malformed_question_is_set(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_malformed_response())
        classifier = Classifier(llm, vault)
        result = classifier.classify(_idea_entry())
        assert result.question is not None
        assert len(result.question) > 0

    def test_malformed_reasoning_is_parse_error(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_malformed_response())
        classifier = Classifier(llm, vault)
        result = classifier.classify(_idea_entry())
        assert result.reasoning == "parse error"

    def test_truncated_json_returns_ask(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM('{"action": "proceed"')  # truncated
        classifier = Classifier(llm, vault)
        result = classifier.classify(_idea_entry())
        assert result.action == "ask"

    def test_markdown_fenced_json_is_parsed_correctly(self, tmp_path):
        """LLMs sometimes wrap JSON in ```json ... ``` — must handle gracefully."""
        vault = _make_vault(tmp_path)
        fenced = "```json\n" + _proceed_idea_response() + "\n```"
        llm = FakeLLM(fenced)
        classifier = Classifier(llm, vault)
        result = classifier.classify(_idea_entry())
        assert result.action == "proceed"

    def test_markdown_fenced_no_lang_tag_is_parsed_correctly(self, tmp_path):
        vault = _make_vault(tmp_path)
        fenced = "```\n" + _proceed_idea_response() + "\n```"
        llm = FakeLLM(fenced)
        classifier = Classifier(llm, vault)
        result = classifier.classify(_idea_entry())
        assert result.action == "proceed"


# ---------------------------------------------------------------------------
# Tests: LLM called with role="classifier"
# ---------------------------------------------------------------------------


class TestClassifierLLMRole:
    def test_llm_called_with_classifier_role(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_proceed_idea_response())
        classifier = Classifier(llm, vault)
        classifier.classify(_idea_entry())
        assert len(llm.calls) == 1
        assert llm.calls[0]["role"] == "classifier"

    def test_llm_called_exactly_once(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_proceed_idea_response())
        classifier = Classifier(llm, vault)
        classifier.classify(_idea_entry())
        assert len(llm.calls) == 1

    def test_llm_prompt_contains_entry_content(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_proceed_idea_response())
        classifier = Classifier(llm, vault)
        classifier.classify(_idea_entry())
        assert "telegram bot" in llm.calls[0]["prompt"]

    def test_llm_prompt_contains_known_projects(self, tmp_path):
        vault = _make_vault(tmp_path, projects=["pipnesiatest-ea", "ai-ticket-tool"])
        llm = FakeLLM(_proceed_idea_response())
        classifier = Classifier(llm, vault)
        classifier.classify(_idea_entry())
        assert "pipnesiatest-ea" in llm.calls[0]["prompt"]
        assert "ai-ticket-tool" in llm.calls[0]["prompt"]

    def test_llm_system_prompt_is_classifier_md_content(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_proceed_idea_response())
        classifier = Classifier(llm, vault)
        classifier.classify(_idea_entry())
        # The system prompt should contain text from classifier.md
        assert "Classifier" in llm.calls[0]["system"]

    def test_llm_content_hint_is_entry_content(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_proceed_idea_response())
        classifier = Classifier(llm, vault)
        entry = _idea_entry()
        classifier.classify(entry)
        assert llm.calls[0]["content_hint"] == entry.content


# ---------------------------------------------------------------------------
# Tests: known projects discovery
# ---------------------------------------------------------------------------


class TestClassifierKnownProjects:
    def test_no_projects_dir_does_not_raise(self, tmp_path):
        vault = _make_vault(tmp_path)  # no projects dir created
        llm = FakeLLM(_proceed_idea_response())
        classifier = Classifier(llm, vault)
        result = classifier.classify(_idea_entry())
        assert result.action == "proceed"

    def test_projects_listed_in_prompt(self, tmp_path):
        vault = _make_vault(tmp_path, projects=["pipnesiatest-ea"])
        llm = FakeLLM(_proceed_idea_response())
        classifier = Classifier(llm, vault)
        classifier.classify(_idea_entry())
        assert "pipnesiatest-ea" in llm.calls[0]["prompt"]

    def test_underscore_dirs_excluded_from_projects(self, tmp_path):
        vault = _make_vault(tmp_path, projects=["pipnesiatest-ea"])
        # Add an _index directory that should be excluded
        (vault / "projects" / "_index").mkdir()
        llm = FakeLLM(_proceed_idea_response())
        classifier = Classifier(llm, vault)
        classifier.classify(_idea_entry())
        assert "_index" not in llm.calls[0]["prompt"]
