"""SQLite database layer — schema init and repository helpers.

DB path: ~/.foundry/foundry.db (override with FOUNDRY_DB_PATH env var).
Call init_db() once at startup. Use get_conn() anywhere that needs a connection.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_db_path: Path | None = None

SCHEMA_VERSION = 1


def _default_db_path() -> Path:
    raw = os.environ.get("FOUNDRY_DB_PATH", "")
    if raw:
        return Path(raw)
    return Path.home() / ".foundry" / "foundry.db"


def init_db(db_path: Path | None = None) -> None:
    global _db_path
    if db_path is None:
        db_path = _default_db_path()
    _db_path = Path(db_path)
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    try:
        _create_schema(conn)
        conn.commit()
    finally:
        conn.close()


def get_conn() -> sqlite3.Connection:
    if _db_path is None:
        raise RuntimeError("db.init_db() must be called before get_conn()")
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        );

        CREATE TABLE IF NOT EXISTS projects (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            spec        TEXT NOT NULL DEFAULT '',
            github_url  TEXT NOT NULL DEFAULT '',
            status      TEXT NOT NULL DEFAULT 'active',
            priority    TEXT NOT NULL DEFAULT 'medium',
            default_device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS devices (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id    TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            os           TEXT NOT NULL DEFAULT 'linux',
            ssh_host     TEXT NOT NULL DEFAULT '',
            ssh_port     INTEGER NOT NULL DEFAULT 22,
            ssh_user     TEXT NOT NULL DEFAULT '',
            notes        TEXT NOT NULL DEFAULT '',
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS project_device_paths (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            device_id  INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            local_path TEXT NOT NULL,
            UNIQUE(project_id, device_id)
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            title       TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status      TEXT NOT NULL DEFAULT 'queued',
            priority    TEXT NOT NULL DEFAULT 'medium',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS task_runs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id      INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            device_id    INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            tmux_session TEXT NOT NULL DEFAULT '',
            command      TEXT NOT NULL DEFAULT '',
            status       TEXT NOT NULL DEFAULT 'running',
            exit_code    INTEGER,
            log_path     TEXT NOT NULL DEFAULT '',
            started_at   TEXT NOT NULL,
            finished_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS llm_providers (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL UNIQUE,
            type            TEXT NOT NULL DEFAULT 'anthropic',
            base_url        TEXT NOT NULL DEFAULT '',
            api_key_env_var TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS llm_models (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id    INTEGER NOT NULL REFERENCES llm_providers(id) ON DELETE CASCADE,
            model_id       TEXT NOT NULL,
            display_name   TEXT NOT NULL DEFAULT '',
            context_window INTEGER NOT NULL DEFAULT 200000,
            UNIQUE(provider_id, model_id)
        );

        CREATE TABLE IF NOT EXISTS llm_roles (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            role_name  TEXT NOT NULL UNIQUE,
            model_id   INTEGER REFERENCES llm_models(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS graveyard_entries (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            source_text      TEXT NOT NULL,
            verdict          TEXT NOT NULL,
            reasoning_json   TEXT NOT NULL DEFAULT '{}',
            killed_at        TEXT NOT NULL,
            revival_condition TEXT
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );
    """)

    # Seed default roles if table is empty
    count = conn.execute("SELECT COUNT(*) FROM llm_roles").fetchone()[0]
    if count == 0:
        roles = [
            "default", "classifier", "idea_killer", "feature_killer",
            "bug_triage", "interviewer", "critic", "atomizer", "task_tagger",
        ]
        for r in roles:
            conn.execute(
                "INSERT OR IGNORE INTO llm_roles (role_name, model_id) VALUES (?, NULL)",
                (r,),
            )

    # Seed default app settings
    defaults = {
        "run_command": "claude --dangerously-skip-permissions",
        "use_tmux": "true",
    }
    for key, value in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
            (key, value),
        )

    # Migrations — safe to run repeatedly
    _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply incremental schema changes to existing DBs."""
    # Add default_device_id to projects if missing
    cols = {r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()}
    if "default_device_id" not in cols:
        conn.execute("ALTER TABLE projects ADD COLUMN default_device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL")
        conn.commit()


# ---------------------------------------------------------------------------
# Projects repo
# ---------------------------------------------------------------------------

def projects_list(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM projects ORDER BY priority DESC, name ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def project_get(conn: sqlite3.Connection, project_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return dict(row) if row else None


def project_get_by_name(conn: sqlite3.Connection, name: str) -> dict | None:
    row = conn.execute("SELECT * FROM projects WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else None


def project_create(
    conn: sqlite3.Connection,
    name: str,
    description: str = "",
    spec: str = "",
    github_url: str = "",
    status: str = "active",
    priority: str = "medium",
) -> int:
    now = _now()
    cur = conn.execute(
        "INSERT INTO projects (name, description, spec, github_url, status, priority, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, description, spec, github_url, status, priority, now, now),
    )
    conn.commit()
    return cur.lastrowid


def project_update(conn: sqlite3.Connection, project_id: int, **fields) -> None:
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [project_id]
    conn.execute(f"UPDATE projects SET {set_clause} WHERE id = ?", values)
    conn.commit()


def project_delete(conn: sqlite3.Connection, project_id: int) -> None:
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Devices repo
# ---------------------------------------------------------------------------

def devices_list(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM devices ORDER BY display_name ASC").fetchall()
    return [dict(r) for r in rows]


def device_get(conn: sqlite3.Connection, device_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    return dict(row) if row else None


def device_get_by_device_id(conn: sqlite3.Connection, device_id_str: str) -> dict | None:
    row = conn.execute("SELECT * FROM devices WHERE device_id = ?", (device_id_str,)).fetchone()
    return dict(row) if row else None


def device_create(
    conn: sqlite3.Connection,
    device_id: str,
    display_name: str,
    os: str = "linux",
    ssh_host: str = "",
    ssh_port: int = 22,
    ssh_user: str = "",
    notes: str = "",
) -> int:
    now = _now()
    cur = conn.execute(
        "INSERT INTO devices (device_id, display_name, os, ssh_host, ssh_port, ssh_user, notes, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (device_id, display_name, os, ssh_host, ssh_port, ssh_user, notes, now, now),
    )
    conn.commit()
    return cur.lastrowid


def device_update(conn: sqlite3.Connection, device_pk: int, **fields) -> None:
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [device_pk]
    conn.execute(f"UPDATE devices SET {set_clause} WHERE id = ?", values)
    conn.commit()


def device_delete(conn: sqlite3.Connection, device_pk: int) -> None:
    conn.execute("DELETE FROM devices WHERE id = ?", (device_pk,))
    conn.commit()


# ---------------------------------------------------------------------------
# Project-device paths repo
# ---------------------------------------------------------------------------

def path_get(conn: sqlite3.Connection, project_id: int, device_pk: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM project_device_paths WHERE project_id = ? AND device_id = ?",
        (project_id, device_pk),
    ).fetchone()
    return dict(row) if row else None


def path_upsert(conn: sqlite3.Connection, project_id: int, device_pk: int, local_path: str) -> None:
    conn.execute(
        "INSERT INTO project_device_paths (project_id, device_id, local_path) VALUES (?, ?, ?) "
        "ON CONFLICT(project_id, device_id) DO UPDATE SET local_path = excluded.local_path",
        (project_id, device_pk, local_path),
    )
    conn.commit()


def paths_for_project(conn: sqlite3.Connection, project_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT pdp.id, pdp.project_id, pdp.device_id as device_pk, pdp.local_path,
                  d.device_id, d.display_name
           FROM project_device_paths pdp
           JOIN devices d ON d.id = pdp.device_id
           WHERE pdp.project_id = ?""",
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Tasks repo
# ---------------------------------------------------------------------------

