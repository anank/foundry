"""Tests for the BugTriager triage component.

Run with:
    pytest tests/test_bug_triage.py

All tests use FakeLLM — no real API calls needed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import pytest

from foundry.llm.base import LLMResponse, TriageLLM
from foundry.triage.bug_triage import BugTriager
from foundry.vault.schema import BrainDumpEntry, BugTriageResult


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
# Canned LLM responses
# ---------------------------------------------------------------------------


def _critical_response() -> str:
    return json.dumps({
        "reproducible": True,
        "impact": "data_loss",
        "workaround_exists": False,
        "severity": "critical",
        "notes": (
            "Trade log file is overwritten on every EA restart. "
            "No workaround — all historical trade data is permanently lost."
        ),
    })


def _not_reproducible_response() -> str:
    return json.dumps({
        "reproducible": False,
        "impact": "annoyance",
        "workaround_exists": False,
        "severity": "low",
        "notes": (
            "Cannot reproduce from description. "
            "Please provide: exact steps to trigger the issue, "
            "what you expected to happen, and what actually happened."
        ),
    })


def _low_severity_with_workaround_response() -> str:
    return json.dumps({
        "reproducible": True,
        "impact": "wrong_output",
        "workaround_exists": True,
        "severity": "low",
        "notes": (
            "Equity curve calculation is wrong when spread filter is active. "
            "Workaround: disable spread filter. Severity reduced from high to low."
        ),
    })


def _high_severity_no_workaround_response() -> str:
    return json.dumps({
        "reproducible": True,
        "impact": "wrong_output",
        "workaround_exists": False,
        "severity": "high",
        "notes": "Dashboard shows incorrect equity values. No workaround available.",
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bug_entry(
    content: str = "EA overwrites trade log on every restart",
    project: str = "pipnesiatest-ea",
    context: Optional[str] = None,
) -> BrainDumpEntry:
    return BrainDumpEntry(
        timestamp="2026-05-26 14:00",
        type="bug",
        project=project,
        content=content,
        context=context,
        state="frustrated",
        source="app",
        triage_status="pending",
    )


def _setup_vault(tmp_path: Path, project: str = "pipnesiatest-ea") -> Path:
    """Create minimal vault structure for tests."""
    project_dir = tmp_path / "projects" / project
    project_dir.mkdir(parents=True)
    tasks_dir = project_dir / "tasks"
    tasks_dir.mkdir()
    return tmp_path


def _list_task_files(tmp_path: Path, project: str = "pipnesiatest-ea") -> list[Path]:
    tasks_dir = tmp_path / "projects" / project / "tasks"
    if not tasks_dir.exists():
        return []
    return sorted(tasks_dir.glob("*.md"))


# ---------------------------------------------------------------------------
# Tests: critical bug → task written with CRITICAL- prefix
# ---------------------------------------------------------------------------


class TestCriticalBug:
    def test_critical_bug_writes_task_file(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_critical_response())
        triager = BugTriager(llm, vault)
        triager.triage(_make_bug_entry())
        files = _list_task_files(tmp_path)
        assert len(files) == 1

    def test_critical_bug_task_id_has_critical_prefix(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_critical_response())
        triager = BugTriager(llm, vault)
        triager.triage(_make_bug_entry())
        files = _list_task_files(tmp_path)
        assert files[0].name.startswith("CRITICAL-")

    def test_critical_bug_returns_critical_severity(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_critical_response())
        triager = BugTriager(llm, vault)
        result = triager.triage(_make_bug_entry())
        assert result.severity == "critical"

    def test_critical_bug_returns_bug_triage_result(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_critical_response())
        triager = BugTriager(llm, vault)
        result = triager.triage(_make_bug_entry())
        assert isinstance(result, BugTriageResult)

    def test_critical_bug_result_is_reproducible(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_critical_response())
        triager = BugTriager(llm, vault)
        result = triager.triage(_make_bug_entry())
        assert result.reproducible is True

    def test_critical_bug_task_file_contains_severity(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_critical_response())
        triager = BugTriager(llm, vault)
        triager.triage(_make_bug_entry())
        files = _list_task_files(tmp_path)
        content = files[0].read_text(encoding="utf-8")
        assert "critical" in content.lower()

    def test_critical_bug_task_file_contains_bug_content(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_critical_response())
        triager = BugTriager(llm, vault)
        entry = _make_bug_entry(content="EA overwrites trade log on every restart")
        triager.triage(entry)
        files = _list_task_files(tmp_path)
        content = files[0].read_text(encoding="utf-8")
        assert "EA overwrites trade log" in content

    def test_llm_called_with_bug_triage_role(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_critical_response())
        triager = BugTriager(llm, vault)
        triager.triage(_make_bug_entry())
        assert len(llm.calls) == 1
        assert llm.calls[0]["role"] == "bug_triage"


# ---------------------------------------------------------------------------
# Tests: not reproducible → no task written, notes ask for more info
# ---------------------------------------------------------------------------


class TestNotReproducible:
    def test_not_reproducible_writes_no_task(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_not_reproducible_response())
        triager = BugTriager(llm, vault)
        triager.triage(_make_bug_entry(content="sometimes it crashes"))
        files = _list_task_files(tmp_path)
        assert len(files) == 0

    def test_not_reproducible_returns_low_severity(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_not_reproducible_response())
        triager = BugTriager(llm, vault)
        result = triager.triage(_make_bug_entry(content="sometimes it crashes"))
        assert result.severity == "low"

    def test_not_reproducible_result_flag_is_false(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_not_reproducible_response())
        triager = BugTriager(llm, vault)
        result = triager.triage(_make_bug_entry(content="sometimes it crashes"))
        assert result.reproducible is False

    def test_not_reproducible_notes_ask_for_info(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_not_reproducible_response())
        triager = BugTriager(llm, vault)
        result = triager.triage(_make_bug_entry(content="sometimes it crashes"))
        # Notes must ask for more information, not just say "ok"
        notes_lower = result.notes.lower()
        assert any(
            phrase in notes_lower
            for phrase in ["provide", "steps", "reproduce", "expected", "happened", "please"]
        )

    def test_not_reproducible_returns_bug_triage_result(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_not_reproducible_response())
        triager = BugTriager(llm, vault)
        result = triager.triage(_make_bug_entry(content="sometimes it crashes"))
        assert isinstance(result, BugTriageResult)

    def test_not_reproducible_tasks_dir_stays_empty(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_not_reproducible_response())
        triager = BugTriager(llm, vault)
        triager.triage(_make_bug_entry(content="sometimes it crashes"))
        tasks_dir = tmp_path / "projects" / "pipnesiatest-ea" / "tasks"
        assert list(tasks_dir.iterdir()) == []


# ---------------------------------------------------------------------------
# Tests: low severity with workaround → severity stays low
# ---------------------------------------------------------------------------


class TestLowSeverityWithWorkaround:
    def test_workaround_bug_severity_is_low(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_low_severity_with_workaround_response())
        triager = BugTriager(llm, vault)
        result = triager.triage(_make_bug_entry(content="equity curve wrong with spread filter"))
        assert result.severity == "low"

    def test_workaround_bug_workaround_flag_is_true(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_low_severity_with_workaround_response())
        triager = BugTriager(llm, vault)
        result = triager.triage(_make_bug_entry(content="equity curve wrong with spread filter"))
        assert result.workaround_exists is True

    def test_workaround_bug_is_reproducible(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_low_severity_with_workaround_response())
        triager = BugTriager(llm, vault)
        result = triager.triage(_make_bug_entry(content="equity curve wrong with spread filter"))
        assert result.reproducible is True

    def test_workaround_bug_still_writes_task(self, tmp_path):
        # Reproducible bugs always get a task, even if low severity
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_low_severity_with_workaround_response())
        triager = BugTriager(llm, vault)
        triager.triage(_make_bug_entry(content="equity curve wrong with spread filter"))
        files = _list_task_files(tmp_path)
        assert len(files) == 1

    def test_workaround_bug_task_has_no_critical_prefix(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_low_severity_with_workaround_response())
        triager = BugTriager(llm, vault)
        triager.triage(_make_bug_entry(content="equity curve wrong with spread filter"))
        files = _list_task_files(tmp_path)
        assert not files[0].name.startswith("CRITICAL-")

    def test_workaround_bug_impact_is_wrong_output(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_low_severity_with_workaround_response())
        triager = BugTriager(llm, vault)
        result = triager.triage(_make_bug_entry(content="equity curve wrong with spread filter"))
        assert result.impact == "wrong_output"

    def test_workaround_bug_notes_mention_workaround(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_low_severity_with_workaround_response())
        triager = BugTriager(llm, vault)
        result = triager.triage(_make_bug_entry(content="equity curve wrong with spread filter"))
        assert "workaround" in result.notes.lower()


# ---------------------------------------------------------------------------
# Tests: high severity, no workaround → task written without CRITICAL- prefix
# ---------------------------------------------------------------------------


class TestHighSeverityNoWorkaround:
    def test_high_severity_writes_task(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_high_severity_no_workaround_response())
        triager = BugTriager(llm, vault)
        triager.triage(_make_bug_entry(content="dashboard shows wrong equity values"))
        files = _list_task_files(tmp_path)
        assert len(files) == 1

    def test_high_severity_task_has_no_critical_prefix(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_high_severity_no_workaround_response())
        triager = BugTriager(llm, vault)
        triager.triage(_make_bug_entry(content="dashboard shows wrong equity values"))
        files = _list_task_files(tmp_path)
        assert not files[0].name.startswith("CRITICAL-")

    def test_high_severity_returns_high(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM(_high_severity_no_workaround_response())
        triager = BugTriager(llm, vault)
        result = triager.triage(_make_bug_entry(content="dashboard shows wrong equity values"))
        assert result.severity == "high"


# ---------------------------------------------------------------------------
# Tests: task id sequencing
# ---------------------------------------------------------------------------


class TestTaskIdSequencing:
    def test_second_bug_gets_incremented_id(self, tmp_path):
        vault = _setup_vault(tmp_path)

        llm1 = FakeLLM(_critical_response())
        triager1 = BugTriager(llm1, vault)
        triager1.triage(_make_bug_entry(content="first bug"))

        llm2 = FakeLLM(_high_severity_no_workaround_response())
        triager2 = BugTriager(llm2, vault)
        triager2.triage(_make_bug_entry(content="second bug"))

        files = _list_task_files(tmp_path)
        assert len(files) == 2

        # Extract numeric parts from filenames
        nums = []
        for f in files:
            m = re.search(r"(\d+)-", f.name)
            if m:
                nums.append(int(m.group(1)))
        assert sorted(nums) == [1, 2]

    def test_critical_prefix_does_not_break_sequencing(self, tmp_path):
        vault = _setup_vault(tmp_path)

        # First task: critical
        llm1 = FakeLLM(_critical_response())
        BugTriager(llm1, vault).triage(_make_bug_entry(content="critical bug"))

        # Second task: high (no critical prefix)
        llm2 = FakeLLM(_high_severity_no_workaround_response())
        BugTriager(llm2, vault).triage(_make_bug_entry(content="high bug"))

        files = _list_task_files(tmp_path)
        assert len(files) == 2
        names = [f.name for f in files]
        assert any(n.startswith("CRITICAL-") for n in names)
        assert any(not n.startswith("CRITICAL-") for n in names)


# ---------------------------------------------------------------------------
# Tests: malformed LLM response → raises ValueError
# ---------------------------------------------------------------------------


class TestMalformedResponse:
    def test_plain_text_raises_value_error(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM("This is not JSON.")
        triager = BugTriager(llm, vault)
        with pytest.raises(ValueError):
            triager.triage(_make_bug_entry())

    def test_truncated_json_raises_value_error(self, tmp_path):
        vault = _setup_vault(tmp_path)
        llm = FakeLLM('{"reproducible": true')
        triager = BugTriager(llm, vault)
        with pytest.raises(ValueError):
            triager.triage(_make_bug_entry())

    def test_markdown_fenced_json_is_parsed_correctly(self, tmp_path):
        vault = _setup_vault(tmp_path)
        fenced = "```json\n" + _critical_response() + "\n```"
        llm = FakeLLM(fenced)
        triager = BugTriager(llm, vault)
        result = triager.triage(_make_bug_entry())
        assert result.severity == "critical"
