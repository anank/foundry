"""Task dispatcher — runs claude in the project directory on a target device."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from foundry.dashboard import db
from foundry.devices.manager import DeviceManager


def _log_dir() -> Path:
    base = Path(os.environ.get("FOUNDRY_DB_PATH", Path.home() / ".foundry" / "foundry.db")).parent
    log_dir = base / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _run_local(
    posix_cmd: str,
    cmd_args: list[str],
    local_path: str,
    log_path: str,
    session_name: str,
) -> str:
    """Launch a command locally, non-blocking. Returns the session name used.

    Tries tmux first (POSIX). Falls back to detached Popen on Windows or when
    tmux is unavailable — uses cmd_args + cwd so no shell quoting is needed.
    Raises RuntimeError with a human-readable message on launch failure.
    """
    try:
        result = subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name,
             "--", "bash", "-c", f"{posix_cmd} 2>&1 | tee {log_path}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()[:300]
            raise RuntimeError(f"tmux launch failed: {err or 'is tmux installed?'}")
        return session_name
    except FileNotFoundError:
        # tmux not available (e.g. Windows) — fall back to detached Popen.
        # Use cmd_args list + cwd to avoid shell quoting entirely.
        try:
            log_file = open(log_path, "w")
            # Detach from the parent process so the run survives server restarts.
            # start_new_session is POSIX-only; Windows needs DETACHED_PROCESS flag.
            if os.name == "nt":
                extra = {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
            else:
                extra = {"start_new_session": True}
            subprocess.Popen(
                cmd_args,
                cwd=local_path,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                **extra,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Command not found: {cmd_args[0]!r} — is it installed and in PATH?"
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"Process launch failed: {exc}") from exc
        return ""  # no tmux session to attach to


def dispatch(task_id: int, device_pk: int) -> dict:
    """Run the configured claude command for task_id on device_pk.

    Returns dict with keys: status, run_id, command, log_path, tmux_session,
    device_name, is_local, error.
    """
    conn = db.get_conn()
    try:
        task = db.task_get(conn, task_id)
        if task is None:
            return {"status": "error", "error": f"Task {task_id} not found"}

        device = db.device_get(conn, device_pk)
        if device is None:
            return {"status": "error", "error": f"Device {device_pk} not found"}

        path_row = db.path_get(conn, task["project_id"], device_pk)
        if path_row is None:
            return {
                "status": "error",
                "error": f"No local path configured for this project on device '{device['display_name']}'",
            }

        local_path = path_row["local_path"]
        run_command = db.setting_get(conn, "run_command", "claude --dangerously-skip-permissions")

        task_desc = task["title"]
        if task.get("description"):
            task_desc = f"{task['title']}: {task['description']}"

        # POSIX shell string — used by tmux/SSH (both POSIX-only paths)
        safe_desc = task_desc.replace("'", "'\\''")
        posix_cmd = f"cd '{local_path}' && {run_command} '{safe_desc}'"

        # Arg list — used by the Windows/no-tmux Popen fallback (no shell quoting needed)
        cmd_args = shlex.split(run_command) + [task_desc]

        session_name = f"foundry-task-{task_id}"
        is_local = DeviceManager.is_local(device)

        if is_local:
            log_path = str(_log_dir() / f"run-{task_id}-{device_pk}.log")
            try:
                session_name = _run_local(posix_cmd, cmd_args, local_path, log_path, session_name)
            except RuntimeError as exc:
                return {"status": "error", "error": str(exc)}
        else:
            remote_log_dir = "/root/.foundry/logs"
            log_path = f"{remote_log_dir}/run-{task_id}-{device_pk}.log"
            from foundry.executor.ssh import SSHRunner
            runner = SSHRunner(device)
            mkdir_result = runner.run(f"mkdir -p {remote_log_dir}")
            if mkdir_result.returncode != 0:
                err = (mkdir_result.stderr or "").strip()[:300]
                return {"status": "error", "error": f"SSH failed: {err or 'check host/key config'}"}
            run_result = runner.run_in_tmux(session_name, posix_cmd, log_path)
            if run_result.returncode != 0:
                err = (run_result.stderr or "").strip()[:300]
                return {"status": "error", "error": f"Remote tmux failed (exit {run_result.returncode}): {err or 'is tmux installed on remote?'}"}

        run_id = db.run_create(
            conn,
            task_id=task_id,
            device_pk=device_pk,
            tmux_session=session_name,
            command=posix_cmd,
            log_path=log_path,
        )
        db.task_update(conn, task_id, status="running")

        return {
            "status": "ok",
            "run_id": run_id,
            "command": posix_cmd,
            "log_path": log_path,
            "tmux_session": session_name,
            "is_local": is_local,
            "device_name": device["display_name"],
        }
    finally:
        conn.close()
