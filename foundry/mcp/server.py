"""FastMCP server — read and write tools exposing vault data to Claude.ai."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from fastmcp import FastMCP

mcp = FastMCP("foundry")


def _vault() -> Path:
    return Path(os.environ.get("FOUNDRY_VAULT_PATH", "vault"))


# ---------------------------------------------------------------------------
# Frontmatter helpers
# ---------------------------------------------------------------------------


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body) from a file that may start with --- delimiters.

    If no frontmatter is present, returns ({}, full text).
    """
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_block = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    try:
        data = yaml.safe_load(fm_block) or {}
    except yaml.YAMLError:
        data = {}
    return data, body


# ---------------------------------------------------------------------------
# Read-only tools
# ---------------------------------------------------------------------------


@mcp.tool()
def get_goals() -> str:
    """Get the vault goals.md content."""
    path = _vault() / "goals.md"
    if not path.exists():
        return "Not found."
    return path.read_text(encoding="utf-8")


@mcp.tool()
def get_principles() -> str:
    """Get the vault principles.md content."""
    path = _vault() / "principles.md"
    if not path.exists():
        return "Not found."
    return path.read_text(encoding="utf-8")


@mcp.tool()
def get_existing_systems() -> str:
    """Get the existing-systems.md inventory."""
    path = _vault() / "existing-systems.md"
    if not path.exists():
        return "Not found."
    return path.read_text(encoding="utf-8")


@mcp.tool()
def list_projects() -> str:
    """List all projects with their status."""
    projects_dir = _vault() / "projects"
    if not projects_dir.exists():
        return "No projects found."

    dirs = sorted(
        p for p in projects_dir.iterdir()
        if p.is_dir() and not p.name.startswith("_")
    )
    if not dirs:
        return "No projects found."

    lines: list[str] = []
    for project_dir in dirs:
        project_md = project_dir / "PROJECT.md"
        status = "unknown"
        if project_md.exists():
            text = project_md.read_text(encoding="utf-8")
            data, _ = _parse_frontmatter(text)
            if not data:
                # Fall back to inline YAML key: value scan
                for line in text.splitlines():
                    m = re.match(r"^status\s*:\s*(.+)$", line)
                    if m:
                        status = m.group(1).strip()
                        break
            else:
                status = data.get("status", "unknown")
        lines.append(f"- **{project_dir.name}** — {status}")

    return "\n".join(lines)


@mcp.tool()
def get_project(name: str) -> str:
    """Get full details of a project including tasks."""
    project_dir = _vault() / "projects" / name
    if not project_dir.exists():
        return f"Project '{name}' not found."

    project_md = project_dir / "PROJECT.md"
    if not project_md.exists():
        return f"PROJECT.md not found for project '{name}'."

    content = project_md.read_text(encoding="utf-8")
    lines: list[str] = [f"# {name}", "", content.strip()]

    # List tasks if the tasks/ subdir exists
    tasks_dir = project_dir / "tasks"
    if tasks_dir.exists():
        task_files = sorted(tasks_dir.glob("*.md"))
        if task_files:
            lines.append("\n## Tasks")
            for tf in task_files:
                task_text = tf.read_text(encoding="utf-8")
                data, _ = _parse_frontmatter(task_text)
                status = data.get("status", "unknown")
                # Try inline YAML fallback
                if not data:
                    for line in task_text.splitlines():
                        m = re.match(r"^status\s*:\s*(.+)$", line)
                        if m:
                            status = m.group(1).strip()
                            break
                lines.append(f"- **{tf.stem}** — {status}")

    return "\n".join(lines)


@mcp.tool()
def get_pipeline() -> str:
    """Get pipeline status: operating/building/queued/parked counts and names."""
    projects_dir = _vault() / "projects"
    if not projects_dir.exists():
        return "No projects found."

    dirs = sorted(
        p for p in projects_dir.iterdir()
        if p.is_dir() and not p.name.startswith("_")
    )
    if not dirs:
        return "No projects found."

    groups: dict[str, list[str]] = {
        "operating": [],
        "building": [],
        "queued": [],
        "parked": [],
        "other": [],
    }

    for project_dir in dirs:
        project_md = project_dir / "PROJECT.md"
        status = "other"
        if project_md.exists():
            text = project_md.read_text(encoding="utf-8")
            data, _ = _parse_frontmatter(text)
            if data:
                status = data.get("status", "other")
            else:
                for line in text.splitlines():
                    m = re.match(r"^status\s*:\s*(.+)$", line)
                    if m:
                        status = m.group(1).strip()
                        break
        bucket = status if status in groups else "other"
        groups[bucket].append(project_dir.name)

    lines: list[str] = []
    for bucket, names in groups.items():
        if not names:
            continue
        lines.append(f"**{bucket.capitalize()}** ({len(names)}): {', '.join(names)}")

    return "\n".join(lines) if lines else "No projects found."