def tasks_list(conn: sqlite3.Connection, project_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM tasks WHERE project_id = ? ORDER BY priority DESC, created_at ASC",
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def task_get(conn: sqlite3.Connection, task_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


def task_next(conn: sqlite3.Connection, project_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM tasks WHERE project_id = ? AND status = 'queued' "
        "ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, created_at ASC LIMIT 1",
        (project_id,),
    ).fetchone()
    return dict(row) if row else None


def task_create(
    conn: sqlite3.Connection,
    project_id: int,
    title: str,
    description: str = "",
    status: str = "queued",
    priority: str = "medium",
) -> int:
    now = _now()
    cur = conn.execute(
        "INSERT INTO tasks (project_id, title, description, status, priority, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (project_id, title, description, status, priority, now, now),
    )
    conn.commit()
    return cur.lastrowid


def task_update(conn: sqlite3.Connection, task_id: int, **fields) -> None:
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [task_id]
    conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
    conn.commit()


def task_delete(conn: sqlite3.Connection, task_id: int) -> None:
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()


def tasks_for_review(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT t.*, p.name as project_name
           FROM tasks t JOIN projects p ON p.id = t.project_id
           WHERE t.status = 'review'
           ORDER BY t.updated_at DESC""",
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Task runs repo
# ---------------------------------------------------------------------------

def run_create(
    conn: sqlite3.Connection,
    task_id: int,
    device_pk: int,
    tmux_session: str,
    command: str,
    log_path: str,
) -> int:
    now = _now()
    cur = conn.execute(
        "INSERT INTO task_runs (task_id, device_id, tmux_session, command, status, log_path, started_at) "
        "VALUES (?, ?, ?, ?, 'running', ?, ?)",
        (task_id, device_pk, tmux_session, command, log_path, now),
    )
    conn.commit()
    return cur.lastrowid


def run_update(conn: sqlite3.Connection, run_id: int, **fields) -> None:
    if "finished_at" not in fields:
        fields["finished_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [run_id]
    conn.execute(f"UPDATE task_runs SET {set_clause} WHERE id = ?", values)
    conn.commit()


def runs_for_project(conn: sqlite3.Connection, project_id: int, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        """SELECT tr.*, t.title as task_title, d.display_name as device_name
           FROM task_runs tr
           JOIN tasks t ON t.id = tr.task_id
           JOIN devices d ON d.id = tr.device_id
           WHERE t.project_id = ?
           ORDER BY tr.started_at DESC LIMIT ?""",
        (project_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# LLM config repo
# ---------------------------------------------------------------------------

def llm_providers_list(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM llm_providers ORDER BY name ASC").fetchall()
    return [dict(r) for r in rows]


def llm_provider_get(conn: sqlite3.Connection, provider_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM llm_providers WHERE id = ?", (provider_id,)).fetchone()
    return dict(row) if row else None


def llm_provider_create(
    conn: sqlite3.Connection,
    name: str,
    type: str,
    base_url: str = "",
    api_key_env_var: str = "",
) -> int:
    now = _now()
    cur = conn.execute(
        "INSERT INTO llm_providers (name, type, base_url, api_key_env_var, created_at) VALUES (?, ?, ?, ?, ?)",
        (name, type, base_url, api_key_env_var, now),
    )
    conn.commit()
    return cur.lastrowid


def llm_provider_update(conn: sqlite3.Connection, provider_id: int, **fields) -> None:
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [provider_id]
    conn.execute(f"UPDATE llm_providers SET {set_clause} WHERE id = ?", values)
    conn.commit()


def llm_provider_delete(conn: sqlite3.Connection, provider_id: int) -> None:
    conn.execute("DELETE FROM llm_providers WHERE id = ?", (provider_id,))
    conn.commit()


def llm_models_list(conn: sqlite3.Connection, provider_id: int | None = None) -> list[dict]:
    if provider_id is not None:
        rows = conn.execute(
            """SELECT m.*, p.name as provider_name, p.type as provider_type
               FROM llm_models m JOIN llm_providers p ON p.id = m.provider_id
               WHERE m.provider_id = ? ORDER BY m.display_name ASC""",
            (provider_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT m.*, p.name as provider_name, p.type as provider_type
               FROM llm_models m JOIN llm_providers p ON p.id = m.provider_id
               ORDER BY p.name ASC, m.display_name ASC"""
        ).fetchall()
    return [dict(r) for r in rows]


def llm_model_create(
    conn: sqlite3.Connection,
    provider_id: int,
    model_id: str,
    display_name: str = "",
    context_window: int = 200000,
) -> int:
    cur = conn.execute(
        "INSERT INTO llm_models (provider_id, model_id, display_name, context_window) VALUES (?, ?, ?, ?)",
        (provider_id, model_id, display_name or model_id, context_window),
    )
    conn.commit()
    return cur.lastrowid


def llm_model_delete(conn: sqlite3.Connection, model_pk: int) -> None:
    conn.execute("DELETE FROM llm_models WHERE id = ?", (model_pk,))
    conn.commit()


def llm_roles_list(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT r.*, m.model_id, m.display_name as model_display_name,
                  p.name as provider_name
           FROM llm_roles r
           LEFT JOIN llm_models m ON m.id = r.model_id
           LEFT JOIN llm_providers p ON p.id = m.provider_id
           ORDER BY r.role_name ASC"""
    ).fetchall()
    return [dict(r) for r in rows]


def llm_role_assign(conn: sqlite3.Connection, role_name: str, model_pk: int | None) -> None:
    conn.execute(
        "INSERT INTO llm_roles (role_name, model_id) VALUES (?, ?) "
        "ON CONFLICT(role_name) DO UPDATE SET model_id = excluded.model_id",
        (role_name, model_pk),
    )
    conn.commit()


def llm_config_for_role(conn: sqlite3.Connection, role: str) -> dict | None:
    """Return provider+model config for a role, falling back to 'default'."""
    row = conn.execute(
        """SELECT p.name as provider_name, p.type as provider_type,
                  p.base_url, p.api_key_env_var,
                  m.model_id, m.display_name
           FROM llm_roles r
           JOIN llm_models m ON m.id = r.model_id
           JOIN llm_providers p ON p.id = m.provider_id
           WHERE r.role_name = ?""",
        (role,),
    ).fetchone()
    if row:
        return dict(row)
    # fallback to default role
    if role != "default":
        return llm_config_for_role(conn, "default")
    return None


# ---------------------------------------------------------------------------
# Graveyard repo
# ---------------------------------------------------------------------------

def graveyard_list(conn: sqlite3.Connection, q: str = "") -> list[dict]:
    if q:
        rows = conn.execute(
            "SELECT * FROM graveyard_entries WHERE source_text LIKE ? OR reasoning_json LIKE ? "
            "ORDER BY killed_at DESC",
            (f"%{q}%", f"%{q}%"),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM graveyard_entries ORDER BY killed_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def graveyard_create(
    conn: sqlite3.Connection,
    source_text: str,
    verdict: str,
    reasoning_json: str,
    revival_condition: str | None = None,
) -> int:
    now = _now()
    cur = conn.execute(
        "INSERT INTO graveyard_entries (source_text, verdict, reasoning_json, killed_at, revival_condition) "
        "VALUES (?, ?, ?, ?, ?)",
        (source_text, verdict, reasoning_json, now, revival_condition),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# App settings repo
# ---------------------------------------------------------------------------

def setting_get(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def setting_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def settings_all(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    return {r["key"]: r["value"] for r in rows}
