"""Projects — CRUD, task management, run dispatch, GitHub commits."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from foundry.dashboard import db

load_dotenv()  # ensure .env is loaded even when module is imported before lifespan

BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

router = APIRouter()

# Simple in-memory commit cache: {github_url: (fetched_at_iso, commits_list)}
_commit_cache: dict[str, tuple[str, list]] = {}
_CACHE_TTL_SECONDS = 300


def _fetch_commits(github_url: str) -> list[dict]:
    """Fetch last 20 commits from GitHub API. Returns [] on any error."""
    import urllib.request
    import urllib.error

    now = datetime.now(timezone.utc)
    cached = _commit_cache.get(github_url)
    if cached:
        fetched_at = datetime.fromisoformat(cached[0])
        if (now - fetched_at).total_seconds() < _CACHE_TTL_SECONDS:
            return cached[1]

    # Parse owner/repo from URL
    # Handles https://github.com/owner/repo and https://github.com/owner/repo.git
    parts = github_url.rstrip("/").rstrip(".git").split("/")
    if len(parts) < 2:
        return []
    owner, repo = parts[-2], parts[-1]

    api_url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=20"
    req = urllib.request.Request(api_url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return []

    commits = []
    for c in data:
        commits.append({
            "sha": c["sha"][:7],
            "message": c["commit"]["message"].splitlines()[0][:80],
            "author": c["commit"]["author"]["name"],
            "date": c["commit"]["author"]["date"][:10],
            "url": c["html_url"],
        })

    _commit_cache[github_url] = (now.isoformat(), commits)
    return commits


# ---------------------------------------------------------------------------
# Project list
# ---------------------------------------------------------------------------

@router.get("/projects", response_class=HTMLResponse)
async def projects_list(request: Request) -> HTMLResponse:
    conn = db.get_conn()
    try:
        projects = db.projects_list(conn)
        for p in projects:
            p["task_count"] = len(db.tasks_list(conn, p["id"]))
    finally:
        conn.close()
    return templates.TemplateResponse(request, "projects.html", {"projects": projects})


# ---------------------------------------------------------------------------
# New project
# ---------------------------------------------------------------------------

@router.get("/projects/new", response_class=HTMLResponse)
async def new_project_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "project_new.html", {})


@router.post("/projects/new", response_class=HTMLResponse)
async def create_project(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    spec: str = Form(""),
    github_url: str = Form(""),
    status: str = Form("active"),
    priority: str = Form("medium"),
) -> HTMLResponse:
    import re
    slug = re.sub(r"[^\w-]", "-", name.lower().strip()).strip("-")
    conn = db.get_conn()
    try:
        project_id = db.project_create(
            conn,
            name=slug,
            description=description,
            spec=spec,
            github_url=github_url,
            status=status,
            priority=priority,
        )
    finally:
        conn.close()

    if request.headers.get("HX-Request") == "true":
        return HTMLResponse(
            f'<div class="rounded bg-green-900 border border-green-700 px-4 py-3 text-green-200 text-sm">'
            f'Project <strong>{slug}</strong> created. '
            f'<a href="/projects/{slug}" class="underline">View →</a>'
            f'</div>'
        )
    return RedirectResponse(url=f"/projects/{slug}", status_code=303)


# ---------------------------------------------------------------------------
# Project detail
# ---------------------------------------------------------------------------

@router.get("/projects/{name}", response_class=HTMLResponse)
async def project_detail(request: Request, name: str) -> HTMLResponse:
    conn = db.get_conn()
    try:
        project = db.project_get_by_name(conn, name)
        if project is None:
            return templates.TemplateResponse(
                request, "404.html", {"message": f"Project '{name}' not found."}, status_code=404
            )
        tasks = db.tasks_list(conn, project["id"])
        device_paths = db.paths_for_project(conn, project["id"])
        runs = db.runs_for_project(conn, project["id"])
        all_devices = db.devices_list(conn)
    finally:
        conn.close()

    commits: list[dict] = []
    if project.get("github_url"):
        commits = _fetch_commits(project["github_url"])

    return templates.TemplateResponse(
        request,
        "project_detail.html",
        {
            "project": project,
            "tasks": tasks,
            "device_paths": device_paths,
            "all_devices": all_devices,
            "runs": runs,
            "commits": commits,
        },
    )


@router.post("/projects/{name}/edit", response_class=HTMLResponse)
async def edit_project(
    request: Request,
    name: str,
    description: str = Form(""),
    spec: str = Form(""),
    github_url: str = Form(""),
    status: str = Form("active"),
    priority: str = Form("medium"),
) -> HTMLResponse:
    conn = db.get_conn()
    try:
        project = db.project_get_by_name(conn, name)
        if project is None:
            return HTMLResponse("Not found", status_code=404)
        db.project_update(
            conn, project["id"],
            description=description, spec=spec,
            github_url=github_url, status=status, priority=priority,
        )
    finally:
        conn.close()
    return RedirectResponse(url=f"/projects/{name}", status_code=303)


@router.post("/projects/{name}/delete")
async def delete_project(request: Request, name: str):
    conn = db.get_conn()
    try:
        project = db.project_get_by_name(conn, name)
        if project:
            db.project_delete(conn, project["id"])
    finally:
        conn.close()
    return RedirectResponse(url="/projects", status_code=303)


# ---------------------------------------------------------------------------
# Device paths
# ---------------------------------------------------------------------------

@router.post("/projects/{name}/paths", response_class=HTMLResponse)
async def upsert_device_path(
    request: Request,
    name: str,
    device_pk: int = Form(...),
    local_path: str = Form(...),
) -> HTMLResponse:
    conn = db.get_conn()
    try:
        project = db.project_get_by_name(conn, name)
        if project is None:
            return HTMLResponse("Not found", status_code=404)
        db.path_upsert(conn, project["id"], device_pk, local_path)
        device_paths = db.paths_for_project(conn, project["id"])
        all_devices = db.devices_list(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "partials/device_paths.html",
        {"project": project, "device_paths": device_paths, "all_devices": all_devices},
    )


@router.post("/projects/{name}/default-device", response_class=HTMLResponse)
async def set_default_device(
    request: Request,
    name: str,
    device_pk: int = Form(...),
) -> HTMLResponse:
    conn = db.get_conn()
    try:
        project = db.project_get_by_name(conn, name)
        if project is None:
            return HTMLResponse("Not found", status_code=404)
        db.project_update(conn, project["id"], default_device_id=device_pk if device_pk > 0 else None)
        project = db.project_get(conn, project["id"])
        device_paths = db.paths_for_project(conn, project["id"])
        all_devices = db.devices_list(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "partials/device_paths.html",
        {"project": project, "device_paths": device_paths, "all_devices": all_devices},
    )


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@router.post("/projects/{name}/tasks", response_class=HTMLResponse)
async def create_task(
    request: Request,
    name: str,
    title: str = Form(...),
    description: str = Form(""),
    priority: str = Form("medium"),
) -> HTMLResponse:
    conn = db.get_conn()
    try:
        project = db.project_get_by_name(conn, name)
        if project is None:
            return HTMLResponse("Not found", status_code=404)
        db.task_create(conn, project["id"], title=title, description=description, priority=priority)
        tasks = db.tasks_list(conn, project["id"])
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "partials/task_list.html", {"project": project, "tasks": tasks}
    )


@router.post("/tasks/{task_id}/status", response_class=HTMLResponse)
async def update_task_status(
    request: Request,
    task_id: int,
    status: str = Form(...),
) -> HTMLResponse:
    conn = db.get_conn()
    try:
        db.task_update(conn, task_id, status=status)
        task = db.task_get(conn, task_id)
    finally:
        conn.close()
    return HTMLResponse(
        f'<span class="text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-300">{task["status"]}</span>'
    )


@router.post("/tasks/{task_id}/delete", response_class=HTMLResponse)
async def delete_task(request: Request, task_id: int) -> HTMLResponse:
    conn = db.get_conn()
    try:
        task = db.task_get(conn, task_id)
        if task:
            project = db.project_get(conn, task["project_id"])
            db.task_delete(conn, task_id)
            tasks = db.tasks_list(conn, task["project_id"])
        else:
            return HTMLResponse("")
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "partials/task_list.html", {"project": project, "tasks": tasks}
    )


# ---------------------------------------------------------------------------
# Run dispatch
# ---------------------------------------------------------------------------

@router.post("/tasks/{task_id}/run/{device_pk}", response_class=HTMLResponse)
async def run_task(request: Request, task_id: int, device_pk: int) -> HTMLResponse:
    import asyncio
    from foundry.executor.runner import dispatch
    result = await asyncio.to_thread(dispatch, task_id, device_pk)
    if result["status"] == "error":
        return HTMLResponse(
            f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:0.7rem;'
            f'padding:0.5rem 0.75rem;background:#2d0a0a;border:1px solid #7f1d1d;border-radius:4px;">'
            f'<span style="color:#fca5a5;">✗ error</span>'
            f'<div style="color:#ef4444;margin-top:0.2rem;">{result["error"]}</div>'
            f'</div>'
        )
    session = result["tmux_session"]
    log = result["log_path"]
    device_name = result.get("device_name", "device")
    is_local = result.get("is_local", True)
    lines = [f'<div style="color:#86efac;font-size:0.72rem;">✓ launched on {device_name}</div>']
    if session:
        attach = f"tmux attach -t {session}" if is_local else f"ssh {device_name} 'tmux attach -t {session}'"
        lines.append(f'<div style="color:#4a5568;margin-top:0.2rem;">session <span style="color:#6ee7b7;">{session}</span></div>')
        lines.append(f'<div style="color:#4a5568;">attach&nbsp;&nbsp;<span style="color:#6ee7b7;">{attach}</span></div>')
    else:
        lines.append(f'<div style="color:#4a5568;margin-top:0.2rem;">(no tmux — running as background process)</div>')
    lines.append(f'<div style="color:#4a5568;">log&nbsp;&nbsp;&nbsp;&nbsp;<span style="color:#4a7a6a;word-break:break-all;">{log}</span></div>')
    return HTMLResponse(
        f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:0.68rem;'
        f'padding:0.5rem 0.75rem;background:#0a1f0a;border:1px solid #14532d;border-radius:4px;line-height:1.6;">'
        + "".join(lines) +
        f'</div>'
    )
