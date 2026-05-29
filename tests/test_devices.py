"""Tests for DeviceManager."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from foundry.dashboard import db
from foundry.devices.manager import DeviceManager


@pytest.fixture
def tmp_db(tmp_path: Path):
    db.init_db(tmp_path / "test.db")
    yield


def test_current_device_id_from_env(tmp_db, monkeypatch):
    monkeypatch.setenv("FOUNDRY_DEVICE_ID", "my-laptop")
    assert DeviceManager.current_device_id() == "my-laptop"


def test_current_device_id_missing(tmp_db, monkeypatch):
    monkeypatch.delenv("FOUNDRY_DEVICE_ID", raising=False)
    assert DeviceManager.current_device_id() is None


def test_is_local_true(tmp_db, monkeypatch):
    monkeypatch.setenv("FOUNDRY_DEVICE_ID", "my-laptop")
    device = {"device_id": "my-laptop"}
    assert DeviceManager.is_local(device) is True


def test_is_local_false(tmp_db, monkeypatch):
    monkeypatch.setenv("FOUNDRY_DEVICE_ID", "my-laptop")
    device = {"device_id": "vps-1"}
    assert DeviceManager.is_local(device) is False


def test_list_and_get(tmp_db):
    conn = db.get_conn()
    try:
        db.device_create(conn, device_id="dev-a", display_name="Dev A")
        db.device_create(conn, device_id="dev-b", display_name="Dev B")
    finally:
        conn.close()

    devices = DeviceManager.list()
    assert len(devices) == 2
    names = {d["device_id"] for d in devices}
    assert "dev-a" in names
    assert "dev-b" in names
