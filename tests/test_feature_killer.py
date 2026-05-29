"""Tests for the Feature Killer triage component.

Run with:
    pytest tests/test_feature_killer.py

All tests use FakeLLM — no real API calls needed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest

from foundry.llm.base import LLMResponse, TriageLLM
from foundry.vault.schema import BrainDumpEntry
from foundry.triage.feature_killer import FeatureKiller


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
# Vault helpers
# ---------------------------------------------------------------------------


def _make_vault(tmp_path: Path, project_name: str = "pipnesia-ea") -> Path:
    """Create a minimal vault with one project directory."""
    vault = tmp_path / "vault"
    vault.mkdir()

    project_dir = vault / "projects" / project_name
    (project_dir / "tasks").mkdir(parents=True)

    return vault


def _write_project_md(vault: Path, project_name: str, status: str, last_activity: str = "") -> None:
    """Write a minimal PROJECT.md for the given project."""
    project_dir = vault / "projects" / project_name
    project_dir.mkdir(parents=True, exist_ok=True)

    content_lines = [
        f"# Project: {project_name}",
        f"status: {status}",
        "priority: high",
        "created: 2025-01-01",
        "goal_anchor: Build and operate the Pipnesia EA on a funded prop firm account.",
        "",
        "## Description",
        "Algorithmic trading EA running on MT5 for prop firm challenges.",
        "",
        "## Tech Spec",
        "MQL5 EA with Python analytics layer.",
        "",
        "## MVP Definition",
        "EA passes a prop firm challenge and reaches funded account status.",
        "",
        "## Current State",
    ]
    if last_activity:
        content_lines.append(last_activity)
    else:
        content_lines.append("Active development ongoing.")

    (project_dir / "PROJECT.md").write_text(
        "\n".join(content_lines) + "\n", encoding="utf-8"
    )


def _write_next_md(vault: Path, project_name: str, content: str = "") -> None:
    """Write tasks/_next.md for the given project."""
    tasks_dir = vault / "projects" / project_name / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / "_next.md").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Brain dump entry factories
# ---------------------------------------------------------------------------


def _make_feature_entry(
    project: str = "pipnesia-ea",
    content: str = "add a Telegram notification when the EA opens a new trade",
    context: str = "missed a trade entry while away from desk",
    state: str = "energized",
) -> BrainDumpEntry:
    return BrainDumpEntry(
        timestamp="2026-05-26 10:00",
        type="feature",
        project=project,
        content=content,
        context=context,
        state=state,
        source="app",
        triage_status="pending",
    )


# ---------------------------------------------------------------------------
# Canned LLM responses
# ---------------------------------------------------------------------------


def _kill_no_mvp_response() -> str:
    """Feature for a project that hasn't shipped MVP yet → KILL."""
    return json.dumps({
        "verdict": "KILL",
        "checks": {
            "mvp_exists": {
                "pass": False,
                "reasoning": (
                    "Project status is 'building' — MVP has not shipped. "
                    "Features are premature until the project is operating."
                ),
            },
            "roadmap_conflict": {
                "pass": True,
                "reasoning": "Moot — mvp_exists already failed.",
            },
            "scope_creep": {
                "pass": True,
                "reasoning": "Moot — mvp_exists already failed.",
            },
            "killshot": {
                "pass": True,
                "reasoning": "Moot — mvp_exists already failed.",
            },
        },
        "verdict_reasoning": (
            "The host project is in 'building' status and has not shipped its MVP. "
            "Adding features before the MVP is live is premature and splits focus. "
            "Ship MVP first, then revisit this feature."
        ),
        "park_revival_condition": None,
    })


