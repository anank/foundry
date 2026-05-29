"""Tests for the Idea Killer triage component.

Run with:
    pytest tests/test_idea_killer.py

All tests use FakeLLM — no real API calls needed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest

from foundry.llm.base import LLMResponse, TriageLLM
from foundry.vault.schema import BrainDumpEntry
from foundry.triage.idea_killer import IdeaKiller


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


def _make_vault(tmp_path: Path) -> Path:
    """Create a minimal vault directory with goals.md, principles.md, existing-systems.md."""
    vault = tmp_path / "vault"
    vault.mkdir()

    (vault / "goals.md").write_text(
        "# Goals\n\n"
        "- Ship the Multi-Agent Content System to production and automate article publishing.\n"
        "- Build and operate the Pipnesia EA on a funded prop firm account.\n"
        "- Reduce manual repetitive work in existing operating systems.\n",
        encoding="utf-8",
    )
    (vault / "principles.md").write_text(
        "# Principles\n\n"
        "- Default verdict is KILL. Ideas must earn survival.\n"
        "- Automate only what has been done manually at least 5 times.\n"
        "- No new projects until existing ones are operating.\n",
        encoding="utf-8",
    )
    (vault / "existing-systems.md").write_text(
        "# Existing Systems\n\n"
        "## Multi-Agent Content System\n"
        "status: operating\n"
        "description: Generates and queues articles for WordPress publishing.\n\n"
        "## Pipnesia EA\n"
        "status: operating\n"
        "description: Algorithmic trading EA running on MT5.\n\n"
        "## AI Ticket Tool\n"
        "status: half-built\n"
        "description: Classifies and routes support tickets.\n",
        encoding="utf-8",
    )
    return vault


def _make_kill_entry() -> BrainDumpEntry:
    """Brain dump entry that should be KILLed — no goal anchor (recipe app)."""
    return BrainDumpEntry(
        timestamp="2026-05-14 08:42",
        type="idea",
        content=(
            "build a recipe recommendation app that suggests meals based on what's in your fridge "
            "— take a photo, AI detects ingredients, suggests 3 recipes with shopping list for missing items"
        ),
        context="cooking dinner, annoyed at not knowing what to make",
        state="energized",
        source="app",
        triage_status="pending",
    )


def _make_advance_entry() -> BrainDumpEntry:
    """Brain dump entry that should ADVANCE — auto-publish articles from content system."""
    return BrainDumpEntry(
        timestamp="2026-05-19 07:45",
        type="idea",
        content=(
            "build a CLI tool that reads the Multi-Agent Content System's output queue, "
            "detects when articles are ready, and auto-posts them to the WordPress site via REST API "
            "— no manual copy-paste, just approve in terminal and it publishes with correct category, "
            "tags, and featured image"
        ),
        context=(
            "spent 40 minutes this morning manually publishing 6 articles that the content system "
            "had already written and approved — this is the third week in a row doing this same manual step"
        ),
        state="frustrated",
        source="app",
        triage_status="pending",
    )


# ---------------------------------------------------------------------------
# Canned LLM responses
# ---------------------------------------------------------------------------


def _kill_response() -> str:
    return json.dumps({
        "verdict": "KILL",
        "checks": {
            "goal_anchor": {
                "pass": False,
                "reasoning": (
                    "The recipe app does not connect to any stated goal — "
                    "goals are about content system automation and algo trading, not consumer food apps."
                ),
            },
            "existing_overlap": {
                "pass": False,
                "reasoning": "Moot — goal_anchor already failed.",
            },
            "manual_baseline": {
                "pass": False,
                "reasoning": "Moot — goal_anchor already failed.",
            },
            "killshot": {
                "pass": False,
                "reasoning": "Moot — goal_anchor already failed.",
            },
            "existence_test": {
                "pass": False,
                "reasoning": "Moot — goal_anchor already failed.",
            },
        },
        "verdict_reasoning": (
            "The idea has no connection to any of Anang's stated goals. "
            "Goals are focused on content automation and algo trading — a recipe app is a consumer product "
            "in a completely different domain. Killed on first check."
        ),
        "park_revival_condition": None,
        "related_killed_ideas": [],
    })


def _advance_response() -> str:
    return json.dumps({
        "verdict": "ADVANCE",
        "checks": {
            "goal_anchor": {
                "pass": True,
                "reasoning": (
                    "Directly serves the goal 'Ship the Multi-Agent Content System to production "
                    "and automate article publishing'."
                ),
            },
            "existing_overlap": {
                "pass": True,
                "reasoning": (
                    "The Multi-Agent Content System generates articles but has no publishing step — "
                    "this fills a real gap, not a duplicate."
                ),
            },
            "manual_baseline": {
                "pass": True,
                "reasoning": (
                    "Context confirms this has been done manually every week for at least 3 weeks, "
                    "40 minutes per session — well past the 5-repetition threshold."
                ),
            },
            "killshot": {
                "pass": True,
                "reasoning": (
                    "Objection 1: WordPress REST API auth may be fragile — survivable, standard OAuth. "
                    "Objection 2: Featured image mapping may be complex — survivable, can default to none. "
                    "Objection 3: CLI tool may be abandoned for a dashboard button later — survivable, "
                    "CLI is the right v1 scope. No decisive objections."
                ),
            },
            "existence_test": {
                "pass": True,
                "reasoning": (
                    "Saves 40 minutes every week, eliminates manual copy-paste of 6+ articles, "
                    "removes the last manual step in the content pipeline."
                ),
            },
        },
        "verdict_reasoning": (
            "All five checks pass. The idea directly serves a stated goal, fills a real gap in an "
            "existing operating system, has a proven manual baseline, survives adversarial objections, "
            "and has a concrete measurable impact. Advance to Interviewer."
        ),
        "park_revival_condition": None,
        "related_killed_ideas": [],
    })


def _park_response() -> str:
    return json.dumps({
        "verdict": "PARK",
        "checks": {
            "goal_anchor": {
                "pass": True,
                "reasoning": "Connects to the goal of reducing manual work in operating systems.",
            },
            "existing_overlap": {
                "pass": True,
                "reasoning": "No existing system covers this specific workflow.",
            },
            "manual_baseline": {
                "pass": True,
                "reasoning": "Has been done manually more than 5 times.",
            },
            "killshot": {
                "pass": True,
                "reasoning": (
                    "Objection 1: Scope may expand — survivable with strict MVP. "
                    "Objection 2: Dependency on external API — survivable. "
                    "Objection 3: Low frequency of use — survivable. No decisive objections."
                ),
            },
            "existence_test": {
                "pass": True,
                "reasoning": "Saves 2 hours per month on a recurring manual task.",
            },
        },
        "verdict_reasoning": (
            "All checks pass but the Pipnesia EA project must reach operating status first — "
            "building this now would split focus from the higher-priority trading system. "
            "Park until EA is on a funded account."
        ),
        "park_revival_condition": "Pipnesia EA is live on a funded prop firm account.",
        "related_killed_ideas": [],
    })


def _malformed_response() -> str:
    return "This is not JSON at all, just plain text from a confused model."


# ---------------------------------------------------------------------------
# Tests: KILL verdict
# ---------------------------------------------------------------------------


class TestIdeaKillerKill:
    def test_kill_fixture_returns_kill_verdict(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_kill_response())
        killer = IdeaKiller(llm, vault)
        result = killer.kill(_make_kill_entry())
        assert result.verdict == "KILL"

    def test_kill_verdict_has_five_checks(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_kill_response())
        killer = IdeaKiller(llm, vault)
        result = killer.kill(_make_kill_entry())
        assert set(result.checks.keys()) == {
            "goal_anchor", "existing_overlap", "manual_baseline", "killshot", "existence_test"
        }

    def test_kill_verdict_goal_anchor_fails(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_kill_response())
        killer = IdeaKiller(llm, vault)
        result = killer.kill(_make_kill_entry())
        assert result.checks["goal_anchor"].pass_ is False

    def test_kill_verdict_has_reasoning(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_kill_response())
        killer = IdeaKiller(llm, vault)
        result = killer.kill(_make_kill_entry())
        assert isinstance(result.verdict_reasoning, str)
        assert len(result.verdict_reasoning) > 0

    def test_kill_verdict_no_revival_condition(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_kill_response())
        killer = IdeaKiller(llm, vault)
        result = killer.kill(_make_kill_entry())
        assert result.park_revival_condition is None

    def test_llm_called_with_idea_killer_role(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_kill_response())
        killer = IdeaKiller(llm, vault)
        killer.kill(_make_kill_entry())
        assert len(llm.calls) == 1
        assert llm.calls[0]["role"] == "idea_killer"

    def test_llm_prompt_contains_entry_content(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_kill_response())
        killer = IdeaKiller(llm, vault)
        killer.kill(_make_kill_entry())
        assert "recipe recommendation" in llm.calls[0]["prompt"]

    def test_llm_prompt_contains_goals(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_kill_response())
        killer = IdeaKiller(llm, vault)
        killer.kill(_make_kill_entry())
        assert "Goals" in llm.calls[0]["prompt"]

    def test_llm_prompt_contains_existing_systems(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_kill_response())
        killer = IdeaKiller(llm, vault)
        killer.kill(_make_kill_entry())
        assert "Existing Systems" in llm.calls[0]["prompt"]

    def test_llm_prompt_contains_principles(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_kill_response())
        killer = IdeaKiller(llm, vault)
        killer.kill(_make_kill_entry())
        assert "Principles" in llm.calls[0]["prompt"]


# ---------------------------------------------------------------------------
# Tests: ADVANCE verdict
# ---------------------------------------------------------------------------


class TestIdeaKillerAdvance:
    def test_advance_fixture_returns_advance_verdict(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_advance_response())
        killer = IdeaKiller(llm, vault)
        result = killer.kill(_make_advance_entry())
        assert result.verdict == "ADVANCE"

    def test_advance_all_checks_pass(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_advance_response())
        killer = IdeaKiller(llm, vault)
        result = killer.kill(_make_advance_entry())
        for key, check in result.checks.items():
            assert check.pass_ is True, f"Expected check {key!r} to pass"

    def test_advance_no_revival_condition(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_advance_response())
        killer = IdeaKiller(llm, vault)
        result = killer.kill(_make_advance_entry())
        assert result.park_revival_condition is None

    def test_advance_does_not_write_graveyard(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_advance_response())
        killer = IdeaKiller(llm, vault)
        killer.kill(_make_advance_entry())
        graveyard = vault / "graveyard"
        # Graveyard directory should not exist (or be empty) for ADVANCE
        if graveyard.exists():
            all_files = list(graveyard.rglob("*.md"))
            assert all_files == [], f"Expected no graveyard files for ADVANCE, found: {all_files}"

    def test_advance_check_reasoning_are_strings(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_advance_response())
        killer = IdeaKiller(llm, vault)
        result = killer.kill(_make_advance_entry())
        for key, check in result.checks.items():
            assert isinstance(check.reasoning, str), f"Check {key!r} reasoning is not a string"
            assert len(check.reasoning) > 0, f"Check {key!r} reasoning is empty"


# ---------------------------------------------------------------------------
# Tests: KILL verdict → graveyard file written
# ---------------------------------------------------------------------------


class TestIdeaKillerGraveyardOnKill:
    def test_kill_writes_graveyard_file(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_kill_response())
        killer = IdeaKiller(llm, vault)
        killer.kill(_make_kill_entry())
        graveyard = vault / "graveyard"
        assert graveyard.exists(), "graveyard directory was not created"
        md_files = list(graveyard.rglob("*.md"))
        assert len(md_files) == 1, f"Expected 1 graveyard file, found {len(md_files)}"

    def test_kill_graveyard_file_contains_verdict(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_kill_response())
        killer = IdeaKiller(llm, vault)
        killer.kill(_make_kill_entry())
        md_files = list((vault / "graveyard").rglob("*.md"))
        content = md_files[0].read_text(encoding="utf-8")
        assert "KILL" in content

    def test_kill_graveyard_file_contains_original_idea(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_kill_response())
        killer = IdeaKiller(llm, vault)
        entry = _make_kill_entry()
        killer.kill(entry)
        md_files = list((vault / "graveyard").rglob("*.md"))
        content = md_files[0].read_text(encoding="utf-8")
        assert "recipe" in content.lower()

    def test_kill_graveyard_file_contains_verdict_reasoning(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_kill_response())
        killer = IdeaKiller(llm, vault)
        killer.kill(_make_kill_entry())
        md_files = list((vault / "graveyard").rglob("*.md"))
        content = md_files[0].read_text(encoding="utf-8")
        assert "Verdict Reasoning" in content

    def test_kill_graveyard_file_in_dated_subdirectory(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_kill_response())
        killer = IdeaKiller(llm, vault)
        killer.kill(_make_kill_entry())
        # Should be graveyard/YYYY-MM/<slug>.md
        month_dirs = list((vault / "graveyard").iterdir())
        assert len(month_dirs) == 1
        assert month_dirs[0].is_dir()
        # Directory name should look like YYYY-MM
        assert len(month_dirs[0].name) == 7
        assert month_dirs[0].name[4] == "-"


# ---------------------------------------------------------------------------
# Tests: PARK verdict → graveyard file written with revival_condition
# ---------------------------------------------------------------------------


class TestIdeaKillerGraveyardOnPark:
    def test_park_writes_graveyard_file(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_park_response())
        killer = IdeaKiller(llm, vault)
        # Use the advance entry — the FakeLLM will return PARK regardless
        killer.kill(_make_advance_entry())
        graveyard = vault / "graveyard"
        assert graveyard.exists()
        md_files = list(graveyard.rglob("*.md"))
        assert len(md_files) == 1

    def test_park_graveyard_file_contains_park_verdict(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_park_response())
        killer = IdeaKiller(llm, vault)
        killer.kill(_make_advance_entry())
        md_files = list((vault / "graveyard").rglob("*.md"))
        content = md_files[0].read_text(encoding="utf-8")
        assert "PARK" in content

    def test_park_graveyard_file_contains_revival_condition(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_park_response())
        killer = IdeaKiller(llm, vault)
        killer.kill(_make_advance_entry())
        md_files = list((vault / "graveyard").rglob("*.md"))
        content = md_files[0].read_text(encoding="utf-8")
        assert "Pipnesia EA is live" in content

    def test_park_verdict_has_revival_condition_on_result(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_park_response())
        killer = IdeaKiller(llm, vault)
        result = killer.kill(_make_advance_entry())
        assert result.park_revival_condition is not None
        assert len(result.park_revival_condition) > 0


# ---------------------------------------------------------------------------
# Tests: malformed JSON → raises ValueError
# ---------------------------------------------------------------------------


class TestIdeaKillerMalformedResponse:
    def test_plain_text_raises_value_error(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_malformed_response())
        killer = IdeaKiller(llm, vault)
        with pytest.raises(ValueError, match="not valid JSON"):
            killer.kill(_make_kill_entry())

    def test_truncated_json_raises_value_error(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM('{"verdict": "KILL"')  # truncated
        killer = IdeaKiller(llm, vault)
        with pytest.raises(ValueError):
            killer.kill(_make_kill_entry())

    def test_json_missing_verdict_raises_value_error(self, tmp_path):
        vault = _make_vault(tmp_path)
        bad = json.dumps({
            "checks": {},
            "verdict_reasoning": "some reasoning",
            "park_revival_condition": None,
            "related_killed_ideas": [],
        })
        llm = FakeLLM(bad)
        killer = IdeaKiller(llm, vault)
        with pytest.raises(ValueError):
            killer.kill(_make_kill_entry())

    def test_json_missing_verdict_reasoning_raises_value_error(self, tmp_path):
        vault = _make_vault(tmp_path)
        bad = json.dumps({
            "verdict": "KILL",
            "checks": {},
            "park_revival_condition": None,
            "related_killed_ideas": [],
        })
        llm = FakeLLM(bad)
        killer = IdeaKiller(llm, vault)
        with pytest.raises(ValueError):
            killer.kill(_make_kill_entry())

    def test_markdown_fenced_json_is_parsed_correctly(self, tmp_path):
        """LLMs sometimes wrap JSON in ```json ... ``` — must handle gracefully."""
        vault = _make_vault(tmp_path)
        fenced = "```json\n" + _kill_response() + "\n```"
        llm = FakeLLM(fenced)
        killer = IdeaKiller(llm, vault)
        result = killer.kill(_make_kill_entry())
        assert result.verdict == "KILL"

    def test_markdown_fenced_no_lang_tag_is_parsed_correctly(self, tmp_path):
        vault = _make_vault(tmp_path)
        fenced = "```\n" + _kill_response() + "\n```"
        llm = FakeLLM(fenced)
        killer = IdeaKiller(llm, vault)
        result = killer.kill(_make_kill_entry())
        assert result.verdict == "KILL"

    def test_empty_string_raises_value_error(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM("")
        killer = IdeaKiller(llm, vault)
        with pytest.raises(ValueError):
            killer.kill(_make_kill_entry())


# ---------------------------------------------------------------------------
# Tests: vault context loading
# ---------------------------------------------------------------------------


class TestIdeaKillerVaultContext:
    def test_missing_goals_file_does_not_raise(self, tmp_path):
        """Vault with no goals.md should not crash — produces a placeholder."""
        vault = tmp_path / "vault"
        vault.mkdir()
        # Only create principles and existing-systems, omit goals
        (vault / "principles.md").write_text("# Principles\n", encoding="utf-8")
        (vault / "existing-systems.md").write_text("# Systems\n", encoding="utf-8")
        llm = FakeLLM(_kill_response())
        killer = IdeaKiller(llm, vault)
        # Should not raise — missing file produces placeholder text
        result = killer.kill(_make_kill_entry())
        assert result.verdict == "KILL"

    def test_missing_goals_placeholder_appears_in_prompt(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "principles.md").write_text("# Principles\n", encoding="utf-8")
        (vault / "existing-systems.md").write_text("# Systems\n", encoding="utf-8")
        llm = FakeLLM(_kill_response())
        killer = IdeaKiller(llm, vault)
        killer.kill(_make_kill_entry())
        assert "goals.md" in llm.calls[0]["prompt"]

    def test_vault_context_loads_all_three_files(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_kill_response())
        killer = IdeaKiller(llm, vault)
        ctx = killer._load_vault_context()
        assert "goals" in ctx
        assert "existing_systems" in ctx
        assert "principles" in ctx

    def test_vault_context_goals_contains_expected_content(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_kill_response())
        killer = IdeaKiller(llm, vault)
        ctx = killer._load_vault_context()
        assert "Multi-Agent Content System" in ctx["goals"]

    def test_vault_context_existing_systems_contains_expected_content(self, tmp_path):
        vault = _make_vault(tmp_path)
        llm = FakeLLM(_kill_response())
        killer = IdeaKiller(llm, vault)
        ctx = killer._load_vault_context()
        assert "Pipnesia EA" in ctx["existing_systems"]
