"""DeviceManager — resolves the current device and checks locality."""

from __future__ import annotations

import os

from foundry.dashboard import db


class DeviceManager:
    @staticmethod
    def current_device_id() -> str | None:
        return os.environ.get("FOUNDRY_DEVICE_ID")

    @staticmethod
    def is_local(device: dict) -> bool:
        current = DeviceManager.current_device_id()
        if not current:
            return False
        return device["device_id"] == current

    @staticmethod
    def list() -> list[dict]:
        conn = db.get_conn()
        try:
            return db.devices_list(conn)
        finally:
            conn.close()

    @staticmethod
    def get(device_pk: int) -> dict | None:
        conn = db.get_conn()
        try:
            return db.device_get(conn, device_pk)
        finally:
            conn.close()

    @staticmethod
    def get_by_device_id(device_id_str: str) -> dict | None:
        conn = db.get_conn()
        try:
            return db.device_get_by_device_id(conn, device_id_str)
        finally:
            conn.close()
