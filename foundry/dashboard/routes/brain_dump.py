"""Brain dump submission route for the Foundry dashboard."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

router = APIRouter()


def _vault_path() -> Path:
    return Path(os.environ.get("FOUNDRY_VAULT_PATH", "vault"))


def _write_brain_dump(content: str, type_: str, project: str) -> tuple[Path, str]:
    """Write a brain dump entry as a standalone YAML-frontmatter markdown file.

    Returns (file_path, stem).
    """
    vault = _vault_path()
    brain_dump_dir = vault / "brain-dump"
    brain_dump_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    stem = now.strftime("%Y-%m-%d-%H%M%S")
    filename = f"{stem}.md"
    path = brain_dump_dir / filename

    frontmatter_lines = [
        "---\n",
        f"timestamp: {now.strftime('%Y-%m-%d %H:%M')}\n",
        f"type: {type_}\n",
    ]
    if project:
        frontmatter_lines.append(f"project: {project}\n")
    frontmatter_lines.append("status: pending\n")
    frontmatter_lines.append("---\n\n")

    path.write_text("".join(frontmatter_lines) + content + "\n", encoding="utf-8")
    return path, stem


def _write_trigger(stem: str) -> Path:
    """Write a trigger file to vault/triage/pending/<stem>.trigger."""
    vault = _vault_path()
    pending_dir = vault / "triage" / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    trigger_path = pending_dir / f"{stem}.trigger"
    trigger_path.write_text(stem + "\n", encoding="utf-8")
    return trigger_path


def _triage_result_banner(result: dict) -> str:
    status = result.get("status", "error")
    message = result.get("message", "")
    verdict = result.get("verdict")
    tasks = result.get("tasks", [])

    if status == "error":
        color = "red"
        label = "Error"
        detail = message
    elif status == "killed":
        color = "red"
        label = "KILLED"
        detail = message or verdict or ""
    elif status == "parked":
        color = "yellow"
        label = "PARKED"
        detail = message or ""
    elif status == "advanced":
        color = "green"
        label = "ADVANCED"
        detail = f"Tasks created: {', '.join(tasks)}" if tasks else message
    elif status == "needs_input":
        color = "blue"
        label = "Needs Input"
        detail = message
    else:
        color = "gray"
        label = status
        detail = message

    return (
        f'<div id="confirmation-banner" '
        f'class="rounded-md bg-{color}-900 border border-{color}-700 px-4 py-3 text-{color}-200 text-sm">'
        f'<span class="font-semibold">{label}</span>'
        f'{" — " + detail if detail else ""}'
        f'</div>'
    )


def _confirmation_banner(triage: bool) -> str:
    if triage:
        msg = "Saved and queued for triage."
    else:
        msg = "Saved for later."
    return (
        f'<div id="confirmation-banner" '
        f'class="rounded-md bg-green-900 border border-green-700 px-4 py-3 text-green-200 text-sm">'
        f'{msg}'
        f'</div>'
    )


@router.get("/brain-dump", response_class=HTMLResponse)
async def brain_dump_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "brain_dump.html")


@router.post("/brain-dump", response_class=HTMLResponse)
async def submit_brain_dump(
    request: Request,
    content: str = Form(...),
    type: str = Form("idea"),
    project: str = Form(""),
) -> HTMLResponse:
    triage = request.query_params.get("triage") == "1"

    _file_path, stem = _write_brain_dump(content, type, project)

    is_htmx = request.headers.get("HX-Request") == "true"

    if triage:
        # Run triage immediately and return result
        from foundry.dashboard.routes.triage import _run_triage_for_entry
        result = _run_triage_for_entry(stem)
        if is_htmx:
            return HTMLResponse(content=_triage_result_banner(result))
        return RedirectResponse(url="/triage", status_code=303)

    if is_htmx:
        return HTMLResponse(content=_confirmation_banner(False))
    return RedirectResponse(url="/brain-dump", status_code=303)
