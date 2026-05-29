"""Tests for /projects dashboard routes (DB-backed)."""

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
def seeded():
    conn = db.get_conn()
    try:
        pid = db.project_create(conn, name="alpha", description="Alpha project")
        tid = db.task_create(conn, pid, title="First task", status="queued")
    finally:
        conn.close()
    return {"pid": pid, "tid": tid}


def test_projects_list_returns_200(client, seeded):
    r = client.get("/projects")
    assert r.status_code == 200
    assert b"alpha" in r.content


def test_project_card_links_to_detail(client, seeded):
    r = client.get("/projects")
    assert b"/projects/alpha" in r.content


def test_existing_project_returns_200(client, seeded):
    r = client.get("/projects/alpha")
    assert r.status_code == 200
    assert b"alpha" in r.content


def test_tasks_appear_in_detail(client, seeded):
    r = client.get("/projects/alpha")
    assert r.status_code == 200
    assert b"First task" in r.content


def test_project_with_no_tasks_shows_empty_state(client):
    conn = db.get_conn()
    try:
        db.project_create(conn, name="empty-proj")
    finally:
        conn.close()
    r = client.get("/projects/empty-proj")
    assert r.status_code == 200
    assert b"empty-proj" in r.content


def test_back_link_present(client, seeded):
    r = client.get("/projects/alpha")
    assert b"/projects" in r.content


def test_missing_project_returns_404(client):
    r = client.get("/projects/nonexistent")
    assert r.status_code == 404


def test_create_project_redirects(client):
    r = client.post("/projects/new", data={
        "name": "new-proj", "description": "desc",
        "spec": "", "github_url": "", "status": "active", "priority": "medium",
    }, follow_redirects=False)
    assert r.status_code == 303
    assert "/projects/new-proj" in r.headers["location"]


def test_fallback_when_no_db(client):
    # With new architecture there's no vault fallback — missing project returns 404
    r = client.get("/projects/no-such-project")
    assert r.status_code == 404
