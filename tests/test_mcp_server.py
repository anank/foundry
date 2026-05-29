"""Tests for foundry/mcp/server.py — read-only MCP tools.

All tests use tmp_path fixtures and monkeypatch FOUNDRY_VAULT_PATH.
No real vault or API calls required.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Import the tool functions directly (not via the MCP protocol layer)
from foundry.mcp.server import (
    get_brain_dump,
    get_existing_systems,
    get_goals,
    get_pipeline,
    get_principles,
    get_project,
    list_projects,
    search_graveyard,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# get_goals
# ---------------------------------------------------------------------------


def test_get_goals_returns_file_content(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))
    _write(tmp_path / "goals.md", "# Goals\n\n- Ship things\n- Stay focused\n")

    result = get_goals()

    assert "Ship things" in result
    assert "Stay focused" in result


def test_get_goals_missing_returns_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))

    result = get_goals()

    assert result == "Not found."


# ---------------------------------------------------------------------------
# get_principles
# ---------------------------------------------------------------------------


def test_get_principles_returns_file_content(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))
    _write(tmp_path / "principles.md", "# Principles\n\n- Default to rejection\n")

    result = get_principles()

    assert "Default to rejection" in result


def test_get_principles_missing_returns_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))

    result = get_principles()

    assert result == "Not found."


# ---------------------------------------------------------------------------
# get_existing_systems
# ---------------------------------------------------------------------------


def test_get_existing_systems_returns_file_content(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))
    _write(
        tmp_path / "existing-systems.md",
        "## Pipnesiatest EA\ndescription: MT5 expert advisor\nstatus: operating\n",
    )

    result = get_existing_systems()

    assert "Pipnesiatest EA" in result
    assert "operating" in result


def test_get_existing_systems_missing_returns_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))

    result = get_existing_systems()

    assert result == "Not found."


# ---------------------------------------------------------------------------
# list_projects
# ---------------------------------------------------------------------------


def test_list_projects_empty_vault_returns_no_projects(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))
    # projects/ dir doesn't exist at all
    result = list_projects()
    assert result == "No projects found."


def test_list_projects_empty_projects_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))
    (tmp_path / "projects").mkdir()

    result = list_projects()

    assert result == "No projects found."


def test_list_projects_shows_name_and_status(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))
    _write(
        tmp_path / "projects" / "algo-trader" / "PROJECT.md",
        "---\nstatus: building\npriority: high\n---\n\nAn algo trading project.\n",
    )

    result = list_projects()

    assert "algo-trader" in result
    assert "building" in result


def test_list_projects_inline_yaml_fallback(tmp_path, monkeypatch):
    """PROJECT.md without frontmatter delimiters — inline YAML fallback."""
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))
    _write(
        tmp_path / "projects" / "content-system" / "PROJECT.md",
        "status: operating\npriority: medium\n\n## Description\nContent pipeline.\n",
    )

    result = list_projects()

    assert "content-system" in result
    assert "operating" in result


def test_list_projects_skips_underscore_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))
    _write(tmp_path / "projects" / "_archive" / "PROJECT.md", "status: parked\n")
    _write(tmp_path / "projects" / "real-project" / "PROJECT.md", "status: queued\n")

    result = list_projects()

    assert "_archive" not in result
    assert "real-project" in result


# ---------------------------------------------------------------------------
# get_project
# ---------------------------------------------------------------------------


def test_get_project_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))

    result = get_project("nonexistent")

    assert "not found" in result.lower()


def test_get_project_returns_content(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))
    _write(
        tmp_path / "projects" / "my-project" / "PROJECT.md",
        "---\nstatus: queued\n---\n\n## Description\nA cool project.\n",
    )

    result = get_project("my-project")

    assert "my-project" in result
    assert "A cool project." in result


def test_get_project_lists_tasks(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))
    _write(
        tmp_path / "projects" / "my-project" / "PROJECT.md",
        "---\nstatus: building\n---\n\n## Description\nProject with tasks.\n",
    )
    _write(
        tmp_path / "projects" / "my-project" / "tasks" / "001-setup.md",
        "---\nstatus: approved\n---\n\n# Task 1.1: Setup\n",
    )
    _write(
        tmp_path / "projects" / "my-project" / "tasks" / "002-implement.md",
        "---\nstatus: queued\n---\n\n# Task 1.2: Implement\n",
    )

    result = get_project("my-project")

    assert "001-setup" in result
    assert "002-implement" in result
    assert "approved" in result
    assert "queued" in result


# ---------------------------------------------------------------------------
# get_pipeline
# ---------------------------------------------------------------------------


def test_get_pipeline_groups_by_status(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))
    _write(
        tmp_path / "projects" / "alpha" / "PROJECT.md",
        "---\nstatus: operating\n---\n",
    )
    _write(
        tmp_path / "projects" / "beta" / "PROJECT.md",
        "---\nstatus: building\n---\n",
    )
    _write(
        tmp_path / "projects" / "gamma" / "PROJECT.md",
        "---\nstatus: queued\n---\n",
    )
    _write(
        tmp_path / "projects" / "delta" / "PROJECT.md",
        "---\nstatus: parked\n---\n",
    )

    result = get_pipeline()

    assert "Operating" in result and "alpha" in result
    assert "Building" in result and "beta" in result
    assert "Queued" in result and "gamma" in result
    assert "Parked" in result and "delta" in result


def test_get_pipeline_empty_returns_no_projects(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))

    result = get_pipeline()

    assert result == "No projects found."


def test_get_pipeline_counts_are_correct(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))
    for name in ("proj-a", "proj-b"):
        _write(
            tmp_path / "projects" / name / "PROJECT.md",
            "---\nstatus: queued\n---\n",
        )

    result = get_pipeline()

    assert "**Queued** (2)" in result


# ---------------------------------------------------------------------------
# search_graveyard
# ---------------------------------------------------------------------------


def test_search_graveyard_finds_match(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))
    _write(
        tmp_path / "graveyard" / "2026-01-blockchain-crm.md",
        "---\nverdict: KILL\n---\n\nA blockchain-based CRM for small businesses.\n",
    )

    result = search_graveyard("blockchain")

    assert "2026-01-blockchain-crm" in result
    assert "1 match" in result


def test_search_graveyard_case_insensitive(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))
    _write(
        tmp_path / "graveyard" / "idea.md",
        "---\nverdict: KILL\n---\n\nAI-powered Blockchain solution.\n",
    )

    result = search_graveyard("BLOCKCHAIN")

    assert "idea" in result


def test_search_graveyard_no_match(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))
    _write(
        tmp_path / "graveyard" / "idea.md",
        "---\nverdict: KILL\n---\n\nSomething unrelated.\n",
    )

    result = search_graveyard("quantum")

    assert "No graveyard entries matching" in result


def test_search_graveyard_missing_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))

    result = search_graveyard("anything")

    assert "No graveyard entries found." == result


# ---------------------------------------------------------------------------
# get_brain_dump
# ---------------------------------------------------------------------------


def _brain_dump_entry(tmp_path: Path, filename: str, triage_status: str, content: str = "An idea.") -> None:
    _write(
        tmp_path / "brain-dump" / filename,
        f"---\ntype: idea\ntriage_status: {triage_status}\n---\n\n{content}\n",
    )


def test_get_brain_dump_filters_by_status(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))
    _brain_dump_entry(tmp_path, "entry-pending.md", "pending", "Pending idea.")
    _brain_dump_entry(tmp_path, "entry-killed.md", "killed", "Killed idea.")

    result = get_brain_dump(status="pending")

    assert "entry-pending" in result
    assert "entry-killed" not in result


def test_get_brain_dump_all_returns_everything(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))
    _brain_dump_entry(tmp_path, "entry-a.md", "pending")
    _brain_dump_entry(tmp_path, "entry-b.md", "killed")
    _brain_dump_entry(tmp_path, "entry-c.md", "advanced")

    result = get_brain_dump(status="all")

    assert "entry-a" in result
    assert "entry-b" in result
    assert "entry-c" in result


def test_get_brain_dump_empty_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))
    (tmp_path / "brain-dump").mkdir()

    result = get_brain_dump()

    assert "No brain dump entries found." == result


def test_get_brain_dump_missing_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))

    result = get_brain_dump()

    assert "No brain dump entries found." == result


def test_get_brain_dump_no_match_for_status(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))
    _brain_dump_entry(tmp_path, "entry.md", "pending")

    result = get_brain_dump(status="killed")

    assert "No brain dump entries found for status='killed'." == result


def test_get_brain_dump_shows_content_preview(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))
    _brain_dump_entry(tmp_path, "entry.md", "pending", "Build a rocket ship.")

    result = get_brain_dump(status="pending")

    assert "Build a rocket ship." in result


def test_get_brain_dump_default_status_is_pending(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(tmp_path))
    _brain_dump_entry(tmp_path, "pending-entry.md", "pending")
    _brain_dump_entry(tmp_path, "killed-entry.md", "killed")

    # Call with no arguments — default is "pending"
    result = get_brain_dump()

    assert "pending-entry" in result
    assert "killed-entry" not in result
