"""Pipeline view — projects grouped by status in kanban-style columns."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).parent.parent

templates = Jinja2Templates(directory=BASE_DIR / "templates")

router = APIRouter()

# The four canonical pipeline statuses, in display order.
PIPELINE_STATUSES = ["operating", "building", "queued", "parked"]


def _vault_path() -> Path:
    return Path(os.environ.get("FOUNDRY_VAULT_PATH", "vault"))


def _db_path(vault_path: Path) -> Path:
    return vault_path / "foundry_index.db"


def _load_from_db(db_path: Path) -> dict[str, list[dict[str, Any]]]:
    """Return projects grouped by status from SQLite.

    Returns an empty dict (not raises) if the DB doesn't exist or the
    projects table is missing — callers fall back to vault scan.
    """
    if not db_path.exists():
        return {}

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT name, status, description FROM projects ORDER BY name"
        ).fetchall()
        conn.close()
    except sqlite3.OperationalError:
        return {}

    grouped: dict[str, list[dict[str, Any]]] = {s: [] for s in PIPELINE_STATUSES}
    for row in rows:
        status = (row["status"] or "").lower()
        if status not in grouped:
            # Unknown status — put in queued so it's visible
            status = "queued"
        grouped[status].append(
            {
                "name": row["name"],
                "description": row["description"] or "",
            }
        )
    return grouped


def _load_from_vault(vault_path: Path) -> dict[str, list[dict[str, Any]]]:
    """Fallback: scan vault/projects/ directories for PROJECT.md files."""
    import re

    projects_dir = vault_path / "projects"
    grouped: dict[str, list[dict[str, Any]]] = {s: [] for s in PIPELINE_STATUSES}

    if not projects_dir.exists():
        return grouped

    try:
        project_dirs = sorted(
            p for p in projects_dir.iterdir()
            if p.is_dir() and not p.name.startswith("_")
        )
    except OSError:
        return grouped

    for proj_dir in project_dirs:
        name = proj_dir.name
        project_md = proj_dir / "PROJECT.md"
        status = "queued"
        description = ""

        if project_md.exists():
            try:
                content = project_md.read_text(encoding="utf-8")
                # Pull status from inline YAML header
                status_match = re.search(r"^status\s*:\s*(\S+)", content, re.MULTILINE | re.IGNORECASE)
                if status_match:
                    status = status_match.group(1).lower()
                # Pull description section
                desc_match = re.search(
                    r"^##\s+Description\s*\n(.*?)(?=^##\s|\Z)",
                    content,
                    re.MULTILINE | re.DOTALL,
                )
                if desc_match:
                    description = desc_match.group(1).strip()
            except OSError:
                pass

        if status not in grouped:
            status = "queued"

        grouped[status].append({"name": name, "description": description})

    return grouped


@router.get("/pipeline", response_class=HTMLResponse)
async def pipeline_page(request: Request):
    vault_path = _vault_path()
    db = _db_path(vault_path)

    grouped = _load_from_db(db)
    if not grouped:
        grouped = _load_from_vault(vault_path)

    # Ensure all four keys are always present
    for status in PIPELINE_STATUSES:
        grouped.setdefault(status, [])

    columns = [
        {"status": s, "label": s.capitalize(), "projects": grouped[s]}
        for s in PIPELINE_STATUSES
    ]

    return templates.TemplateResponse(
        request,
        "pipeline.html",
        {"columns": columns},
    )
