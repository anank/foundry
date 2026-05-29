"""SSHRunner — wraps subprocess calls to the ssh CLI for remote execution."""

from __future__ import annotations

import subprocess
from typing import Optional


class SSHRunner:
    def __init__(self, device: dict) -> None:
        self._device = device

    def _ssh_prefix(self) -> list[str]:
        host = self._device["ssh_host"]
        port = self._device.get("ssh_port", 22)
        user = self._device.get("ssh_user", "")
        target = f"{user}@{host}" if user else host
        return [
            "ssh",
            "-p", str(port),
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10",
            "-o", "StrictHostKeyChecking=accept-new",
            target,
        ]

    def run(self, cmd: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            self._ssh_prefix() + [cmd],
            capture_output=True,
            text=True,
        )

    def run_in_tmux(
        self,
        session_name: str,
        cmd: str,
        log_path: str,
    ) -> subprocess.CompletedProcess:
        full_cmd = (
            f"tmux new-session -d -s {session_name} -- "
            f"bash -c '{cmd} 2>&1 | tee {log_path}'"
        )
        return self.run(full_cmd)

    def tmux_session_exists(self, session_name: str) -> bool:
        result = self.run(f"tmux has-session -t {session_name} 2>/dev/null && echo yes || echo no")
        return result.stdout.strip() == "yes"

    def kill_tmux(self, session_name: str) -> subprocess.CompletedProcess:
        return self.run(f"tmux kill-session -t {session_name}")

    @staticmethod
    def run_local_in_tmux(
        session_name: str,
        cmd: str,
        log_path: str,
    ) -> subprocess.CompletedProcess:
        full_cmd = (
            f"tmux new-session -d -s {session_name} -- "
            f"bash -c '{cmd} 2>&1 | tee {log_path}'"
        )
        return subprocess.run(full_cmd, shell=True, capture_output=True, text=True)

    @staticmethod
    def local_tmux_session_exists(session_name: str) -> bool:
        result = subprocess.run(
            f"tmux has-session -t {session_name} 2>/dev/null && echo yes || echo no",
            shell=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() == "yes"
