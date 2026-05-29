"""Devices — CRUD and SSH connectivity test."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from foundry.dashboard import db

BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

router = APIRouter()


@router.get("/devices", response_class=HTMLResponse)
async def devices_list(request: Request) -> HTMLResponse:
    conn = db.get_conn()
    try:
        devices = db.devices_list(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(request, "devices.html", {"devices": devices})


@router.get("/devices/new", response_class=HTMLResponse)
async def new_device_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "device_form.html", {"device": None})


@router.post("/devices/new", response_class=HTMLResponse)
async def create_device(
    request: Request,
    device_id: str = Form(...),
    display_name: str = Form(...),
    os: str = Form("linux"),
    ssh_host: str = Form(""),
    ssh_port: int = Form(22),
    ssh_user: str = Form(""),
    notes: str = Form(""),
) -> HTMLResponse:
    conn = db.get_conn()
    try:
        db.device_create(
            conn,
            device_id=device_id,
            display_name=display_name,
            os=os,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            ssh_user=ssh_user,
            notes=notes,
        )
    finally:
        conn.close()
    return RedirectResponse(url="/devices", status_code=303)


@router.get("/devices/{device_pk}/edit", response_class=HTMLResponse)
async def edit_device_form(request: Request, device_pk: int) -> HTMLResponse:
    conn = db.get_conn()
    try:
        device = db.device_get(conn, device_pk)
    finally:
        conn.close()
    if device is None:
        return templates.TemplateResponse(
            request, "404.html", {"message": "Device not found."}, status_code=404
        )
    return templates.TemplateResponse(request, "device_form.html", {"device": device})


@router.post("/devices/{device_pk}/edit", response_class=HTMLResponse)
async def update_device(
    request: Request,
    device_pk: int,
    device_id: str = Form(...),
    display_name: str = Form(...),
    os: str = Form("linux"),
    ssh_host: str = Form(""),
    ssh_port: int = Form(22),
    ssh_user: str = Form(""),
    notes: str = Form(""),
) -> HTMLResponse:
    conn = db.get_conn()
    try:
        db.device_update(
            conn, device_pk,
            device_id=device_id,
            display_name=display_name,
            os=os,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            ssh_user=ssh_user,
            notes=notes,
        )
    finally:
        conn.close()
    return RedirectResponse(url="/devices", status_code=303)


@router.post("/devices/{device_pk}/delete")
async def delete_device(request: Request, device_pk: int):
    conn = db.get_conn()
    try:
        db.device_delete(conn, device_pk)
    finally:
        conn.close()
    return RedirectResponse(url="/devices", status_code=303)


@router.post("/devices/{device_pk}/test", response_class=HTMLResponse)
async def test_device(request: Request, device_pk: int) -> HTMLResponse:
    conn = db.get_conn()
    try:
        device = db.device_get(conn, device_pk)
    finally:
        conn.close()

    if device is None:
        return HTMLResponse('<span class="text-red-400 text-sm">Device not found</span>')

    from foundry.devices.manager import DeviceManager
    if DeviceManager.is_local(device):
        return HTMLResponse('<span class="text-green-400 text-sm">✓ Local device — no SSH needed</span>')

    from foundry.executor.ssh import SSHRunner
    runner = SSHRunner(device)
    result = runner.run("echo ok")
    if result.returncode == 0 and "ok" in result.stdout:
        return HTMLResponse('<span class="text-green-400 text-sm">✓ SSH connection OK</span>')
    err = result.stderr.strip() or result.stdout.strip() or "connection failed"
    return HTMLResponse(f'<span class="text-red-400 text-sm">✗ {err}</span>')
