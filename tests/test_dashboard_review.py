"""Tests for /review dashboard route (DB-backed)."""

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
def review_task():
    conn = db.get_conn()
    try:
        pid = db.project_create(conn, name="alpha")
        tid = db.task_create(conn, pid, title="Do something", status="review")
    finally:
        conn.close()
    return {"pid": pid, "tid": tid}


def test_review_queue_shows_task(client, review_task):
    r = client.get("/review")
    assert r.status_code == 200
    assert b"Do something" in r.content


def test_approve_updates_task_file(client, review_task):
    r = client.post(f"/review/{review_task['tid']}/approve")
    assert r.status_code == 200
    conn = db.get_conn()
    try:
        task = db.task_get(conn, review_task["tid"])
    finally:
        conn.close()
    assert task["status"] == "approved"


def test_reject_updates_task_file(client, review_task):
    r = client.post(f"/review/{review_task['tid']}/reject")
    assert r.status_code == 200
    conn = db.get_conn()
    try:
        task = db.task_get(conn, review_task["tid"])
    finally:
        conn.close()
    assert task["status"] == "rejected"


def test_revise_updates_status_and_appends_notes(client, review_task):
    r = client.post(f"/review/{review_task['tid']}/revise",
                    data={"notes": "Fix the edge case"})
    assert r.status_code == 200
    conn = db.get_conn()
    try:
        task = db.task_get(conn, review_task["tid"])
    finally:
        conn.close()
    assert task["status"] == "queued"
    assert "Fix the edge case" in task["description"]


def test_revise_without_notes_still_updates_status(client, review_task):
    r = client.post(f"/review/{review_task['tid']}/revise", data={"notes": ""})
    assert r.status_code == 200
    conn = db.get_conn()
    try:
        task = db.task_get(conn, review_task["tid"])
    finally:
        conn.close()
    assert task["status"] == "queued"


def test_action_on_missing_task_does_not_crash(client):
    r = client.post("/review/99999/approve")
    assert r.status_code == 200
