"""Triage page (textarea input) and graveyard."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from foundry.dashboard import db

BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

router = APIRouter()


def _run_triage(text: str) -> dict:
    """Run the coordinator pipeline on raw text. Returns result dict."""
    from foundry.triage.schema import BrainDumpEntry
    entry = BrainDumpEntry(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        type="idea",
        content=text,
    )
    try:
        from foundry.dashboard.llm import get_dispatcher
        from foundry.triage.coordinator import Coordinator
        llm = get_dispatcher()
        # Coordinator still expects a vault_path for VaultWriter — pass a dummy path.
        # The writer is only called on ADVANCE; we intercept before that.
        import tempfile, os
        dummy_vault = Path(tempfile.gettempdir()) / "foundry_triage_dummy"
        dummy_vault.mkdir(exist_ok=True)
        result = Coordinator(llm, dummy_vault).run(entry)
    except Exception as exc:
        return {"status": "error", "message": str(exc), "verdict": None, "checks": {}}

    verdict_obj = result.verdict
    checks = {}
    if verdict_obj and hasattr(verdict_obj, "checks"):
        for k, v in verdict_obj.checks.items():
            checks[k] = {"pass": getattr(v, "pass_", False), "reasoning": v.reasoning}

    return {
        "status": result.status,
        "message": result.message,
        "verdict": verdict_obj.verdict if verdict_obj and hasattr(verdict_obj, "verdict") else None,
        "verdict_reasoning": getattr(verdict_obj, "verdict_reasoning", ""),
        "park_revival_condition": getattr(verdict_obj, "park_revival_condition", None),
        "checks": checks,
        "tasks": [t.title for t in result.tasks],
    }


@router.get("/triage", response_class=HTMLResponse)
async def triage_page(request: Request) -> HTMLResponse:
    conn = db.get_conn()
    try:
        recent = db.graveyard_list(conn)[:10]
    finally:
        conn.close()
    return templates.TemplateResponse(request, "triage.html", {"recent_graveyard": recent})


@router.post("/triage/run", response_class=HTMLResponse)
async def run_triage(
    request: Request,
    idea_text: str = Form(...),
) -> HTMLResponse:
    result = _run_triage(idea_text.strip())

    # Persist KILL/PARK to graveyard
    if result.get("verdict") in ("KILL", "PARK"):
        conn = db.get_conn()
        try:
            db.graveyard_create(
                conn,
                source_text=idea_text.strip(),
                verdict=result["verdict"],
                reasoning_json=json.dumps({
                    "verdict_reasoning": result.get("verdict_reasoning", ""),
                    "checks": result.get("checks", {}),
                }),
                revival_condition=result.get("park_revival_condition"),
            )
        finally:
            conn.close()

    return templates.TemplateResponse(
        request, "partials/triage_result.html", {"result": result, "idea_text": idea_text}
    )


@router.get("/graveyard", response_class=HTMLResponse)
async def graveyard_page(request: Request, q: str = "") -> HTMLResponse:
    conn = db.get_conn()
    try:
        entries = db.graveyard_list(conn, q=q)
    finally:
        conn.close()
    return templates.TemplateResponse(request, "graveyard.html", {"entries": entries, "q": q})
