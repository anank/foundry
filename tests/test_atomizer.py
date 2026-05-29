"""Tests for Atomizer and TaskTagger.

Run with:
    pytest tests/test_atomizer.py

All tests use FakeLLM — no real API calls needed.
"""

from __future__ import annotations

import json
from typing import Optional

import pytest

from foundry.llm.base import LLMResponse, TriageLLM
from foundry.triage.atomizer import AtomizedTask, Atomizer
from foundry.triage.task_tagger import TaskTagger


# ---------------------------------------------------------------------------
# FakeLLM
# ---------------------------------------------------------------------------


class FakeLLM(TriageLLM):
    """Returns canned LLMResponse values keyed by role."""

    def __init__(self, responses: dict) -> None:
        self._responses = responses
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
        if role in self._responses:
            return self._responses[role]
        return LLMResponse(
            text="{}",
            provider="fake",
            model="fake-model",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
        )


def _llm_response(text: str) -> LLMResponse:
    return LLMResponse(
        text=text,
        provider="fake",
        model="fake-model",
        input_tokens=10,
        output_tokens=20,
        cost_usd=0.0,
    )


# ---------------------------------------------------------------------------
# Canned payloads
# ---------------------------------------------------------------------------

_TWO_TASKS_JSON = json.dumps({
    "tasks": [
        {
            "title": "Add VaultReader.read_goals method",
            "spec": "Implement read_goals on VaultReader. Parse goals.md bullet list into list[Goal].",
            "acceptance_criteria": [
                "read_goals returns a list of Goal objects",
                "Missing file returns empty list",
            ],
            "files_expected": ["foundry/vault/reader.py", "tests/test_vault.py"],
            "estimated_diff": 75,
            "out_of_scope": ["Caching", "Pagination"],
        },
        {
            "title": "Add VaultWriter.write_task method",
            "spec": "Implement write_task on VaultWriter. Serialise a Task to the project tasks directory.",
            "acceptance_criteria": [
                "File is created at projects/<project>/tasks/<id>-<slug>.md",
                "File contains all non-None Task fields",
            ],
            "files_expected": ["foundry/vault/writer.py", "tests/test_vault.py"],
            "estimated_diff": 110,
            "out_of_scope": ["Git commit", "SQLite index update"],
        },
    ]
})

_ONE_TASK_JSON = json.dumps({
    "tasks": [
        {
            "title": "Implement LiteLLMDispatcher",
            "spec": "Wrap litellm.completion with sensitive routing and audit logging.",
            "acceptance_criteria": [
                "Sensitive content_hint routes to local endpoint",
                "Audit log entry written after each call",
            ],
            "files_expected": ["foundry/llm/dispatcher.py", "tests/test_dispatcher.py"],
            "estimated_diff": 160,
            "out_of_scope": ["Retry logic", "Streaming"],
        }
    ]
})

_BEHAVIORAL_TAG_JSON = json.dumps({
    "review_tag": "behavioral",
    "reasoning": "Task produces HTMX dashboard UI that must be verified by clicking through flows.",
})

_OUTPUT_TAG_JSON = json.dumps({
    "review_tag": "output",
    "reasoning": "Task writes vault markdown files whose correctness is verified by reading them.",
})

_CODE_TAG_JSON = json.dumps({
    "review_tag": "code",
    "reasoning": "Task handles API key routing and sensitive content — full code review required.",
})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_spec() -> dict:
    return {
        "title": "Vault Reader/Writer",
        "description": "Read and write all vault file types.",
        "tech_spec": "Python, Pydantic v2, pathlib.",
        "mvp_definition": "All vault file types round-trip correctly.",
        "acceptance_criteria": ["All read/write methods pass tests"],
        "files_expected": ["foundry/vault/reader.py", "foundry/vault/writer.py"],
    }


@pytest.fixture()
def sample_task() -> AtomizedTask:
    return AtomizedTask(
        title="Add VaultReader.read_goals method",
        spec="Implement read_goals on VaultReader.",
        acceptance_criteria=["Returns list of Goal objects", "Missing file returns empty list"],
        files_expected=["foundry/vault/reader.py"],
        estimated_diff=75,
        out_of_scope=["Caching"],
    )


# ---------------------------------------------------------------------------
# Atomizer tests
# ---------------------------------------------------------------------------


