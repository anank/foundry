"""Tests for dispatch() — mocks SSH so no real connections are made."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import subprocess

import pytest

from foundry.dashboard import db
from foundry.executor.runner import dispatch


@pytest.fixture
def populated_db(tmp_path: Path):
    db.init_db(tmp_path / "test.db")
    conn = db.get_conn()
    try:
        proj_id = db.project_create(conn, name="my-proj")
        dev_id = db.device_create(conn, device_id="local-mac", display_name="Local Mac",
                                   ssh_host="", ssh_user="")
        db.path_upsert(conn, proj_id, dev_id, "/home/user/my-proj")
        task_id = db.task_create(conn, proj_id, title="Build feature", description="Do the thing")
    finally:
        conn.close()
    return {"proj_id": proj_id, "dev_id": dev_id, "task_id": task_id}


def test_dispatch_local_success(populated_db, monkeypatch):
    monkeypatch.setenv("FOUNDRY_DEVICE_ID", "local-mac")

    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result):
        result = dispatch(populated_db["task_id"], populated_db["dev_id"])

    assert result["status"] == "ok"
    assert "run_id" in result
    assert "command" in result

    # task status should be updated to running
    conn = db.get_conn()
    try:
        task = db.task_get(conn, populated_db["task_id"])
    finally:
        conn.close()
    assert task["status"] == "running"


def test_dispatch_missing_path_returns_error(populated_db, monkeypatch):
    monkeypatch.setenv("FOUNDRY_DEVICE_ID", "local-mac")
    conn = db.get_conn()
    try:
        # Create a second device with no path configured
        dev2_id = db.device_create(conn, device_id="vps", display_name="VPS",
                                    ssh_host="1.2.3.4", ssh_user="ubuntu")
    finally:
        conn.close()

    result = dispatch(populated_db["task_id"], dev2_id)
    assert result["status"] == "error"
    assert "path" in result["error"].lower()


def test_dispatch_missing_task_returns_error(populated_db):
    result = dispatch(99999, populated_db["dev_id"])
    assert result["status"] == "error"
    assert "99999" in result["error"]


def test_dispatch_tmux_launch_failure_returns_error(populated_db, monkeypatch):
    monkeypatch.setenv("FOUNDRY_DEVICE_ID", "local-mac")

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "duplicate session: foundry-task-1"
    mock_result.stdout = ""

    with patch("subprocess.run", return_value=mock_result):
        result = dispatch(populated_db["task_id"], populated_db["dev_id"])

    # non-zero exit from tmux means the session didn't start — surface it as error
    assert result["status"] == "error"
    assert "tmux launch failed" in result["error"]


def test_dispatch_no_tmux_falls_back_to_popen(populated_db, monkeypatch):
    """When tmux is not installed, dispatch uses Popen (Windows / minimal envs)."""
    monkeypatch.setenv("FOUNDRY_DEVICE_ID", "local-mac")

    mock_proc = MagicMock()

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("tmux not found")

    with patch("subprocess.run", side_effect=fake_run), \
         patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        result = dispatch(populated_db["task_id"], populated_db["dev_id"])

    assert result["status"] == "ok"
    assert result["tmux_session"] == ""  # no session when using Popen
    # Popen should have been called with a list (no shell quoting) and cwd set
    call_kwargs = mock_popen.call_args
    assert call_kwargs.kwargs.get("cwd") == "/home/user/my-proj"
    cmd_arg = call_kwargs.args[0]
    assert isinstance(cmd_arg, list)
    assert any("Build feature" in arg for arg in cmd_arg)  # task title passed as direct arg


def test_dispatch_command_not_found_returns_error(populated_db, monkeypatch):
    """If the configured command binary doesn't exist, return a clear error."""
    monkeypatch.setenv("FOUNDRY_DEVICE_ID", "local-mac")

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("tmux not found")

    def fake_popen(*args, **kwargs):
        raise FileNotFoundError("No such file or directory: 'claude'")

    with patch("subprocess.run", side_effect=fake_run), \
         patch("subprocess.Popen", side_effect=fake_popen):
        result = dispatch(populated_db["task_id"], populated_db["dev_id"])

    assert result["status"] == "error"
    assert "not found" in result["error"].lower() or "claude" in result["error"]