def _park_scope_creep_response() -> str:
    """Feature for a stable operating project untouched >30 days → PARK."""
    return json.dumps({
        "verdict": "PARK",
        "checks": {
            "mvp_exists": {
                "pass": True,
                "reasoning": "Project status is 'operating' — MVP is shipped and live.",
            },
            "roadmap_conflict": {
                "pass": True,
                "reasoning": "tasks/_next.md is empty — no queued tasks to conflict with.",
            },
            "scope_creep": {
                "pass": False,
                "reasoning": (
                    "Project is 'operating' and the Current State section indicates "
                    "last activity was over 30 days ago. Adding features to a stable "
                    "system carries risk without an active development cycle."
                ),
            },
            "killshot": {
                "pass": True,
                "reasoning": "Moot — scope_creep already failed.",
            },
        },
        "verdict_reasoning": (
            "The project is operating and has been stable for over 30 days. "
            "The feature itself is reasonable but the timing is wrong — "
            "park until there is an active development cycle or a compelling operational need."
        ),
        "park_revival_condition": (
            "An active development cycle is opened for pipnesia-ea, "
            "or the feature addresses a live operational problem."
        ),
    })


def _advance_response() -> str:
    """Valid feature for an active operating project → ADVANCE."""
    return json.dumps({
        "verdict": "ADVANCE",
        "checks": {
            "mvp_exists": {
                "pass": True,
                "reasoning": "Project status is 'operating' — MVP is shipped and live.",
            },
            "roadmap_conflict": {
                "pass": True,
                "reasoning": (
                    "tasks/_next.md contains only a spread-filter fix task — "
                    "no overlap with a Telegram notification feature."
                ),
            },
            "scope_creep": {
                "pass": True,
                "reasoning": (
                    "Project is actively being developed with recent commits. "
                    "No inactivity concern."
                ),
            },
            "killshot": {
                "pass": True,
                "reasoning": (
                    "Objection A: Telegram adds an external dependency — survivable, "
                    "standard bot API, already in Anang's workflow. "
                    "Objection B: Not a new project — notification is a single output channel, "
                    "not a new domain or deployment. Both objections answered."
                ),
            },
        },
        "verdict_reasoning": (
            "All four checks pass. The project is live, the feature has no roadmap conflicts, "
            "the project is actively maintained, and the feature is clearly within scope. "
            "Advance to the project's interviewer."
        ),
        "park_revival_condition": None,
    })


def _malformed_response() -> str:
    return "This is not JSON at all, just plain text from a confused model."


# ---------------------------------------------------------------------------
# Tests: KILL — project has no MVP yet
# ---------------------------------------------------------------------------


class TestFeatureKillerKillNoMvp:
    def test_kill_verdict_returned(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="building")
        _write_next_md(vault, "pipnesia-ea")
        llm = FakeLLM(_kill_no_mvp_response())
        killer = FeatureKiller(llm, vault)
        result = killer.kill(_make_feature_entry())
        assert result.verdict == "KILL"

    def test_kill_mvp_exists_check_fails(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="building")
        _write_next_md(vault, "pipnesia-ea")
        llm = FakeLLM(_kill_no_mvp_response())
        killer = FeatureKiller(llm, vault)
        result = killer.kill(_make_feature_entry())
        assert result.checks["mvp_exists"].pass_ is False

    def test_kill_has_four_checks(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="building")
        _write_next_md(vault, "pipnesia-ea")
        llm = FakeLLM(_kill_no_mvp_response())
        killer = FeatureKiller(llm, vault)
        result = killer.kill(_make_feature_entry())
        assert set(result.checks.keys()) == {
            "mvp_exists", "roadmap_conflict", "scope_creep", "killshot"
        }

    def test_kill_has_verdict_reasoning(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="building")
        _write_next_md(vault, "pipnesia-ea")
        llm = FakeLLM(_kill_no_mvp_response())
        killer = FeatureKiller(llm, vault)
        result = killer.kill(_make_feature_entry())
        assert isinstance(result.verdict_reasoning, str)
        assert len(result.verdict_reasoning) > 0

    def test_kill_no_revival_condition(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="building")
        _write_next_md(vault, "pipnesia-ea")
        llm = FakeLLM(_kill_no_mvp_response())
        killer = FeatureKiller(llm, vault)
        result = killer.kill(_make_feature_entry())
        assert result.park_revival_condition is None

    def test_llm_called_with_feature_killer_role(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="building")
        _write_next_md(vault, "pipnesia-ea")
        llm = FakeLLM(_kill_no_mvp_response())
        killer = FeatureKiller(llm, vault)
        killer.kill(_make_feature_entry())
        assert len(llm.calls) == 1
        assert llm.calls[0]["role"] == "feature_killer"

    def test_llm_prompt_contains_entry_content(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="building")
        _write_next_md(vault, "pipnesia-ea")
        llm = FakeLLM(_kill_no_mvp_response())
        killer = FeatureKiller(llm, vault)
        killer.kill(_make_feature_entry())
        assert "Telegram" in llm.calls[0]["prompt"]

    def test_llm_prompt_contains_project_md(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="building")
        _write_next_md(vault, "pipnesia-ea")
        llm = FakeLLM(_kill_no_mvp_response())
        killer = FeatureKiller(llm, vault)
        killer.kill(_make_feature_entry())
        assert "PROJECT.md" in llm.calls[0]["prompt"]

    def test_llm_prompt_contains_project_name(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="building")
        _write_next_md(vault, "pipnesia-ea")
        llm = FakeLLM(_kill_no_mvp_response())
        killer = FeatureKiller(llm, vault)
        killer.kill(_make_feature_entry())
        assert "pipnesia-ea" in llm.calls[0]["prompt"]

    def test_missing_project_raises_value_error(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_kill_no_mvp_response())
        killer = FeatureKiller(llm, vault)
        entry = BrainDumpEntry(
            timestamp="2026-05-26 10:00",
            type="feature",
            project=None,
            content="some feature",
            triage_status="pending",
        )
        with pytest.raises(ValueError, match="entry.project"):
            killer.kill(entry)


