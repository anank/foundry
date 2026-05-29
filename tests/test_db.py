"""Tests for the new DB schema and repository helpers."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from foundry.dashboard import db


@pytest.fixture
def tmp_db(tmp_path: Path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    yield db_path


def test_init_creates_schema(tmp_db):
    conn = db.get_conn()
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    finally:
        conn.close()
    assert "projects" in tables
    assert "devices" in tables
    assert "tasks" in tables
    assert "task_runs" in tables
    assert "llm_providers" in tables
    assert "llm_models" in tables
    assert "llm_roles" in tables
    assert "graveyard_entries" in tables


def test_default_roles_seeded(tmp_db):
    conn = db.get_conn()
    try:
        roles = {r["role_name"] for r in conn.execute("SELECT role_name FROM llm_roles").fetchall()}
    finally:
        conn.close()
    assert "default" in roles
    assert "idea_killer" in roles
    assert "classifier" in roles


def test_project_crud(tmp_db):
    conn = db.get_conn()
    try:
        pid = db.project_create(conn, name="test-proj", description="desc", github_url="https://github.com/x/y")
        p = db.project_get(conn, pid)
        assert p["name"] == "test-proj"
        assert p["github_url"] == "https://github.com/x/y"

        db.project_update(conn, pid, description="updated")
        p2 = db.project_get(conn, pid)
        assert p2["description"] == "updated"

        db.project_delete(conn, pid)
        assert db.project_get(conn, pid) is None
    finally:
        conn.close()


def test_device_crud(tmp_db):
    conn = db.get_conn()
    try:
        did = db.device_create(conn, device_id="my-mac", display_name="My Mac", os="macos",
                               ssh_host="192.168.1.1", ssh_port=22, ssh_user="anang")
        d = db.device_get(conn, did)
        assert d["device_id"] == "my-mac"
        assert d["ssh_host"] == "192.168.1.1"

        d2 = db.device_get_by_device_id(conn, "my-mac")
        assert d2["id"] == did

        db.device_update(conn, did, display_name="Renamed Mac")
        assert db.device_get(conn, did)["display_name"] == "Renamed Mac"

        db.device_delete(conn, did)
        assert db.device_get(conn, did) is None
    finally:
        conn.close()


def test_task_crud_and_next(tmp_db):
    conn = db.get_conn()
    try:
        pid = db.project_create(conn, name="proj")
        t1 = db.task_create(conn, pid, title="First task", priority="low")
        t2 = db.task_create(conn, pid, title="High priority", priority="high")

        next_task = db.task_next(conn, pid)
        assert next_task["id"] == t2  # high priority first

        db.task_update(conn, t2, status="running")
        next_task2 = db.task_next(conn, pid)
        assert next_task2["id"] == t1  # t2 no longer queued
    finally:
        conn.close()


def test_project_device_path_upsert(tmp_db):
    conn = db.get_conn()
    try:
        pid = db.project_create(conn, name="proj")
        did = db.device_create(conn, device_id="vps", display_name="VPS")
        db.path_upsert(conn, pid, did, "/home/anang/proj")
        row = db.path_get(conn, pid, did)
        assert row["local_path"] == "/home/anang/proj"

        # upsert again — should update
        db.path_upsert(conn, pid, did, "/home/anang/proj-v2")
        row2 = db.path_get(conn, pid, did)
        assert row2["local_path"] == "/home/anang/proj-v2"
    finally:
        conn.close()


def test_llm_provider_and_model(tmp_db):
    conn = db.get_conn()
    try:
        prov_id = db.llm_provider_create(conn, name="Anthropic", type="anthropic",
                                          api_key_env_var="ANTHROPIC_API_KEY")
        model_id = db.llm_model_create(conn, prov_id, model_id="claude-sonnet-4-6",
                                        display_name="Sonnet 4.6")
        db.llm_role_assign(conn, "default", model_id)

        cfg = db.llm_config_for_role(conn, "default")
        assert cfg["model_id"] == "claude-sonnet-4-6"
        assert cfg["provider_type"] == "anthropic"
        assert cfg["api_key_env_var"] == "ANTHROPIC_API_KEY"
    finally:
        conn.close()


def test_llm_config_fallback_to_default(tmp_db):
    conn = db.get_conn()
    try:
        prov_id = db.llm_provider_create(conn, name="Anthropic", type="anthropic",
                                          api_key_env_var="ANTHROPIC_API_KEY")
        model_id = db.llm_model_create(conn, prov_id, model_id="claude-haiku-4-5")
        db.llm_role_assign(conn, "default", model_id)

        # classifier has no model assigned — should fall back to default
        cfg = db.llm_config_for_role(conn, "classifier")
        assert cfg["model_id"] == "claude-haiku-4-5"
    finally:
        conn.close()


def test_graveyard_create_and_list(tmp_db):
    conn = db.get_conn()
    try:
        db.graveyard_create(conn, source_text="bad idea", verdict="KILL",
                             reasoning_json='{"verdict_reasoning": "no goal"}')
        db.graveyard_create(conn, source_text="maybe later", verdict="PARK",
                             reasoning_json='{}', revival_condition="after v1")
        entries = db.graveyard_list(conn)
        assert len(entries) == 2
        kills = [e for e in entries if e["verdict"] == "KILL"]
        assert len(kills) == 1

        filtered = db.graveyard_list(conn, q="maybe")
        assert len(filtered) == 1
    finally:
        conn.close()
