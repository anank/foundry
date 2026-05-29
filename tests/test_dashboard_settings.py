"""Tests for /settings/models dashboard routes (DB-backed)."""

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


def test_settings_page_returns_200(client):
    r = client.get("/settings/models")
    assert r.status_code == 200


def test_renders_providers_section(client):
    r = client.get("/settings/models")
    assert b"Providers" in r.content


def test_renders_models_section(client):
    r = client.get("/settings/models")
    assert b"Models" in r.content


def test_renders_roles_section(client):
    r = client.get("/settings/models")
    assert b"Roles" in r.content


def test_add_provider(client):
    r = client.post("/settings/providers/new", data={
        "name": "Anthropic", "type": "anthropic",
        "base_url": "", "api_key_env_var": "ANTHROPIC_API_KEY",
    })
    assert r.status_code == 200
    assert b"Anthropic" in r.content


def test_add_model(client):
    conn = db.get_conn()
    try:
        prov_id = db.llm_provider_create(conn, name="Anthropic", type="anthropic",
                                          api_key_env_var="ANTHROPIC_API_KEY")
    finally:
        conn.close()
    r = client.post("/settings/models/new", data={
        "provider_id": str(prov_id),
        "model_id": "claude-sonnet-4-6",
        "display_name": "Sonnet",
        "context_window": "200000",
    })
    assert r.status_code == 200
    assert b"claude-sonnet-4-6" in r.content


def test_assign_role(client):
    conn = db.get_conn()
    try:
        prov_id = db.llm_provider_create(conn, name="Anthropic", type="anthropic",
                                          api_key_env_var="ANTHROPIC_API_KEY")
        model_pk = db.llm_model_create(conn, prov_id, model_id="claude-haiku-4-5")
    finally:
        conn.close()
    r = client.post("/settings/roles/default/assign", data={"model_pk": str(model_pk)})
    assert r.status_code == 200
    conn = db.get_conn()
    try:
        cfg = db.llm_config_for_role(conn, "default")
    finally:
        conn.close()
    assert cfg["model_id"] == "claude-haiku-4-5"


def test_delete_provider(client):
    conn = db.get_conn()
    try:
        prov_id = db.llm_provider_create(conn, name="ToDelete", type="anthropic",
                                          api_key_env_var="KEY")
    finally:
        conn.close()
    r = client.post(f"/settings/providers/{prov_id}/delete")
    assert r.status_code == 200
    conn = db.get_conn()
    try:
        providers = db.llm_providers_list(conn)
    finally:
        conn.close()
    assert not any(p["name"] == "ToDelete" for p in providers)
