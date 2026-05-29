"""Tests for the Coordinator triage pipeline orchestrator.

All tests use FakeLLM — no real API calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest

from foundry.llm.base import LLMResponse, TriageLLM
from foundry.triage.coordinator import Coordinator, TriageResult
from foundry.vault.schema import BrainDumpEntry


# ---------------------------------------------------------------------------
# FakeLLM
# ---------------------------------------------------------------------------


class FakeLLM(TriageLLM):
    """Returns canned responses keyed by role. Falls back to default."""

    def __init__(self, responses: dict[str, str], default: str = "{}") -> None:
        self._responses = responses
        self._default = default
        self.calls: list[dict] = []

    def analyze(
        self,
        role: str,
        system: str,
        prompt: str,
        max_tokens: int = 2048,
        content_hint: Optional[str] = None,
    ) -> LLMResponse:
        self.calls.append({"role": role})
        text = self._responses.get(role, self._default)
        return LLMResponse(
            text=text,
            provider="fake",
            model="fake-model",
            input_tokens=10,
            output_tokens=20,
            cost_usd=0.0,
        )


# ---------------------------------------------------------------------------
# Canned JSON responses
# ---------------------------------------------------------------------------

CLASSIFIER_PROCEED_IDEA = json.dumps({
    "action": "proceed",
    "type": "idea",
    "project": None,
    "question": None,
    "reasoning": "Clearly an idea.",
})

CLASSIFIER_PROCEED_FEATURE = json.dumps({
    "action": "proceed",
    "type": "feature",
    "project": "my-project",
    "question": None,
    "reasoning": "Clearly a feature.",
})

CLASSIFIER_PROCEED_BUG = json.dumps({
    "action": "proceed",
    "type": "bug",
    "project": "my-project",
    "question": None,
    "reasoning": "Clearly a bug.",
})

CLASSIFIER_ASK = json.dumps({
    "action": "ask",
    "type": "idea",
    "project": None,
    "question": "Is this an idea or a feature?",
    "reasoning": "Ambiguous.",
})

IDEA_KILLER_KILL = json.dumps({
    "verdict": "KILL",
    "checks": {
        "goal_anchor":      {"pass": False, "reasoning": "No goal alignment."},
        "existing_overlap": {"pass": True,  "reasoning": "No overlap."},
        "manual_baseline":  {"pass": True,  "reasoning": "Passes baseline."},
        "killshot":         {"pass": False, "reasoning": "Fatal flaw found."},
        "existence_test":   {"pass": True,  "reasoning": "Would use it."},
    },
    "verdict_reasoning": "Killed: no goal alignment and fatal flaw.",
    "park_revival_condition": None,
    "related_killed_ideas": [],
})

IDEA_KILLER_PARK = json.dumps({
    "verdict": "PARK",
    "checks": {
        "goal_anchor":      {"pass": True,  "reasoning": "Aligns with goals."},
        "existing_overlap": {"pass": True,  "reasoning": "No overlap."},
        "manual_baseline":  {"pass": False, "reasoning": "Could do manually."},
        "killshot":         {"pass": True,  "reasoning": "No fatal flaw."},
        "existence_test":   {"pass": True,  "reasoning": "Would use it."},
    },
    "verdict_reasoning": "Parked: not the right time.",
    "park_revival_condition": "Revisit after shipping v1.",
    "related_killed_ideas": [],
})

IDEA_KILLER_ADVANCE = json.dumps({
    "verdict": "ADVANCE",
    "checks": {
        "goal_anchor":      {"pass": True, "reasoning": "Aligns."},
        "existing_overlap": {"pass": True, "reasoning": "No overlap."},
        "manual_baseline":  {"pass": True, "reasoning": "Passes."},
        "killshot":         {"pass": True, "reasoning": "No flaw."},
        "existence_test":   {"pass": True, "reasoning": "Would use."},
    },
    "verdict_reasoning": "Advance: all checks pass.",
    "park_revival_condition": None,
    "related_killed_ideas": [],
})

FEATURE_KILLER_KILL = json.dumps({
    "verdict": "KILL",
    "checks": {
        "mvp_exists":       {"pass": True,  "reasoning": "MVP exists."},
        "roadmap_conflict": {"pass": False, "reasoning": "Conflicts with roadmap."},
        "scope_creep":      {"pass": False, "reasoning": "Scope creep."},
        "killshot":         {"pass": False, "reasoning": "Fatal flaw."},
    },
    "verdict_reasoning": "Killed: scope creep.",
    "park_revival_condition": None,
})

FEATURE_KILLER_ADVANCE = json.dumps({
    "verdict": "ADVANCE",
    "checks": {
        "mvp_exists":       {"pass": True, "reasoning": "MVP exists."},
        "roadmap_conflict": {"pass": True, "reasoning": "No conflict."},
        "scope_creep":      {"pass": True, "reasoning": "No creep."},
        "killshot":         {"pass": True, "reasoning": "No flaw."},
    },
    "verdict_reasoning": "Advance.",
    "park_revival_condition": None,
})

BUG_TRIAGE_REPRODUCIBLE = json.dumps({
    "reproducible": True,
    "severity": "high",
    "impact": "wrong_output",
    "workaround_exists": False,
    "notes": "Reproducible on every run.",
})

BUG_TRIAGE_NOT_REPRODUCIBLE = json.dumps({
    "reproducible": False,
    "severity": "low",
    "impact": "annoyance",
    "workaround_exists": True,
    "notes": "Cannot reproduce — need more info.",
})

INTERVIEWER_NEEDS_INPUT = json.dumps({
    "status": "NEEDS_USER_INPUT",
    "question": "What problem does this solve?",
    "spec_draft": None,
})

INTERVIEWER_SPEC_DRAFT = json.dumps({
    "status": "SPEC_DRAFT",
    "question": None,
    "spec_draft": {
        "title": "Test Project",
        "problem": "A real problem.",
        "solution": "A real solution.",
        "success_criteria": ["Works end to end."],
        "out_of_scope": [],
    },
})

CRITIC_RETURN = json.dumps({
    "status": "RETURN",
    "reasoning": "Spec has gaps.",
    "gaps": ["Missing success criteria."],
    "questions": ["What does success look like?"],
})

CRITIC_LOCKED = json.dumps({
    "status": "LOCKED",
    "reasoning": "Spec is solid.",
    "gaps": [],
    "questions": [],
})

ATOMIZER_TASKS = json.dumps({
    "tasks": [
        {
            "title": "Task 1",
            "spec": "Do the first thing.",
            "acceptance_criteria": ["It works."],
            "out_of_scope": [],
            "files_expected": ["src/thing.py"],
            "estimated_diff": 50,
        }
    ]
})

TASK_TAGGER_CODE = json.dumps({"review_tag": "code"})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def vault_path(tmp_path: Path) -> Path:
    """Minimal vault structure."""
    (tmp_path / "brain-dump").mkdir()
    (tmp_path / "graveyard").mkdir()
    (tmp_path / "projects").mkdir()
    (tmp_path / "triage").mkdir()
    (tmp_path / "pipeline").mkdir()
    # Minimal models.yaml so VaultReader doesn't error
    (tmp_path / "models.yaml").write_text(
        "default_model: fake-model\nroles: {}\nsensitive_overrides:\n  patterns: []\n  local_endpoint: http://localhost:11434\n"
    )
    return tmp_path


def _entry(type_: str = "idea", project: Optional[str] = None) -> BrainDumpEntry:
    return BrainDumpEntry(
        timestamp="2026-05-26 10:00",
        type=type_,
        project=project,
        content="A brain dump entry for testing.",
    )


# ---------------------------------------------------------------------------
# Classifier routing
# ---------------------------------------------------------------------------


def test_classifier_ask_returns_needs_input(vault_path: Path) -> None:
    llm = FakeLLM({"classifier": CLASSIFIER_ASK})
    result = Coordinator(llm, vault_path).run(_entry())
    assert result.status == "needs_input"
    assert "idea or a feature" in result.message


# ---------------------------------------------------------------------------
# Idea path
# ---------------------------------------------------------------------------


def test_idea_killed(vault_path: Path) -> None:
    llm = FakeLLM({
        "classifier": CLASSIFIER_PROCEED_IDEA,
        "idea_killer": IDEA_KILLER_KILL,
    })
    result = Coordinator(llm, vault_path).run(_entry("idea"))
    assert result.status == "killed"
    assert result.verdict is not None
    assert result.tasks == []


def test_idea_parked(vault_path: Path) -> None:
    llm = FakeLLM({
        "classifier": CLASSIFIER_PROCEED_IDEA,
        "idea_killer": IDEA_KILLER_PARK,
    })
    result = Coordinator(llm, vault_path).run(_entry("idea"))
    assert result.status == "parked"
    assert result.tasks == []


def test_idea_advance_interviewer_needs_input(vault_path: Path) -> None:
    llm = FakeLLM({
        "classifier": CLASSIFIER_PROCEED_IDEA,
        "idea_killer": IDEA_KILLER_ADVANCE,
        "interviewer": INTERVIEWER_NEEDS_INPUT,
    })
    result = Coordinator(llm, vault_path).run(_entry("idea"))
    assert result.status == "needs_input"
    assert "What problem" in result.message


def test_idea_advance_critic_returns_gaps(vault_path: Path) -> None:
    llm = FakeLLM({
        "classifier": CLASSIFIER_PROCEED_IDEA,
        "idea_killer": IDEA_KILLER_ADVANCE,
        "interviewer": INTERVIEWER_SPEC_DRAFT,
        "critic": CRITIC_RETURN,
    })
    result = Coordinator(llm, vault_path).run(_entry("idea"))
    assert result.status == "needs_input"
    assert "gaps" in result.message.lower() or "Gaps" in result.message


def test_idea_advance_full_pipeline_writes_tasks(vault_path: Path) -> None:
    llm = FakeLLM({
        "classifier": CLASSIFIER_PROCEED_IDEA,
        "idea_killer": IDEA_KILLER_ADVANCE,
        "interviewer": INTERVIEWER_SPEC_DRAFT,
        "critic": CRITIC_LOCKED,
        "atomizer": ATOMIZER_TASKS,
        "task_tagger": TASK_TAGGER_CODE,
    })
    result = Coordinator(llm, vault_path).run(_entry("idea"))
    assert result.status == "advanced"
    assert len(result.tasks) == 1
    assert result.tasks[0].title == "Task 1"
    # Task file should exist on disk
    project = result.tasks[0].project
    tasks_dir = vault_path / "projects" / project / "tasks"
    assert any(tasks_dir.iterdir())


def test_idea_advance_with_interview_history(vault_path: Path) -> None:
    """Second call with history should skip to spec draft."""
    llm = FakeLLM({
        "classifier": CLASSIFIER_PROCEED_IDEA,
        "idea_killer": IDEA_KILLER_ADVANCE,
        "interviewer": INTERVIEWER_SPEC_DRAFT,
        "critic": CRITIC_LOCKED,
        "atomizer": ATOMIZER_TASKS,
        "task_tagger": TASK_TAGGER_CODE,
    })
    history = [{"question": "What problem?", "answer": "A real problem."}]
    result = Coordinator(llm, vault_path).run(_entry("idea"), interview_history=history)
    assert result.status == "advanced"


# ---------------------------------------------------------------------------
# Feature path
# ---------------------------------------------------------------------------


def test_feature_killed(vault_path: Path) -> None:
    llm = FakeLLM({
        "classifier": CLASSIFIER_PROCEED_FEATURE,
        "feature_killer": FEATURE_KILLER_KILL,
    })
    result = Coordinator(llm, vault_path).run(_entry("feature", project="my-project"))
    assert result.status == "killed"
    assert result.tasks == []


def test_feature_advanced_writes_task(vault_path: Path) -> None:
    llm = FakeLLM({
        "classifier": CLASSIFIER_PROCEED_FEATURE,
        "feature_killer": FEATURE_KILLER_ADVANCE,
    })
    result = Coordinator(llm, vault_path).run(_entry("feature", project="my-project"))
    assert result.status == "advanced"
    assert len(result.tasks) == 1


# ---------------------------------------------------------------------------
# Bug path
# ---------------------------------------------------------------------------


def test_bug_not_reproducible_returns_needs_input(vault_path: Path) -> None:
    llm = FakeLLM({
        "classifier": CLASSIFIER_PROCEED_BUG,
        "bug_triage": BUG_TRIAGE_NOT_REPRODUCIBLE,
    })
    result = Coordinator(llm, vault_path).run(_entry("bug", project="my-project"))
    assert result.status == "needs_input"


def test_bug_reproducible_writes_task(vault_path: Path) -> None:
    llm = FakeLLM({
        "classifier": CLASSIFIER_PROCEED_BUG,
        "bug_triage": BUG_TRIAGE_REPRODUCIBLE,
    })
    result = Coordinator(llm, vault_path).run(_entry("bug", project="my-project"))
    assert result.status == "advanced"
    assert len(result.tasks) == 1


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_classifier_error_returns_error_status(vault_path: Path) -> None:
    class BrokenLLM(TriageLLM):
        def analyze(self, role, system, prompt, max_tokens=2048, content_hint=None):
            raise RuntimeError("LLM exploded")

    result = Coordinator(BrokenLLM(), vault_path).run(_entry())
    assert result.status == "error"
    assert "Classifier failed" in result.message


def test_idea_killer_error_returns_error_status(vault_path: Path) -> None:
    call_count = 0

    class PartialLLM(TriageLLM):
        def analyze(self, role, system, prompt, max_tokens=2048, content_hint=None):
            nonlocal call_count
            call_count += 1
            if role == "classifier":
                return LLMResponse(
                    text=CLASSIFIER_PROCEED_IDEA,
                    provider="fake", model="fake", input_tokens=1, output_tokens=1, cost_usd=0.0,
                )
            raise RuntimeError("killer exploded")

    result = Coordinator(PartialLLM(), vault_path).run(_entry())
    assert result.status == "error"
    assert "IdeaKiller failed" in result.message
