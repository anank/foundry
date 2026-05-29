"""Home — card grid of next tasks per project + quick-add widget."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from foundry.dashboard import db

BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    conn = db.get_conn()
    try:
        projects = db.projects_list(conn)
        cards = []
        for p in projects:
            next_task = db.task_next(conn, p["id"])
            devices = db.paths_for_project(conn, p["id"])
            cards.append({
                "project": p,
                "next_task": next_task,
                "devices": devices,
            })
        all_projects = projects
    finally:
        conn.close()

    return templates.TemplateResponse(
        request, "index.html", {"cards": cards, "all_projects": all_projects}
    )


@router.post("/tasks/quick-add", response_class=HTMLResponse)
async def quick_add(
    request: Request,
    title: str = Form(...),
    project_id: int = Form(...),
    description: str = Form(""),
) -> HTMLResponse:
    conn = db.get_conn()
    try:
        task_id = db.task_create(conn, project_id=project_id, title=title, description=description)
        task = db.task_get(conn, task_id)
        project = db.project_get(conn, project_id)
        devices = db.paths_for_project(conn, project_id)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "partials/project_card.html",
        {"card": {"project": project, "next_task": task, "devices": devices}},
    )
