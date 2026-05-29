"""Tests for triage and graveyard dashboard routes (DB-backed)."""

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


def test_triage_page_loads(client):
    r = client.get("/triage")
    assert r.status_code == 200
    assert b"Triage" in r.content


def test_triage_page_shows_recent_graveyard(client):
    conn = db.get_conn()
    try:
        db.graveyard_create(conn, source_text="bad idea", verdict="KILL", reasoning_json="{}")
    finally:
        conn.close()
    r = client.get("/triage")
    assert r.status_code == 200
    assert b"KILL" in r.content


def test_graveyard_page_loads(client):
    r = client.get("/graveyard")
    assert r.status_code == 200
    assert b"Graveyard" in r.content


def test_graveyard_shows_killed_entry(client):
    conn = db.get_conn()
    try:
        db.graveyard_create(conn, source_text="dead idea text", verdict="KILL",
                             reasoning_json='{"verdict_reasoning": "no goal"}')
    finally:
        conn.close()
    r = client.get("/graveyard")
    assert r.status_code == 200
    assert b"KILL" in r.content
    assert b"dead idea text" in r.content


def test_graveyard_shows_parked_entry(client):
    conn = db.get_conn()
    try:
        db.graveyard_create(conn, source_text="parked idea", verdict="PARK",
                             reasoning_json="{}", revival_condition="after v1")
    finally:
        conn.close()
    r = client.get("/graveyard")
    assert r.status_code == 200
    assert b"PARK" in r.content


def test_graveyard_search_filters_results(client):
    conn = db.get_conn()
    try:
        db.graveyard_create(conn, source_text="trading bot idea", verdict="KILL", reasoning_json="{}")
        db.graveyard_create(conn, source_text="todo app idea", verdict="KILL", reasoning_json="{}")
    finally:
        conn.close()
    r = client.get("/graveyard?q=trading")
    assert r.status_code == 200
    assert b"trading" in r.content
    assert b"todo app" not in r.content


def test_graveyard_search_no_results(client):
    conn = db.get_conn()
    try:
        db.graveyard_create(conn, source_text="some idea", verdict="KILL", reasoning_json="{}")
    finally:
        conn.close()
    r = client.get("/graveyard?q=zzznomatch")
    assert r.status_code == 200
    assert b"some idea" not in r.content