class TestAtomizerParsesTasksCorrectly:
    def test_returns_list_of_atomized_tasks(self, sample_spec: dict):
        llm = FakeLLM({"atomizer": _llm_response(_TWO_TASKS_JSON)})
        atomizer = Atomizer(llm)
        tasks = atomizer.atomize(sample_spec)

        assert isinstance(tasks, list)
        assert len(tasks) == 2
        assert all(isinstance(t, AtomizedTask) for t in tasks)

    def test_task_fields_populated_correctly(self, sample_spec: dict):
        llm = FakeLLM({"atomizer": _llm_response(_TWO_TASKS_JSON)})
        tasks = Atomizer(llm).atomize(sample_spec)

        t0 = tasks[0]
        assert t0.title == "Add VaultReader.read_goals method"
        assert "read_goals" in t0.spec
        assert t0.estimated_diff == 75
        assert "foundry/vault/reader.py" in t0.files_expected
        assert "tests/test_vault.py" in t0.files_expected
        assert len(t0.acceptance_criteria) == 2
        assert "Caching" in t0.out_of_scope

    def test_second_task_fields(self, sample_spec: dict):
        llm = FakeLLM({"atomizer": _llm_response(_TWO_TASKS_JSON)})
        tasks = Atomizer(llm).atomize(sample_spec)

        t1 = tasks[1]
        assert t1.title == "Add VaultWriter.write_task method"
        assert t1.estimated_diff == 110
        assert "Git commit" in t1.out_of_scope

    def test_single_task_returned(self, sample_spec: dict):
        llm = FakeLLM({"atomizer": _llm_response(_ONE_TASK_JSON)})
        tasks = Atomizer(llm).atomize(sample_spec)

        assert len(tasks) == 1
        assert tasks[0].title == "Implement LiteLLMDispatcher"

    def test_calls_llm_with_correct_role(self, sample_spec: dict):
        llm = FakeLLM({"atomizer": _llm_response(_TWO_TASKS_JSON)})
        Atomizer(llm).atomize(sample_spec)

        assert len(llm.calls) == 1
        assert llm.calls[0]["role"] == "atomizer"

    def test_prompt_contains_spec_title(self, sample_spec: dict):
        llm = FakeLLM({"atomizer": _llm_response(_TWO_TASKS_JSON)})
        Atomizer(llm).atomize(sample_spec)

        assert "Vault Reader/Writer" in llm.calls[0]["prompt"]

    def test_content_hint_forwarded(self, sample_spec: dict):
        llm = FakeLLM({"atomizer": _llm_response(_ONE_TASK_JSON)})
        Atomizer(llm).atomize(sample_spec, content_hint="trading")

        assert llm.calls[0]["content_hint"] == "trading"

    def test_no_content_hint_by_default(self, sample_spec: dict):
        llm = FakeLLM({"atomizer": _llm_response(_ONE_TASK_JSON)})
        Atomizer(llm).atomize(sample_spec)

        assert llm.calls[0]["content_hint"] is None

    def test_empty_tasks_list_is_valid(self, sample_spec: dict):
        payload = json.dumps({"tasks": []})
        llm = FakeLLM({"atomizer": _llm_response(payload)})
        tasks = Atomizer(llm).atomize(sample_spec)

        assert tasks == []


class TestAtomizerMalformedJSON:
    def test_raises_on_invalid_json(self, sample_spec: dict):
        llm = FakeLLM({"atomizer": _llm_response("not json at all")})
        with pytest.raises(ValueError, match="invalid JSON"):
            Atomizer(llm).atomize(sample_spec)

    def test_raises_on_missing_tasks_key(self, sample_spec: dict):
        payload = json.dumps({"result": []})
        llm = FakeLLM({"atomizer": _llm_response(payload)})
        with pytest.raises(ValueError, match="'tasks' key"):
            Atomizer(llm).atomize(sample_spec)

    def test_raises_on_tasks_not_a_list(self, sample_spec: dict):
        payload = json.dumps({"tasks": "not a list"})
        llm = FakeLLM({"atomizer": _llm_response(payload)})
        with pytest.raises(ValueError, match="must be a list"):
            Atomizer(llm).atomize(sample_spec)

    def test_raises_on_task_missing_required_field(self, sample_spec: dict):
        # estimated_diff is required — omit it
        payload = json.dumps({
            "tasks": [
                {
                    "title": "Some task",
                    "spec": "Do something.",
                    # estimated_diff missing
                }
            ]
        })
        llm = FakeLLM({"atomizer": _llm_response(payload)})
        with pytest.raises(ValueError, match="task\\[0\\] failed validation"):
            Atomizer(llm).atomize(sample_spec)

    def test_raises_on_bare_list_response(self, sample_spec: dict):
        payload = json.dumps([{"title": "task"}])
        llm = FakeLLM({"atomizer": _llm_response(payload)})
        with pytest.raises(ValueError):
            Atomizer(llm).atomize(sample_spec)


# ---------------------------------------------------------------------------
# TaskTagger tests
# ---------------------------------------------------------------------------


