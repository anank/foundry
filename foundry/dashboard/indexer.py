"""VaultIndexer — reads vault markdown files and populates a SQLite database.

The indexer is intentionally simple: raw sqlite3, no ORM, no async.
It is designed to be run as a background process alongside the dashboard.

Usage
-----
    from pathlib import Path
    from foundry.dashboard.indexer import VaultIndexer

    indexer = VaultIndexer(vault_path=Path("/path/to/vault"), db_path=Path("/path/to/foundry.db"))
    indexer.init_db()
    indexer.index_all()
    indexer.watch()   # blocking — re-indexes on file changes
"""

from __future__ import annotations

import logging
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers (inline YAML parser — mirrors the one in vault/reader.py so we
# don't import from there and create a cross-layer dependency)
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s*$", re.MULTILINE)


def _parse_inline_yaml(block: str) -> dict:
    """Parse 'key: value' lines from a markdown block.

    Lines that don't look like top-level YAML key/value pairs are skipped
    silently so free-form prose doesn't break parsing.
    """
    import yaml  # pyyaml is already a project dependency

    lines = []
    for line in block.splitlines():
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*:", line):
            lines.append(line)
    if not lines:
        return {}
    try:
        return yaml.safe_load("\n".join(lines)) or {}
    except Exception:
        return {}


def _dir_mtime(path: Path) -> Optional[float]:
    """Return the mtime of a directory, or None if it doesn't exist."""
    try:
        return path.stat().st_mtime
    except OSError:
        return None


# ---------------------------------------------------------------------------
# VaultIndexer
# ---------------------------------------------------------------------------


class VaultIndexer:
    """Index vault markdown files into a SQLite database.

    Parameters
    ----------
    vault_path:
        Root of the vault directory tree.
    db_path:
        Path to the SQLite database file (created if it doesn't exist).
    poll_interval:
        Seconds between mtime checks in ``watch()``.  Default 5.
    """

    def __init__(
        self,
        vault_path: Path,
        db_path: Path,
        poll_interval: float = 5.0,
    ) -> None:
        self.vault_path = Path(vault_path)
        self.db_path = Path(db_path)
        self.poll_interval = poll_interval

    # ------------------------------------------------------------------
    # DB lifecycle
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Create tables if they don't already exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS brain_dump_entries (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    type TEXT,
                    project TEXT,
                    content TEXT,
                    status TEXT DEFAULT 'pending'
                );

                CREATE TABLE IF NOT EXISTS projects (
                    name TEXT PRIMARY KEY,
                    status TEXT,
                    description TEXT,
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    project TEXT,
                    title TEXT,
                    status TEXT,
                    review_tag TEXT,
                    estimated_diff INTEGER,
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS graveyard_entries (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    verdict TEXT,
                    verdict_reasoning TEXT,
                    killed_at TEXT
                );
            """)

    # ------------------------------------------------------------------
    # Full re-index
    # ------------------------------------------------------------------

    def index_all(self) -> None:
        """Re-index all vault sections."""
        self.index_brain_dump()
        self.index_projects()
        self.index_graveyard()

    # ------------------------------------------------------------------
    # Brain dump
    # ------------------------------------------------------------------

    def index_brain_dump(self) -> None:
        """Index all monthly brain-dump files into ``brain_dump_entries``."""
        brain_dump_dir = self.vault_path / "brain-dump"
        if not brain_dump_dir.exists():
            logger.debug("brain-dump dir not found, skipping")
            return

        rows: list[tuple] = []
        try:
            md_files = sorted(brain_dump_dir.glob("*.md"))
        except OSError as exc:
            logger.warning("Could not list brain-dump dir: %s", exc)
            return

        for md_file in md_files:
            try:
                content = md_file.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("Could not read %s: %s", md_file, exc)
                continue

            # Split on ## YYYY-MM-DD HH:MM headings
            parts = _HEADING_RE.split(content)
            it = iter(parts[1:])
            for timestamp, body in zip(it, it):
                data = _parse_inline_yaml(body)
                if not data.get("type"):
                    continue
                # Use "YYYY-MM-DD_HH:MM" as a stable row id
                entry_id = timestamp.strip().replace(" ", "_")
                rows.append((
                    entry_id,
                    timestamp.strip(),
                    data.get("type"),
                    data.get("project") or None,
                    data.get("content", ""),
                    data.get("triage_status", "pending"),
                ))

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO brain_dump_entries (id, timestamp, type, project, content, status)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    timestamp = excluded.timestamp,
                    type = excluded.type,
                    project = excluded.project,
                    content = excluded.content,
                    status = excluded.status
                """,
                rows,
            )
        logger.info("Indexed %d brain-dump entries", len(rows))

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def index_projects(self) -> None:
        """Index all project directories into ``projects`` and their tasks into ``tasks``."""
        projects_dir = self.vault_path / "projects"
        if not projects_dir.exists():
            logger.debug("projects dir not found, skipping")
            return

        project_rows: list[tuple] = []
        task_rows: list[tuple] = []

        try:
            project_dirs = sorted(
                p for p in projects_dir.iterdir()
                if p.is_dir() and not p.name.startswith("_")
            )
        except OSError as exc:
            logger.warning("Could not list projects dir: %s", exc)
            return

        for proj_dir in project_dirs:
            name = proj_dir.name
            project_md = proj_dir / "PROJECT.md"

            status = None
            description = None
            created_at = None

            if project_md.exists():
                try:
                    content = project_md.read_text(encoding="utf-8")
                    header_end = re.search(r"^##\s", content, re.MULTILINE)
                    header_block = content[: header_end.start()] if header_end else content
                    data = _parse_inline_yaml(header_block)
                    status = data.get("status")
                    created_at = str(data.get("created")) if data.get("created") else None

                    # Extract ## Description section
                    desc_match = re.search(
                        r"^##\s+Description\s*\n(.*?)(?=^##\s|\Z)",
                        content,
                        re.MULTILINE | re.DOTALL,
                    )
                    description = desc_match.group(1).strip() if desc_match else None
                except OSError as exc:
                    logger.warning("Could not read PROJECT.md for %s: %s", name, exc)

            project_rows.append((name, status, description, created_at))

            # Index tasks for this project
            tasks_dir = proj_dir / "tasks"
            if tasks_dir.exists():
                try:
                    task_files = sorted(tasks_dir.glob("*.md"))
                except OSError:
                    task_files = []

                for task_file in task_files:
                    try:
                        task_content = task_file.read_text(encoding="utf-8")
                    except OSError as exc:
                        logger.warning("Could not read task file %s: %s", task_file, exc)
                        continue

                    # Parse header (before first ## section)
                    header_end = re.search(r"^##\s", task_content, re.MULTILINE)
                    header_block = task_content[: header_end.start()] if header_end else task_content
                    header_lines = [l for l in header_block.splitlines() if not l.startswith("#")]
                    data = _parse_inline_yaml("\n".join(header_lines))

                    # Derive task id from filename prefix
                    stem = task_file.stem
                    task_id_raw = stem.split("-")[0] if "-" in stem else stem
                    task_id = f"{name}/{task_id_raw}"

                    # Title from # Task NNN: ... heading
                    title_match = re.search(r"^#\s+Task\s+\S+:\s+(.+)$", task_content, re.MULTILINE)
                    title = title_match.group(1).strip() if title_match else stem

                    estimated_diff = data.get("estimated_diff")
                    if estimated_diff is not None:
                        try:
                            estimated_diff = int(str(estimated_diff).split()[0])
                        except (ValueError, IndexError):
                            estimated_diff = None

                    created_at_task = str(data.get("created")) if data.get("created") else None

                    task_rows.append((
                        task_id,
                        name,
                        title,
                        data.get("status", "queued"),
                        data.get("review_tag", "code"),
                        estimated_diff,
                        created_at_task,
                    ))

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO projects (name, status, description, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    status = excluded.status,
                    description = excluded.description,
                    created_at = excluded.created_at
                """,
                project_rows,
            )
            conn.executemany(
                """
                INSERT INTO tasks (id, project, title, status, review_tag, estimated_diff, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    project = excluded.project,
                    title = excluded.title,
                    status = excluded.status,
                    review_tag = excluded.review_tag,
                    estimated_diff = excluded.estimated_diff,
                    created_at = excluded.created_at
                """,
                task_rows,
            )
        logger.info(
            "Indexed %d projects, %d tasks", len(project_rows), len(task_rows)
        )

    # ------------------------------------------------------------------
    # Graveyard
    # ------------------------------------------------------------------

    def index_graveyard(self) -> None:
        """Index all graveyard files into ``graveyard_entries``."""
        graveyard_dir = self.vault_path / "graveyard"
        if not graveyard_dir.exists():
            logger.debug("graveyard dir not found, skipping")
            return

        rows: list[tuple] = []

        try:
            md_files = sorted(graveyard_dir.rglob("*.md"))
        except OSError as exc:
            logger.warning("Could not list graveyard dir: %s", exc)
            return

        for md_file in md_files:
            try:
                content = md_file.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("Could not read %s: %s", md_file, exc)
                continue

            # Extract title from "# Killed: <title>" heading
            title_match = re.search(r"^#\s+Killed:\s+(.+)$", content, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else md_file.stem

            # Parse inline YAML fields (killed_date, verdict, revival_condition)
            # These appear right after the # heading line
            data = _parse_inline_yaml(content)

            verdict = data.get("verdict") or None
            killed_at = str(data.get("killed_date")) if data.get("killed_date") else None

            # Extract ## Verdict Reasoning section
            reasoning_match = re.search(
                r"^##\s+Verdict Reasoning\s*\n(.*?)(?=^##\s|\Z)",
                content,
                re.MULTILINE | re.DOTALL,
            )
            verdict_reasoning = reasoning_match.group(1).strip() if reasoning_match else None

            # Use the file stem as the id (unique within graveyard)
            entry_id = md_file.stem

            rows.append((entry_id, title, verdict, verdict_reasoning, killed_at))

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO graveyard_entries (id, title, verdict, verdict_reasoning, killed_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    verdict = excluded.verdict,
                    verdict_reasoning = excluded.verdict_reasoning,
                    killed_at = excluded.killed_at
                """,
                rows,
            )
        logger.info("Indexed %d graveyard entries", len(rows))

    # ------------------------------------------------------------------
    # File watcher (polling)
    # ------------------------------------------------------------------

    def watch(self) -> None:
        """Block and re-index vault sections when their directory mtime changes.

        Polls every ``self.poll_interval`` seconds.  Uses directory mtime
        rather than watchfiles to avoid adding a dependency.
        """
        watched_dirs = {
            "brain-dump": self.vault_path / "brain-dump",
            "projects": self.vault_path / "projects",
            "graveyard": self.vault_path / "graveyard",
        }

        # Capture initial mtimes
        last_mtimes: dict[str, Optional[float]] = {
            key: _dir_mtime(path) for key, path in watched_dirs.items()
        }

        indexers = {
            "brain-dump": self.index_brain_dump,
            "projects": self.index_projects,
            "graveyard": self.index_graveyard,
        }

        logger.info(
            "Watching vault at %s (poll interval: %ss)",
            self.vault_path,
            self.poll_interval,
        )

        while True:
            time.sleep(self.poll_interval)
            for key, path in watched_dirs.items():
                current_mtime = _dir_mtime(path)
                if current_mtime != last_mtimes[key]:
                    logger.info("Change detected in %s, re-indexing", key)
                    try:
                        indexers[key]()
                    except Exception as exc:
                        logger.error("Re-index failed for %s: %s", key, exc)
                    last_mtimes[key] = current_mtime
