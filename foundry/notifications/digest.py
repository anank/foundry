"""Build digest stats from the vault for the daily Telegram digest."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def build_digest_stats(vault_path: Path) -> dict:
    """Read vault and return a stats dict suitable for ``TelegramNotifier.send_daily_digest``.

    Keys returned:
    - ``pending_triage``: brain dump entries with triage_status == "pending"
      across all monthly files for the current month.
    - ``building``: projects with status == "building".
    - ``review_queue``: tasks with status == "review" across all projects.
    - ``killed_today``: files in ``graveyard/`` whose mtime is today (UTC).

    All counts default to 0 on any read error so the digest always sends.
    """
    vault_path = Path(vault_path)
    stats: dict[str, int] = {
        "pending_triage": 0,
        "building": 0,
        "review_queue": 0,
        "killed_today": 0,
    }

    # --- pending triage: parse current month's brain-dump file ---------------
    try:
        month = date.today().strftime("%Y-%m")
        brain_dump_file = vault_path / "brain-dump" / f"{month}.md"
        if brain_dump_file.exists():
            # Import here to avoid circular issues at module level
            from foundry.vault.reader import VaultReader

            reader = VaultReader(vault_path)
            entries = reader.read_brain_dump(month)
            stats["pending_triage"] = sum(
                1 for e in entries if e.triage_status == "pending"
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("digest: could not count pending triage entries: %s", exc)

    # --- building projects ----------------------------------------------------
    try:
        projects_dir = vault_path / "projects"
        if projects_dir.exists():
            from foundry.vault.reader import VaultReader

            reader = VaultReader(vault_path)
            for project_name in reader.list_projects():
                try:
                    project = reader.read_project(project_name)
                    if project.status == "building":
                        stats["building"] += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "digest: could not read project '%s': %s", project_name, exc
                    )
    except Exception as exc:  # noqa: BLE001
        logger.warning("digest: could not count building projects: %s", exc)

    # --- review queue: tasks with status == "review" -------------------------
    try:
        projects_dir = vault_path / "projects"
        if projects_dir.exists():
            from foundry.vault.reader import VaultReader

            reader = VaultReader(vault_path)
            for project_name in reader.list_projects():
                tasks_dir = projects_dir / project_name / "tasks"
                if not tasks_dir.exists():
                    continue
                for task_file in sorted(tasks_dir.glob("*.md")):
                    try:
                        task = reader.read_task(project_name, task_file.name)
                        if task.status == "review":
                            stats["review_queue"] += 1
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "digest: could not read task '%s/%s': %s",
                            project_name,
                            task_file.name,
                            exc,
                        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("digest: could not count review queue tasks: %s", exc)

    # --- killed today: graveyard file mtimes ---------------------------------
    try:
        graveyard_dir = vault_path / "graveyard"
        if graveyard_dir.exists():
            today_utc = datetime.now(tz=timezone.utc).date()
            for entry in graveyard_dir.iterdir():
                try:
                    mtime = datetime.fromtimestamp(
                        entry.stat().st_mtime, tz=timezone.utc
                    ).date()
                    if mtime == today_utc:
                        stats["killed_today"] += 1
                except Exception:  # noqa: BLE001
                    pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("digest: could not count killed-today entries: %s", exc)

    return stats
