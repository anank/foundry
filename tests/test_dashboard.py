"""Tests for dashboard routes — projects, devices, review, triage, settings."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from foundry.dashboard import db
from foundry.dashboard.app import app


@pytest.fixture(autouse=True)
def init_test_db(tmp_path: Path):
    db.init_db(tmp_path / "test.db")
    yield


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def seeded_db():
    conn = db.get_conn()
    try:
        pid = db.project_create(conn, name="test-proj", description="A test project",
                                 github_url="", status="active", priority="medium")
        did = db.device_create(conn, device_id="local", display_name="Local")
        db.path_upsert(conn, pid, did, "/tmp/test-proj")
        tid = db.task_create(conn, pid, title="Do something", status="queued")
    finally:
        conn.close()
    return {"pid": pid, "did": did, "tid": tid}


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------

def test_home_loads(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Foundry" in r.content


def test_home_shows_project_card(client, seeded_db):
    r = client.get("/")
    assert r.status_code == 200
    assert b"test-proj" in r.content


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def test_projects_list(client, seeded_db):
    r = client.get("/projects")
    assert r.status_code == 200
    assert b"test-proj" in r.content


def test_project_detail(client, seeded_db):
    r = client.get("/projects/test-proj")
    assert r.status_code == 200
    assert b"test-proj" in r.content


def test_project_detail_404(client):
    r = client.get("/projects/nonexistent")
    assert r.status_code == 404


def test_create_project(client):
    r = client.post("/projects/new", data={
        "name": "new-proj", "description": "desc",
        "spec": "", "github_url": "", "status": "active", "priority": "medium",
    }, follow_redirects=False)
    assert r.status_code == 303
    conn = db.get_conn()
    try:
        p = db.project_get_by_name(conn, "new-proj")
    finally:
        conn.close()
    assert p is not None


def test_create_task(client, seeded_db):
    r = client.post("/projects/test-proj/tasks", data={
        "title": "New task", "description": "", "priority": "medium",
    })
    assert r.status_code == 200
    conn = db.get_conn()
    try:
        tasks = db.tasks_list(conn, seeded_db["pid"])
    finally:
        conn.close()
    assert any(t["title"] == "New task" for t in tasks)


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------

def test_devices_list(client, seeded_db):
    r = client.get("/devices")
    assert r.status_code == 200
    assert b"Local" in r.content


def test_create_device(client):
    r = client.post("/devices/new", data={
        "device_id": "vps-1", "display_name": "VPS 1",
        "os": "linux", "ssh_host": "1.2.3.4", "ssh_port": "22",
        "ssh_user": "ubuntu", "notes": "",
    }, follow_redirects=False)
    assert r.status_code == 303
    conn = db.get_conn()
    try:
        d = db.device_get_by_device_id(conn, "vps-1")
    finally:
        conn.close()
    assert d is not None


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------

def test_review_empty(client):
    r = client.get("/review")
    assert r.status_code == 200
    assert b"empty" in r.content.lower() or b"Review" in r.content


def test_review_approve(client, seeded_db):
    conn = db.get_conn()
    try:
        db.task_update(conn, seeded_db["tid"], status="review")
    finally:
        conn.close()

    r = client.post(f"/review/{seeded_db['tid']}/approve")
    assert r.status_code == 200

    conn = db.get_conn()
    try:
        task = db.task_get(conn, seeded_db["tid"])
    finally:
        conn.close()
    assert task["status"] == "approved"


def test_review_reject(client, seeded_db):
    conn = db.get_conn()
    try:
        db.task_update(conn, seeded_db["tid"], status="review")
    finally:
        conn.close()

    r = client.post(f"/review/{seeded_db['tid']}/reject")
    assert r.status_code == 200

    conn = db.get_conn()
    try:
        task = db.task_get(conn, seeded_db["tid"])
    finally:
        conn.close()
    assert task["status"] == "rejected"


# ---------------------------------------------------------------------------
# Graveyard
# ---------------------------------------------------------------------------

def test_graveyard_empty(client):
    r = client.get("/graveyard")
    assert r.status_code == 200


def test_graveyard_with_entries(client):
    conn = db.get_conn()
    try:
        db.graveyard_create(conn, source_text="bad idea", verdict="KILL",
                             reasoning_json='{}')
    finally:
        conn.close()
    r = client.get("/graveyard")
    assert r.status_code == 200
    assert b"KILL" in r.content


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def test_settings_page_loads(client):
    r = client.get("/settings/models")
    assert r.status_code == 200
    assert b"Providers" in r.content


def test_create_provider(client):
    r = client.post("/settings/providers/new", data={
        "name": "Anthropic", "type": "anthropic",
        "base_url": "", "api_key_env_var": "ANTHROPIC_API_KEY",
    })
    assert r.status_code == 200
    conn = db.get_conn()
    try:
        providers = db.llm_providers_list(conn)
    finally:
        conn.close()
    assert any(p["name"] == "Anthropic" for p in providers)


def test_create_model(client):
    conn = db.get_conn()
    try:
        prov_id = db.llm_provider_create(conn, name="Anthropic", type="anthropic",
                                          api_key_env_var="ANTHROPIC_API_KEY")
    finally:
        conn.close()

    r = client.post("/settings/models/new", data={
        "provider_id": str(prov_id), "model_id": "claude-sonnet-4-6",
        "display_name": "Sonnet", "context_window": "200000",
    })
    assert r.status_code == 200
    conn = db.get_conn()
    try:
        models = db.llm_models_list(conn)
    finally:
        conn.close()
    assert any(m["model_id"] == "claude-sonnet-4-6" for m in models)