class TestTaskTaggerTagsCorrectly:
    def test_returns_behavioral_tag(self, sample_task: AtomizedTask):
        llm = FakeLLM({"task_tagger": _llm_response(_BEHAVIORAL_TAG_JSON)})
        tag = TaskTagger(llm).tag(sample_task)

        assert tag == "behavioral"

    def test_returns_output_tag(self, sample_task: AtomizedTask):
        llm = FakeLLM({"task_tagger": _llm_response(_OUTPUT_TAG_JSON)})
        tag = TaskTagger(llm).tag(sample_task)

        assert tag == "output"

    def test_returns_code_tag(self, sample_task: AtomizedTask):
        llm = FakeLLM({"task_tagger": _llm_response(_CODE_TAG_JSON)})
        tag = TaskTagger(llm).tag(sample_task)

        assert tag == "code"

    def test_calls_llm_with_correct_role(self, sample_task: AtomizedTask):
        llm = FakeLLM({"task_tagger": _llm_response(_OUTPUT_TAG_JSON)})
        TaskTagger(llm).tag(sample_task)

        assert len(llm.calls) == 1
        assert llm.calls[0]["role"] == "task_tagger"

    def test_prompt_contains_task_title(self, sample_task: AtomizedTask):
        llm = FakeLLM({"task_tagger": _llm_response(_OUTPUT_TAG_JSON)})
        TaskTagger(llm).tag(sample_task)

        assert sample_task.title in llm.calls[0]["prompt"]

    def test_content_hint_forwarded(self, sample_task: AtomizedTask):
        llm = FakeLLM({"task_tagger": _llm_response(_CODE_TAG_JSON)})
        TaskTagger(llm).tag(sample_task, content_hint="trading")

        assert llm.calls[0]["content_hint"] == "trading"

    def test_no_content_hint_by_default(self, sample_task: AtomizedTask):
        llm = FakeLLM({"task_tagger": _llm_response(_OUTPUT_TAG_JSON)})
        TaskTagger(llm).tag(sample_task)

        assert llm.calls[0]["content_hint"] is None


class TestTaskTaggerMalformedJSON:
    def test_raises_on_invalid_json(self, sample_task: AtomizedTask):
        llm = FakeLLM({"task_tagger": _llm_response("not json")})
        with pytest.raises(ValueError, match="invalid JSON"):
            TaskTagger(llm).tag(sample_task)

    def test_raises_on_missing_review_tag_field(self, sample_task: AtomizedTask):
        payload = json.dumps({"reasoning": "some reason"})
        llm = FakeLLM({"task_tagger": _llm_response(payload)})
        with pytest.raises(ValueError, match="missing 'review_tag'"):
            TaskTagger(llm).tag(sample_task)

    def test_raises_on_unknown_tag_value(self, sample_task: AtomizedTask):
        payload = json.dumps({"review_tag": "manual", "reasoning": "unknown"})
        llm = FakeLLM({"task_tagger": _llm_response(payload)})
        with pytest.raises(ValueError, match="unknown review_tag"):
            TaskTagger(llm).tag(sample_task)

    def test_raises_on_non_object_response(self, sample_task: AtomizedTask):
        payload = json.dumps(["behavioral"])
        llm = FakeLLM({"task_tagger": _llm_response(payload)})
        with pytest.raises(ValueError, match="expected JSON object"):
            TaskTagger(llm).tag(sample_task)


# ---------------------------------------------------------------------------
# Integration: atomize then tag
# ---------------------------------------------------------------------------


class TestAtomizeThenTag:
    def test_each_task_gets_tagged(self, sample_spec: dict):
        atomizer_llm = FakeLLM({"atomizer": _llm_response(_TWO_TASKS_JSON)})
        tasks = Atomizer(atomizer_llm).atomize(sample_spec)

        tagger_llm = FakeLLM({"task_tagger": _llm_response(_OUTPUT_TAG_JSON)})
        tagger = TaskTagger(tagger_llm)

        tags = [tagger.tag(t) for t in tasks]

        assert len(tags) == 2
        assert all(tag == "output" for tag in tags)
        assert len(tagger_llm.calls) == 2

    def test_different_tags_per_task(self, sample_spec: dict):
        atomizer_llm = FakeLLM({"atomizer": _llm_response(_TWO_TASKS_JSON)})
        tasks = Atomizer(atomizer_llm).atomize(sample_spec)

        # Return different tags on successive calls
        call_count = 0
        tag_sequence = [_BEHAVIORAL_TAG_JSON, _CODE_TAG_JSON]

        class SequencedFakeLLM(TriageLLM):
            def analyze(self, role, system, prompt, max_tokens=2048, content_hint=None):
                nonlocal call_count
                text = tag_sequence[call_count % len(tag_sequence)]
                call_count += 1
                return _llm_response(text)

        tagger = TaskTagger(SequencedFakeLLM())
        tags = [tagger.tag(t) for t in tasks]

        assert tags[0] == "behavioral"
        assert tags[1] == "code"
