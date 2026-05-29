"""Tests for db module — kept minimal, covers old init() API compatibility."""

from __future__ import annotations

from pathlib import Path
import pytest

from foundry.dashboard import db


def test_get_conn_raises_before_init(tmp_path: Path):
    db._db_path = None
    with pytest.raises(RuntimeError, match="init_db"):
        db.get_conn()


def test_init_and_get_conn(tmp_path: Path):
    db.init_db(tmp_path / "test.db")
    conn = db.get_conn()
    try:
        # Should be able to query schema_version table
        conn.execute("SELECT * FROM projects").fetchall()
    finally:
        conn.close()
