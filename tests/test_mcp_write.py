"""Tests for MCP write tools in foundry/mcp/server.py."""

from __future__ import annotations

import importlib
from pathlib import Path


def _reload_server(monkeypatch, vault_path: Path):
    """Set FOUNDRY_VAULT_PATH and reload the server module so _vault() picks it up."""
    monkeypatch.setenv("FOUNDRY_VAULT_PATH", str(vault_path))
    import foundry.mcp.server as srv
    importlib.reload(srv)
    return srv


# ---------------------------------------------------------------------------
# add_brain_dump
# ---------------------------------------------------------------------------


def test_add_brain_dump_creates_file(tmp_path, monkeypatch):
    """add_brain_dump always writes a file in brain-dump/ without confirm."""
    srv = _reload_server(monkeypatch, tmp_path)

    result = srv.add_brain_dump(content="Test idea content", type="idea", project="")

    brain_dump_dir = tmp_path / "brain-dump"
    files = list(brain_dump_dir.glob("*.md"))
    assert len(files) == 1, "Expected exactly one brain-dump file"
    assert "Created" in result


def test_add_brain_dump_frontmatter(tmp_path, monkeypatch):
    """add_brain_dump writes correct YAML frontmatter including status: pending."""
    srv = _reload_server(monkeypatch, tmp_path)

    srv.add_brain_dump(content="My idea", type="feature", project="algofx")

    files = list((tmp_path / "brain-dump").glob("*.md"))
    text = files[0].read_text(encoding="utf-8")

    assert "type: feature" in text
    assert "project: algofx" in text
    assert "status: pending" in text
    assert "My idea" in text


def test_add_brain_dump_no_project_omits_project_line(tmp_path, monkeypatch):
    """add_brain_dump omits the project line when project is empty."""
    srv = _reload_server(monkeypatch, tmp_path)

    srv.add_brain_dump(content="Idea without project")

    files = list((tmp_path / "brain-dump").glob("*.md"))
    text = files[0].read_text(encoding="utf-8")
    assert "project:" not in text


# ---------------------------------------------------------------------------
# update_principles
# ---------------------------------------------------------------------------


def test_update_principles_without_confirm_returns_preview(tmp_path, monkeypatch):
    """update_principles with confirm=False returns a preview string, does not write."""
    srv = _reload_server(monkeypatch, tmp_path)

    result = srv.update_principles(new_content="New principles text", confirm=False)

    assert "Would overwrite" in result
    assert "confirm=True" in result
    assert not (tmp_path / "principles.md").exists()


def test_update_principles_with_confirm_overwrites_file(tmp_path, monkeypatch):
    """update_principles with confirm=True writes the file."""
    srv = _reload_server(monkeypatch, tmp_path)

    principles_path = tmp_path / "principles.md"
    principles_path.write_text("Old principles", encoding="utf-8")

    result = srv.update_principles(new_content="New principles text", confirm=True)

    assert principles_path.read_text(encoding="utf-8") == "New principles text"
    assert "Updated" in result


# ---------------------------------------------------------------------------
# trigger_triage
# ---------------------------------------------------------------------------


def test_trigger_triage_without_confirm_returns_preview(tmp_path, monkeypatch):
    """trigger_triage with confirm=False returns preview, creates no file."""
    srv = _reload_server(monkeypatch, tmp_path)

    result = srv.trigger_triage(entry_id="2026-05-26-120000", confirm=False)

    assert "Would write" in result
    assert "confirm=True" in result
    assert not (tmp_path / "triage" / "pending").exists()


def test_trigger_triage_with_confirm_creates_trigger_file(tmp_path, monkeypatch):
    """trigger_triage with confirm=True creates the .trigger marker file."""
    srv = _reload_server(monkeypatch, tmp_path)

    result = srv.trigger_triage(entry_id="2026-05-26-120000", confirm=True)

    marker = tmp_path / "triage" / "pending" / "2026-05-26-120000.trigger"
    assert marker.exists()
    assert "Triage queued" in result


# ---------------------------------------------------------------------------
# create_project
# ---------------------------------------------------------------------------


def test_create_project_without_confirm_returns_preview(tmp_path, monkeypatch):
    """create_project with confirm=False returns preview, creates no directory."""
    srv = _reload_server(monkeypatch, tmp_path)

    result = srv.create_project(name="my-project", description="A test project", confirm=False)

    assert "Would create" in result
    assert "confirm=True" in result
    assert not (tmp_path / "projects" / "my-project").exists()


def test_create_project_with_confirm_creates_dir_and_project_md(tmp_path, monkeypatch):
    """create_project with confirm=True creates the project dir and PROJECT.md."""
    srv = _reload_server(monkeypatch, tmp_path)

    result = srv.create_project(name="my-project", description="A test project", confirm=True)

    project_dir = tmp_path / "projects" / "my-project"
    assert project_dir.is_dir()
    project_md = project_dir / "PROJECT.md"
    assert project_md.exists()
    text = project_md.read_text(encoding="utf-8")
    assert "my-project" in text
    assert "A test project" in text
    assert "Created project" in result


# ---------------------------------------------------------------------------
# set_pause
# ---------------------------------------------------------------------------


def test_set_pause_true_with_confirm_creates_pause_file(tmp_path, monkeypatch):
    """set_pause(True, confirm=True) creates vault/.pause."""
    srv = _reload_server(monkeypatch, tmp_path)

    result = srv.set_pause(paused=True, confirm=True)

    pause_file = tmp_path / ".pause"
    assert pause_file.exists()
    assert "paused" in result.lower()


def test_set_pause_false_with_confirm_deletes_pause_file(tmp_path, monkeypatch):
    """set_pause(False, confirm=True) deletes vault/.pause when it exists."""
    srv = _reload_server(monkeypatch, tmp_path)

    pause_file = tmp_path / ".pause"
    pause_file.write_text("paused", encoding="utf-8")

    result = srv.set_pause(paused=False, confirm=True)

    assert not pause_file.exists()
    assert "resumed" in result.lower()


def test_set_pause_false_when_not_paused_returns_message(tmp_path, monkeypatch):
    """set_pause(False, confirm=True) returns a message when .pause does not exist."""
    srv = _reload_server(monkeypatch, tmp_path)

    result = srv.set_pause(paused=False, confirm=True)

    assert "not paused" in result.lower()


def test_set_pause_without_confirm_returns_preview(tmp_path, monkeypatch):
    """set_pause with confirm=False returns preview string, creates no file."""
    srv = _reload_server(monkeypatch, tmp_path)

    result = srv.set_pause(paused=True, confirm=False)

    assert "Would" in result
    assert "confirm=True" in result
    assert not (tmp_path / ".pause").exists()