# ---------------------------------------------------------------------------
# Tests: PARK — scope creep on stable operating project
# ---------------------------------------------------------------------------


class TestFeatureKillerParkScopeCreep:
    def test_park_verdict_returned(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(
            vault, "pipnesia-ea", status="operating",
            last_activity="Last commit: 2026-03-01. No changes since."
        )
        _write_next_md(vault, "pipnesia-ea", content="")
        llm = FakeLLM(_park_scope_creep_response())
        killer = FeatureKiller(llm, vault)
        result = killer.kill(_make_feature_entry())
        assert result.verdict == "PARK"

    def test_park_scope_creep_check_fails(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(
            vault, "pipnesia-ea", status="operating",
            last_activity="Last commit: 2026-03-01. No changes since."
        )
        _write_next_md(vault, "pipnesia-ea", content="")
        llm = FakeLLM(_park_scope_creep_response())
        killer = FeatureKiller(llm, vault)
        result = killer.kill(_make_feature_entry())
        assert result.checks["scope_creep"].pass_ is False

    def test_park_mvp_exists_passes(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(
            vault, "pipnesia-ea", status="operating",
            last_activity="Last commit: 2026-03-01. No changes since."
        )
        _write_next_md(vault, "pipnesia-ea", content="")
        llm = FakeLLM(_park_scope_creep_response())
        killer = FeatureKiller(llm, vault)
        result = killer.kill(_make_feature_entry())
        assert result.checks["mvp_exists"].pass_ is True

    def test_park_has_revival_condition(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(
            vault, "pipnesia-ea", status="operating",
            last_activity="Last commit: 2026-03-01. No changes since."
        )
        _write_next_md(vault, "pipnesia-ea", content="")
        llm = FakeLLM(_park_scope_creep_response())
        killer = FeatureKiller(llm, vault)
        result = killer.kill(_make_feature_entry())
        assert result.park_revival_condition is not None
        assert len(result.park_revival_condition) > 0

    def test_park_has_four_checks(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(
            vault, "pipnesia-ea", status="operating",
            last_activity="Last commit: 2026-03-01. No changes since."
        )
        _write_next_md(vault, "pipnesia-ea", content="")
        llm = FakeLLM(_park_scope_creep_response())
        killer = FeatureKiller(llm, vault)
        result = killer.kill(_make_feature_entry())
        assert set(result.checks.keys()) == {
            "mvp_exists", "roadmap_conflict", "scope_creep", "killshot"
        }

    def test_park_check_reasoning_are_strings(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(
            vault, "pipnesia-ea", status="operating",
            last_activity="Last commit: 2026-03-01. No changes since."
        )
        _write_next_md(vault, "pipnesia-ea", content="")
        llm = FakeLLM(_park_scope_creep_response())
        killer = FeatureKiller(llm, vault)
        result = killer.kill(_make_feature_entry())
        for key, check in result.checks.items():
            assert isinstance(check.reasoning, str), f"Check {key!r} reasoning is not a string"
            assert len(check.reasoning) > 0, f"Check {key!r} reasoning is empty"


# ---------------------------------------------------------------------------
# Tests: ADVANCE — valid feature for active operating project
# ---------------------------------------------------------------------------


class TestFeatureKillerAdvance:
    def test_advance_verdict_returned(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="operating")
        _write_next_md(
            vault, "pipnesia-ea",
            content="# Next Tasks\n\n1. Fix spread filter on GBPUSD\n"
        )
        llm = FakeLLM(_advance_response())
        killer = FeatureKiller(llm, vault)
        result = killer.kill(_make_feature_entry())
        assert result.verdict == "ADVANCE"

    def test_advance_all_checks_pass(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="operating")
        _write_next_md(
            vault, "pipnesia-ea",
            content="# Next Tasks\n\n1. Fix spread filter on GBPUSD\n"
        )
        llm = FakeLLM(_advance_response())
        killer = FeatureKiller(llm, vault)
        result = killer.kill(_make_feature_entry())
        for key, check in result.checks.items():
            assert check.pass_ is True, f"Expected check {key!r} to pass"

    def test_advance_no_revival_condition(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="operating")
        _write_next_md(
            vault, "pipnesia-ea",
            content="# Next Tasks\n\n1. Fix spread filter on GBPUSD\n"
        )
        llm = FakeLLM(_advance_response())
        killer = FeatureKiller(llm, vault)
        result = killer.kill(_make_feature_entry())
        assert result.park_revival_condition is None

    def test_advance_has_four_checks(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="operating")
        _write_next_md(
            vault, "pipnesia-ea",
            content="# Next Tasks\n\n1. Fix spread filter on GBPUSD\n"
        )
        llm = FakeLLM(_advance_response())
        killer = FeatureKiller(llm, vault)
        result = killer.kill(_make_feature_entry())
        assert set(result.checks.keys()) == {
            "mvp_exists", "roadmap_conflict", "scope_creep", "killshot"
        }

    def test_advance_has_verdict_reasoning(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="operating")
        _write_next_md(
            vault, "pipnesia-ea",
            content="# Next Tasks\n\n1. Fix spread filter on GBPUSD\n"
        )
        llm = FakeLLM(_advance_response())
        killer = FeatureKiller(llm, vault)
        result = killer.kill(_make_feature_entry())
        assert isinstance(result.verdict_reasoning, str)
        assert len(result.verdict_reasoning) > 0

    def test_advance_llm_prompt_contains_next_md(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="operating")
        _write_next_md(
            vault, "pipnesia-ea",
            content="# Next Tasks\n\n1. Fix spread filter on GBPUSD\n"
        )
        llm = FakeLLM(_advance_response())
        killer = FeatureKiller(llm, vault)
        killer.kill(_make_feature_entry())
        assert "tasks/_next.md" in llm.calls[0]["prompt"]

    def test_advance_llm_prompt_contains_today_date(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="operating")
        _write_next_md(vault, "pipnesia-ea")
        llm = FakeLLM(_advance_response())
        killer = FeatureKiller(llm, vault)
        killer.kill(_make_feature_entry())
        # Today's date is injected into the prompt for scope_creep calculation
        from datetime import date
        assert date.today().isoformat()[:4] in llm.calls[0]["prompt"]  # at least the year


# ---------------------------------------------------------------------------
# Tests: missing project files — graceful handling
# ---------------------------------------------------------------------------


class TestFeatureKillerMissingFiles:
    def test_missing_project_md_does_not_raise(self, tmp_path):
        """PROJECT.md absent — killer should still call LLM with placeholder."""
        vault = _make_vault(tmp_path)
        # Do NOT write PROJECT.md — only create the tasks dir
        (vault / "projects" / "pipnesia-ea" / "tasks").mkdir(parents=True, exist_ok=True)
        _write_next_md(vault, "pipnesia-ea")
        llm = FakeLLM(_kill_no_mvp_response())
        killer = FeatureKiller(llm, vault)
        result = killer.kill(_make_feature_entry())
        assert result.verdict == "KILL"

    def test_missing_project_md_placeholder_in_prompt(self, tmp_path):
        vault = _make_vault(tmp_path)
        (vault / "projects" / "pipnesia-ea" / "tasks").mkdir(parents=True, exist_ok=True)
        _write_next_md(vault, "pipnesia-ea")
        llm = FakeLLM(_kill_no_mvp_response())
        killer = FeatureKiller(llm, vault)
        killer.kill(_make_feature_entry())
        assert "not found" in llm.calls[0]["prompt"]

    def test_missing_next_md_does_not_raise(self, tmp_path):
        """tasks/_next.md absent — killer should still call LLM with placeholder."""
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="operating")
        # Do NOT write _next.md
        llm = FakeLLM(_advance_response())
        killer = FeatureKiller(llm, vault)
        result = killer.kill(_make_feature_entry())
        assert result.verdict == "ADVANCE"

    def test_missing_next_md_placeholder_in_prompt(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="operating")
        llm = FakeLLM(_advance_response())
        killer = FeatureKiller(llm, vault)
        killer.kill(_make_feature_entry())
        assert "not found" in llm.calls[0]["prompt"] or "empty" in llm.calls[0]["prompt"]


# ---------------------------------------------------------------------------
# Tests: malformed JSON → raises ValueError
# ---------------------------------------------------------------------------


class TestFeatureKillerMalformedResponse:
    def test_plain_text_raises_value_error(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="operating")
        _write_next_md(vault, "pipnesia-ea")
        llm = FakeLLM(_malformed_response())
        killer = FeatureKiller(llm, vault)
        with pytest.raises(ValueError, match="not valid JSON"):
            killer.kill(_make_feature_entry())

    def test_truncated_json_raises_value_error(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="operating")
        _write_next_md(vault, "pipnesia-ea")
        llm = FakeLLM('{"verdict": "KILL"')  # truncated
        killer = FeatureKiller(llm, vault)
        with pytest.raises(ValueError):
            killer.kill(_make_feature_entry())

    def test_json_missing_verdict_raises_value_error(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="operating")
        _write_next_md(vault, "pipnesia-ea")
        bad = json.dumps({
            "checks": {},
            "verdict_reasoning": "some reasoning",
            "park_revival_condition": None,
        })
        llm = FakeLLM(bad)
        killer = FeatureKiller(llm, vault)
        with pytest.raises((ValueError, KeyError)):
            killer.kill(_make_feature_entry())

    def test_markdown_fenced_json_is_parsed_correctly(self, tmp_path):
        """LLMs sometimes wrap JSON in ```json ... ``` — must handle gracefully."""
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="operating")
        _write_next_md(vault, "pipnesia-ea")
        fenced = "```json\n" + _advance_response() + "\n```"
        llm = FakeLLM(fenced)
        killer = FeatureKiller(llm, vault)
        result = killer.kill(_make_feature_entry())
        assert result.verdict == "ADVANCE"

    def test_markdown_fenced_no_lang_tag_is_parsed_correctly(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="operating")
        _write_next_md(vault, "pipnesia-ea")
        fenced = "```\n" + _advance_response() + "\n```"
        llm = FakeLLM(fenced)
        killer = FeatureKiller(llm, vault)
        result = killer.kill(_make_feature_entry())
        assert result.verdict == "ADVANCE"

    def test_empty_string_raises_value_error(self, tmp_path):
        vault = _make_vault(tmp_path)
        _write_project_md(vault, "pipnesia-ea", status="operating")
        _write_next_md(vault, "pipnesia-ea")
        llm = FakeLLM("")
        killer = FeatureKiller(llm, vault)
        with pytest.raises(ValueError):
            killer.kill(_make_feature_entry())