@mcp.tool()
def search_graveyard(query: str) -> str:
    """Search killed ideas by keyword (case-insensitive)."""
    graveyard_dir = _vault() / "graveyard"
    if not graveyard_dir.exists():
        return "No graveyard entries found."

    query_lower = query.lower()
    matches: list[str] = []

    for path in sorted(graveyard_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if query_lower in text.lower():
            # Return filename + first non-empty content line as a summary
            data, body = _parse_frontmatter(text)
            summary_line = ""
            for line in body.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    summary_line = line[:120]
                    break
            matches.append(f"- **{path.stem}**: {summary_line}")

    if not matches:
        return f"No graveyard entries matching '{query}'."
    return f"Found {len(matches)} match(es) for '{query}':\n" + "\n".join(matches)


@mcp.tool()
def get_brain_dump(status: str = "pending") -> str:
    """Get brain dump entries filtered by status (pending/triaged/killed/all).

    Scans all .md files in vault/brain-dump/ and filters by the 'triage_status'
    frontmatter field. Pass status='all' to return every entry.
    """
    brain_dump_dir = _vault() / "brain-dump"
    if not brain_dump_dir.exists():
        return "No brain dump entries found."

    files = sorted(brain_dump_dir.glob("*.md"))
    if not files:
        return "No brain dump entries found."

    entries: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        data, body = _parse_frontmatter(text)

        entry_status = data.get("triage_status", "pending")

        if status != "all" and entry_status != status:
            continue

        # Build a compact summary line
        entry_type = data.get("type", "unknown")
        project = data.get("project", "")
        project_tag = f" [{project}]" if project else ""
        # First non-empty body line as content preview
        preview = ""
        for line in body.splitlines():
            line = line.strip()
            if line:
                preview = line[:100]
                break
        if not preview:
            preview = data.get("content", "")[:100]

        entries.append(
            f"- **{path.stem}** ({entry_type}{project_tag}, {entry_status}): {preview}"
        )

    if not entries:
        label = "all" if status == "all" else f"status='{status}'"
        return f"No brain dump entries found for {label}."

    label = "all" if status == "all" else f"status='{status}'"
    return f"Brain dump entries ({label}) — {len(entries)} found:\n" + "\n".join(entries)


# ---------------------------------------------------------------------------
# Write tools — all destructive actions require confirm=True
# ---------------------------------------------------------------------------


@mcp.tool()
def add_brain_dump(content: str, type: str = "idea", project: str = "") -> str:
    """Add a new brain dump entry to the vault. Always writes immediately (additive, non-destructive)."""
    ts = datetime.now(timezone.utc)
    filename = ts.strftime("%Y-%m-%d-%H%M%S") + ".md"
    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S UTC")

    brain_dump_dir = _vault() / "brain-dump"
    brain_dump_dir.mkdir(parents=True, exist_ok=True)
    path = brain_dump_dir / filename

    frontmatter_lines = [
        "---",
        f"type: {type}",
    ]
    if project:
        frontmatter_lines.append(f"project: {project}")
    frontmatter_lines += [
        f"timestamp: {ts_str}",
        "status: pending",
        "---",
        "",
        content,
    ]
    path.write_text("\n".join(frontmatter_lines), encoding="utf-8")
    return f"Created {path}"


@mcp.tool()
def trigger_triage(entry_id: str, confirm: bool = False) -> str:
    """Trigger triage on a brain dump entry. Requires confirm=True to actually run."""
    if not confirm:
        return (
            f"Would write vault/triage/pending/{entry_id}.trigger to queue triage. "
            "Call again with confirm=True to proceed."
        )

    pending_dir = _vault() / "triage" / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    marker = pending_dir / f"{entry_id}.trigger"
    marker.write_text(
        datetime.now(timezone.utc).isoformat(),
        encoding="utf-8",
    )
    return f"Triage queued: {marker}"


@mcp.tool()
def update_principles(new_content: str, confirm: bool = False) -> str:
    """Update vault/principles.md. Requires confirm=True to actually write."""
    if not confirm:
        preview = new_content[:120] + ("..." if len(new_content) > 120 else "")
        return (
            f"Would overwrite vault/principles.md with {len(new_content)} chars:\n"
            f"  {preview}\n"
            "Call again with confirm=True to proceed."
        )

    path = _vault() / "principles.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_content, encoding="utf-8")
    return f"Updated {path} ({len(new_content)} chars written)"


@mcp.tool()
def create_project(name: str, description: str, confirm: bool = False) -> str:
    """Create a new project directory in vault/projects/. Requires confirm=True."""
    if not confirm:
        return (
            f"Would create vault/projects/{name}/ with PROJECT.md "
            f"(description: {description[:80]}{'...' if len(description) > 80 else ''}). "
            "Call again with confirm=True to proceed."
        )

    project_dir = _vault() / "projects" / name
    project_dir.mkdir(parents=True, exist_ok=True)
    project_md = project_dir / "PROJECT.md"
    project_md.write_text(
        f"# {name}\n\n{description}\n",
        encoding="utf-8",
    )
    return f"Created project at {project_dir}"


@mcp.tool()
def set_pause(paused: bool, confirm: bool = False) -> str:
    """Set the executor pause flag. Requires confirm=True."""
    action = "create vault/.pause (executor will pause)" if paused else "delete vault/.pause (executor will resume)"
    if not confirm:
        return f"Would {action}. Call again with confirm=True to proceed."

    pause_file = _vault() / ".pause"
    if paused:
        pause_file.parent.mkdir(parents=True, exist_ok=True)
        pause_file.write_text(
            datetime.now(timezone.utc).isoformat(),
            encoding="utf-8",
        )
        return f"Executor paused: {pause_file} created"
    else:
        if pause_file.exists():
            pause_file.unlink()
            return f"Executor resumed: {pause_file} deleted"
        return "Executor was not paused (vault/.pause did not exist)"
