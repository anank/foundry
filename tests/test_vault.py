"""Tests for VaultReader and VaultWriter.

Run with:
    pytest tests/test_vault.py

All tests use tmp_path — no real vault or API calls needed.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from foundry.vault.schema import (
    BrainDumpEntry,
    BugTriageResult,
    CheckResult,
    ExistingSystem,
    FeatureKillerVerdict,
    Goal,
    IdeaKillerVerdict,
    Principle,
    Project,
    Task,
)
from foundry.vault.reader import VaultReader
from foundry.vault.writer import VaultWriter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    """Return a minimal vault directory tree inside tmp_path."""
    (tmp_path / "brain-dump").mkdir()
    (tmp_path / "projects").mkdir()
    (tmp_path / "graveyard").mkdir()
    return tmp_path


@pytest.fixture()
def reader(vault: Path) -> VaultReader:
    return VaultReader(vault)


@pytest.fixture()
def writer(vault: Path) -> VaultWriter:
    # VaultWriter gracefully handles a non-git directory (self._repo = None)
    return VaultWriter(vault)


# ---------------------------------------------------------------------------
# Schema unit tests
# ---------------------------------------------------------------------------


class TestSchemaModels:
    def test_brain_dump_entry_defaults(self):
        entry = BrainDumpEntry(
            timestamp="2026-05-26 14:32",
            type="idea",
            content="telegram bot that posts EA equity curve daily",
        )
        assert entry.triage_status == "pending"
        assert entry.project is None
        assert entry.state is None

    def test_brain_dump_entry_full(self):
        entry = BrainDumpEntry(
            timestamp="2026-05-26 09:00",
            type="feature",
            project="pipnesiatest-ea",
            content="add trailing stop",
            context="watching live trade",
            state="energized",
            source="app",
            triage_status="classified",
        )
        assert entry.type == "feature"
        assert entry.project == "pipnesiatest-ea"

    def test_check_result_alias(self):
        # Must accept "pass" as the field name (alias)
        cr = CheckResult(**{"pass": True, "reasoning": "connects to goal 1"})
        assert cr.pass_ is True
        assert cr.reasoning == "connects to goal 1"

    def test_idea_killer_verdict(self):
        verdict = IdeaKillerVerdict(
            verdict="KILL",
            checks={
                "goal_anchor": CheckResult(**{"pass": False, "reasoning": "no goal match"}),
                "existing_overlap": CheckResult(**{"pass": True, "reasoning": "no overlap"}),
                "manual_baseline": CheckResult(**{"pass": False, "reasoning": "never done manually"}),
                "killshot": CheckResult(**{"pass": False, "reasoning": "decisive objection"}),
                "existence_test": CheckResult(**{"pass": False, "reasoning": "vague outcome"}),
            },
            verdict_reasoning="Fails goal anchor and manual baseline.",
            park_revival_condition=None,
            related_killed_ideas=[],
        )
        assert verdict.verdict == "KILL"
        assert verdict.checks["goal_anchor"].pass_ is False

    def test_feature_killer_verdict(self):
        v = FeatureKillerVerdict(
            verdict="PARK",
            checks={
                "mvp_exists": CheckResult(**{"pass": True, "reasoning": "MVP shipped"}),
                "killshot": CheckResult(**{"pass": False, "reasoning": "scope creep"}),
            },
            verdict_reasoning="Scope creep on a finished project.",
            park_revival_condition="Revisit after v2 roadmap is set.",
        )
        assert v.verdict == "PARK"
        assert v.park_revival_condition is not None

    def test_bug_triage_result(self):
        b = BugTriageResult(
            reproducible=True,
            impact="wrong_output",
            workaround_exists=False,
            severity="high",
            notes="Spread filter returns negative values on low-liquidity pairs.",
        )
        assert b.severity == "high"
        assert b.reproducible is True

    def test_task_model(self):
        t = Task(
            id="001",
            title="Add trailing stop",
            status="queued",
            project="pipnesiatest-ea",
            review_tag="behavioral",
            created=date(2026, 5, 26),
        )
        assert t.spec_locked is False
        assert t.acceptance_criteria == []

    def test_project_model(self):
        p = Project(
            name="pipnesiatest-ea",
            status="operating",
            priority="high",
            created=date(2026, 1, 1),
            description="MT5 EA for prop firm trading.",
        )
        assert p.goal_anchor is None

    def test_goal_principle_existing_system(self):
        g = Goal(text="Ship one profitable algo trading system by end of 2026.")
        assert g.text.startswith("Ship")

        pr = Principle(text="Never build what can be done manually first.")
        assert "manually" in pr.text

        es = ExistingSystem(
            name="Pipnesiatest EA",
            description="MT5 expert advisor",
            status="operating",
        )
        assert es.status == "operating"


# ---------------------------------------------------------------------------
# VaultReader tests
# ---------------------------------------------------------------------------


class TestVaultReaderBrainDump:
    def _write_brain_dump(self, vault: Path, month: str, content: str) -> None:
        (vault / "brain-dump").mkdir(exist_ok=True)
        (vault / "brain-dump" / f"{month}.md").write_text(content, encoding="utf-8")

    def test_read_single_entry(self, vault: Path, reader: VaultReader):
        self._write_brain_dump(
            vault,
            "2026-05",
            "## 2026-05-26 14:32\n"
            "type: idea\n"
            "content: telegram bot that posts EA equity curve daily\n"
            "context: while watching MT5 charts\n"
            "state: energized\n"
            "source: app\n"
            "triage_status: pending\n",
        )
        entries = reader.read_brain_dump("2026-05")
        assert len(entries) == 1
        e = entries[0]
        assert e.timestamp == "2026-05-26 14:32"
        assert e.type == "idea"
        assert e.content == "telegram bot that posts EA equity curve daily"
        assert e.context == "while watching MT5 charts"
        assert e.state == "energized"
        assert e.source == "app"
        assert e.triage_status == "pending"

    def test_read_multiple_entries(self, vault: Path, reader: VaultReader):
        self._write_brain_dump(
            vault,
            "2026-05",
            "## 2026-05-26 09:00\n"
            "type: idea\n"
            "content: first idea\n"
            "\n"
            "## 2026-05-26 14:32\n"
            "type: feature\n"
            "project: pipnesiatest-ea\n"
            "content: add trailing stop\n"
            "triage_status: classified\n",
        )
        entries = reader.read_brain_dump("2026-05")
        assert len(entries) == 2
        assert entries[0].type == "idea"
        assert entries[1].type == "feature"
        assert entries[1].project == "pipnesiatest-ea"

    def test_entry_without_type_is_skipped(self, vault: Path, reader: VaultReader):
        self._write_brain_dump(
            vault,
            "2026-05",
            "## 2026-05-26 10:00\n"
            "content: no type field here\n",
        )
        entries = reader.read_brain_dump("2026-05")
        assert entries == []

    def test_missing_file_returns_empty(self, reader: VaultReader):
        entries = reader.read_brain_dump("1999-01")
        assert entries == []

    def test_optional_fields_default_to_none(self, vault: Path, reader: VaultReader):
        self._write_brain_dump(
            vault,
            "2026-05",
            "## 2026-05-26 08:00\n"
            "type: bug\n"
            "content: spread filter crashes on weekend\n",
        )
        entries = reader.read_brain_dump("2026-05")
        assert len(entries) == 1
        e = entries[0]
        assert e.project is None
        assert e.context is None
        assert e.state is None
        assert e.source is None
        assert e.triage_status == "pending"


class TestVaultReaderGoalsPrinciples:
    def test_read_goals(self, vault: Path, reader: VaultReader):
        (vault / "goals.md").write_text(
            "# Goals\n\n"
            "- Ship one profitable algo trading system by end of 2026.\n"
            "- Build a passive income stream from AI tools.\n",
            encoding="utf-8",
        )
        goals = reader.read_goals()
        assert len(goals) == 2
        assert goals[0].text == "Ship one profitable algo trading system by end of 2026."

    def test_read_goals_missing_file(self, reader: VaultReader):
        assert reader.read_goals() == []

    def test_read_principles(self, vault: Path, reader: VaultReader):
        (vault / "principles.md").write_text(
            "# Principles\n\n"
            "- Never build what can be done manually first.\n"
            "- Max 2 projects in BUILDING state at once.\n",
            encoding="utf-8",
        )
        principles = reader.read_principles()
        assert len(principles) == 2
        assert "manually" in principles[0].text

    def test_read_principles_missing_file(self, reader: VaultReader):
        assert reader.read_principles() == []


class TestVaultReaderExistingSystems:
    def test_read_existing_systems(self, vault: Path, reader: VaultReader):
        (vault / "existing-systems.md").write_text(
            "# Existing Systems\n\n"
            "## Pipnesiatest EA\n"
            "description: MT5 expert advisor for prop firm trading\n"
            "status: operating\n"
            "\n"
            "## AI Ticket Tool\n"
            "description: Classifies support tickets automatically\n"
            "status: half-built\n",
            encoding="utf-8",
        )
        systems = reader.read_existing_systems()
        assert len(systems) == 2
        assert systems[0].name == "Pipnesiatest EA"
        assert systems[0].status == "operating"
        assert systems[1].name == "AI Ticket Tool"
        assert systems[1].status == "half-built"

    def test_read_existing_systems_missing_file(self, reader: VaultReader):
        assert reader.read_existing_systems() == []


class TestVaultReaderProjects:
    def _make_project(self, vault: Path, name: str, content: str) -> None:
        proj_dir = vault / "projects" / name
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "PROJECT.md").write_text(content, encoding="utf-8")

    def test_list_projects(self, vault: Path, reader: VaultReader):
        (vault / "projects" / "pipnesiatest-ea").mkdir(parents=True)
        (vault / "projects" / "ai-ticket-tool").mkdir(parents=True)
        (vault / "projects" / "_index.md").write_text("", encoding="utf-8")
        projects = reader.list_projects()
        assert "pipnesiatest-ea" in projects
        assert "ai-ticket-tool" in projects
        assert "_index.md" not in projects

    def test_list_projects_empty(self, reader: VaultReader):
        assert reader.list_projects() == []

    def test_read_project(self, vault: Path, reader: VaultReader):
        self._make_project(
            vault,
            "pipnesiatest-ea",
            "# Project: Pipnesiatest EA\n"
            "status: operating\n"
            "priority: high\n"
            "created: 2026-01-15\n"
            "goal_anchor: Ship one profitable algo trading system\n"
            "\n"
            "## Description\n"
            "MT5 expert advisor for prop firm trading.\n"
            "\n"
            "## Tech Spec\n"
            "MQL5, deployed to prop firm MT5 account.\n"
            "\n"
            "## MVP Definition\n"
            "Passes prop firm challenge with 10% drawdown limit.\n",
        )
        project = reader.read_project("pipnesiatest-ea")
        assert project.name == "pipnesiatest-ea"
        assert project.status == "operating"
        assert project.priority == "high"
        assert project.created == date(2026, 1, 15)
        assert project.goal_anchor == "Ship one profitable algo trading system"
        assert "MT5 expert advisor" in project.description
        assert project.tech_spec is not None
        assert project.mvp_definition is not None

    def test_read_project_missing_raises(self, reader: VaultReader):
        with pytest.raises(FileNotFoundError):
            reader.read_project("nonexistent-project")


# ---------------------------------------------------------------------------
# VaultWriter tests
# ---------------------------------------------------------------------------


class TestVaultWriterBrainDump:
    def test_append_creates_file(self, vault: Path, writer: VaultWriter):
        entry = BrainDumpEntry(
            timestamp="2026-05-26 14:32",
            type="idea",
            content="telegram bot that posts EA equity curve daily",
            context="while watching MT5 charts",
            state="energized",
            source="app",
        )
        path = writer.append_brain_dump(entry)
        assert path.exists()
        assert path.name == "2026-05.md"

    def test_append_content_correct(self, vault: Path, writer: VaultWriter):
        entry = BrainDumpEntry(
            timestamp="2026-05-26 14:32",
            type="idea",
            content="my idea content",
        )
        path = writer.append_brain_dump(entry)
        text = path.read_text(encoding="utf-8")
        assert "## 2026-05-26 14:32" in text
        assert "type: idea" in text
        assert "content: my idea content" in text
        assert "triage_status: pending" in text

    def test_append_multiple_entries(self, vault: Path, writer: VaultWriter):
        for i in range(3):
            entry = BrainDumpEntry(
                timestamp=f"2026-05-2{i} 10:00",
                type="idea",
                content=f"idea {i}",
            )
            writer.append_brain_dump(entry)
        path = vault / "brain-dump" / "2026-05.md"
        text = path.read_text(encoding="utf-8")
        assert text.count("## 2026-05-") == 3

    def test_append_optional_fields_omitted_when_none(self, vault: Path, writer: VaultWriter):
        entry = BrainDumpEntry(
            timestamp="2026-05-26 08:00",
            type="bug",
            content="spread filter crashes",
        )
        path = writer.append_brain_dump(entry)
        text = path.read_text(encoding="utf-8")
        assert "project:" not in text
        assert "context:" not in text
        assert "state:" not in text
        assert "source:" not in text


class TestVaultWriterGraveyard:
    def _make_verdict(self, verdict_str: str = "KILL") -> IdeaKillerVerdict:
        return IdeaKillerVerdict(
            verdict=verdict_str,  # type: ignore[arg-type]
            checks={
                "goal_anchor": CheckResult(**{"pass": False, "reasoning": "no goal match"}),
                "existing_overlap": CheckResult(**{"pass": True, "reasoning": "no overlap found"}),
                "manual_baseline": CheckResult(**{"pass": False, "reasoning": "never done manually"}),
                "killshot": CheckResult(**{"pass": False, "reasoning": "decisive objection raised"}),
                "existence_test": CheckResult(**{"pass": False, "reasoning": "outcome is vague"}),
            },
            verdict_reasoning="Fails goal anchor and manual baseline checks.",
            park_revival_condition=None,
            related_killed_ideas=[],
        )

    def _make_entry(self) -> BrainDumpEntry:
        return BrainDumpEntry(
            timestamp="2026-05-26 14:32",
            type="idea",
            content="telegram bot that posts EA equity curve daily",
        )

    def test_write_graveyard_creates_file(self, vault: Path, writer: VaultWriter):
        path = writer.write_graveyard("Telegram EA Bot", self._make_verdict(), self._make_entry())
        assert path.exists()
        assert path.suffix == ".md"

    def test_write_graveyard_content(self, vault: Path, writer: VaultWriter):
        path = writer.write_graveyard("Telegram EA Bot", self._make_verdict(), self._make_entry())
        text = path.read_text(encoding="utf-8")
        assert "# Killed: Telegram EA Bot" in text
        assert "verdict: KILL" in text
        assert "telegram bot that posts EA equity curve daily" in text
        assert "goal_anchor" in text.lower() or "Goal anchor" in text
        assert "Fails goal anchor" in text

    def test_write_graveyard_park_revival(self, vault: Path, writer: VaultWriter):
        verdict = self._make_verdict("PARK")
        verdict.park_revival_condition = "Revisit when EA is profitable for 3 months."
        path = writer.write_graveyard("Telegram EA Bot", verdict, self._make_entry())
        text = path.read_text(encoding="utf-8")
        assert "Revisit when EA is profitable" in text

    def test_write_graveyard_slug_from_title(self, vault: Path, writer: VaultWriter):
        path = writer.write_graveyard(
            "My Fancy Idea With Spaces!", self._make_verdict(), self._make_entry()
        )
        assert "my-fancy-idea-with-spaces" in path.name


class TestVaultWriterTask:
    def _make_task(self) -> Task:
        return Task(
            id="001",
            title="Add trailing stop",
            status="queued",
            project="pipnesiatest-ea",
            review_tag="behavioral",
            estimated_diff=120,
            token_budget=40000,
            created=date(2026, 5, 26),
            spec_locked=False,
            spec="Implement a trailing stop that follows price by N pips.",
            acceptance_criteria=[
                "Trailing stop activates after 20 pips profit.",
                "Stop moves only in the direction of the trade.",
            ],
            out_of_scope=["Partial close logic"],
            files_expected=["Experts/pipnesiatest.mq5"],
        )

    def test_write_task_creates_file(self, vault: Path, writer: VaultWriter):
        task = self._make_task()
        path = writer.write_task("pipnesiatest-ea", task)
        assert path.exists()
        assert path.name.startswith("001-")
        assert path.suffix == ".md"

    def test_write_task_content(self, vault: Path, writer: VaultWriter):
        task = self._make_task()
        path = writer.write_task("pipnesiatest-ea", task)
        text = path.read_text(encoding="utf-8")
        assert "# Task 001: Add trailing stop" in text
        assert "status: queued" in text
        assert "review_tag: behavioral" in text
        assert "estimated_diff: 120 lines" in text
        assert "token_budget: 40000" in text
        assert "spec_locked: false" in text
        assert "Implement a trailing stop" in text
        assert "Trailing stop activates after 20 pips profit." in text
        assert "Partial close logic" in text
        assert "Experts/pipnesiatest.mq5" in text

    def test_write_task_slug_in_filename(self, vault: Path, writer: VaultWriter):
        task = self._make_task()
        path = writer.write_task("pipnesiatest-ea", task)
        assert "add-trailing-stop" in path.name

    def test_write_task_no_optional_fields(self, vault: Path, writer: VaultWriter):
        task = Task(
            id="002",
            title="Fix spread filter",
            status="queued",
            project="pipnesiatest-ea",
            review_tag="code",
            created=date(2026, 5, 26),
        )
        path = writer.write_task("pipnesiatest-ea", task)
        text = path.read_text(encoding="utf-8")
        assert "estimated_diff:" not in text
        assert "token_budget:" not in text


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_write_then_read_brain_dump(self, vault: Path, writer: VaultWriter, reader: VaultReader):
        entry = BrainDumpEntry(
            timestamp="2026-05-26 14:32",
            type="idea",
            content="telegram bot that posts EA equity curve daily",
            context="while watching MT5 charts",
            state="energized",
            source="app",
            triage_status="pending",
        )
        writer.append_brain_dump(entry)
        entries = reader.read_brain_dump("2026-05")

        assert len(entries) == 1
        read_back = entries[0]
        assert read_back.timestamp == entry.timestamp
        assert read_back.type == entry.type
        assert read_back.content == entry.content
        assert read_back.context == entry.context
        assert read_back.state == entry.state
        assert read_back.source == entry.source
        assert read_back.triage_status == entry.triage_status

    def test_write_then_read_multiple_brain_dump_entries(
        self, vault: Path, writer: VaultWriter, reader: VaultReader
    ):
        entries_in = [
            BrainDumpEntry(
                timestamp="2026-05-26 09:00",
                type="idea",
                content="first idea",
            ),
            BrainDumpEntry(
                timestamp="2026-05-26 14:32",
                type="feature",
                project="pipnesiatest-ea",
                content="add trailing stop",
                triage_status="classified",
            ),
            BrainDumpEntry(
                timestamp="2026-05-26 18:00",
                type="bug",
                project="pipnesiatest-ea",
                content="spread filter crashes on weekend",
                state="frustrated",
            ),
        ]
        for e in entries_in:
            writer.append_brain_dump(e)

        entries_out = reader.read_brain_dump("2026-05")
        assert len(entries_out) == 3
        assert entries_out[0].type == "idea"
        assert entries_out[1].type == "feature"
        assert entries_out[1].project == "pipnesiatest-ea"
        assert entries_out[2].type == "bug"
        assert entries_out[2].state == "frustrated"
