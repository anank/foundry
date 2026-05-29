"""Public API endpoints — for cron jobs, MCP, and external integrations."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from foundry.dashboard import db
from foundry.executor.runner import dispatch

router = APIRouter(prefix="/api")


@router.get("/projects")
def api_projects():
    """List all projects with their next queued task."""
    conn = db.get_conn()
    try:
        projects = db.projects_list(conn)
        result = []
        for p in projects:
            next_task = db.task_next(conn, p["id"])
            result.append({
                "id": p["id"],
                "name": p["name"],
                "status": p["status"],
                "priority": p["priority"],
                "default_device_id": p.get("default_device_id"),
                "next_task": {
                    "id": next_task["id"],
                    "title": next_task["title"],
                    "priority": next_task["priority"],
                } if next_task else None,
            })
    finally:
        conn.close()
    return result


@router.get("/projects/{name}/next-task")
def api_next_task(name: str):
    """Get the next queued task for a project."""
    conn = db.get_conn()
    try:
        project = db.project_get_by_name(conn, name)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project '{name}' not found")
        task = db.task_next(conn, project["id"])
        if not task:
            return {"status": "idle", "project": name}
        return {
            "status": "ready",
            "project": name,
            "task_id": task["id"],
            "task_title": task["title"],
            "default_device_id": project.get("default_device_id"),
        }
    finally:
        conn.close()


@router.post("/tasks/{task_id}/run")
def api_run_task(task_id: int, device_id: int | None = None):
    """Run a task on a device. Uses project default device if device_id omitted.

    Designed for cron jobs:
        curl -X POST http://localhost:8000/api/tasks/1/run
        curl -X POST http://localhost:8000/api/tasks/1/run?device_id=2
    """
    conn = db.get_conn()
    try:
        task = db.task_get(conn, task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        # Resolve device: explicit > project default > error
        if device_id is None:
            project = db.project_get(conn, task["project_id"])
            device_id = project.get("default_device_id") if project else None

        if device_id is None:
            raise HTTPException(
                status_code=400,
                detail="No device_id provided and no default device set for this project. "
                       "Set a default device on the project's Devices tab.",
            )
    finally:
        conn.close()

    result = dispatch(task_id, device_id)
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.post("/projects/{name}/run-next")
def api_run_next(name: str, device_id: int | None = None):
    """Pick and run the next queued task for a project. Perfect for cron.

    Example crontab (run next task every hour):
        0 * * * * curl -s -X POST http://localhost:8000/api/projects/my-proj/run-next
    """
    conn = db.get_conn()
    try:
        project = db.project_get_by_name(conn, name)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

        task = db.task_next(conn, project["id"])
        if not task:
            return {"status": "idle", "project": name, "message": "No queued tasks"}

        resolved_device_id = device_id or project.get("default_device_id")
        if not resolved_device_id:
            raise HTTPException(
                status_code=400,
                detail="No device_id provided and no default device set for this project.",
            )

        task_id = task["id"]
    finally:
        conn.close()

    result = dispatch(task_id, resolved_device_id)
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["error"])
    return {"status": "ok", "project": name, "task_id": task_id, **result}
