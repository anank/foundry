"""Review queue — tasks awaiting review with approve/reject/revise actions."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from foundry.dashboard import db

BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

router = APIRouter()


@router.get("/review", response_class=HTMLResponse)
async def review_queue(request: Request) -> HTMLResponse:
    conn = db.get_conn()
    try:
        tasks = db.tasks_for_review(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(request, "review.html", {"tasks": tasks})


@router.post("/review/{task_id}/approve", response_class=HTMLResponse)
async def approve_task(request: Request, task_id: int) -> HTMLResponse:
    conn = db.get_conn()
    try:
        db.task_update(conn, task_id, status="approved")
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "review_card_done.html",
        {"task_id": task_id, "action": "approved", "action_class": "text-green-400"},
    )


@router.post("/review/{task_id}/reject", response_class=HTMLResponse)
async def reject_task(request: Request, task_id: int) -> HTMLResponse:
    conn = db.get_conn()
    try:
        db.task_update(conn, task_id, status="rejected")
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "review_card_done.html",
        {"task_id": task_id, "action": "rejected", "action_class": "text-red-400"},
    )


@router.post("/review/{task_id}/revise", response_class=HTMLResponse)
async def revise_task(
    request: Request,
    task_id: int,
    notes: str = Form(""),
) -> HTMLResponse:
    conn = db.get_conn()
    try:
        task = db.task_get(conn, task_id)
        if task:
            new_desc = task["description"]
            if notes.strip():
                new_desc = (new_desc + f"\n\nRevision notes: {notes.strip()}").strip()
            db.task_update(conn, task_id, status="queued", description=new_desc)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "review_card_done.html",
        {"task_id": task_id, "action": "sent back for revision", "action_class": "text-yellow-400"},
    )
